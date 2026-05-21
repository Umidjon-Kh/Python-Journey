from __future__ import annotations

from collections.abc import Mapping, Sequence
from json import dump, load
from logging import DEBUG, FileHandler, Formatter, Logger, getLogger
from os import replace
from pathlib import Path
from shutil import copy2, rmtree
from time import monotonic
from typing import Callable, Optional

from ...core import (
    BasePathLock,
    BaseSnapshotsRegistryStore,
    Event,
    EventType,
    Snapshot,
)
from ..utils import checksum, hash_path


class SAJSnapshotsRegistryStore(BaseSnapshotsRegistryStore):
    """
    Implementation of BaseSnapshotsRegistryStore that stores backup files
    on disk and persists snapshot metadata as JSON registry file.

    Why the unusual prefix in SAJSnapshotsRegistryStore:
        The prefix SAJ is not an accident. It was deliberately chosen by the project
        author (me) to encode three fundamental behavioural guarantees that this
        implementation provides. Anyone using this store must understand that SAJ
        stands for Secure, Atomic, Journaled. These three properties ensure predictable
        behaviour under unexpected crashes, concurrent access, and external interface
        with every failure leaving a trace.

        - Secure:
            All Snapshots of a concrete file system object are stored under the SHA-256
            hash of original path of this object. This provides two
            security-relevant benefits:
                1. Obfuscation: external or untrusted processes cannot easily determine
                    which file system object belongs to this backup.
                2. Collision avoidance: hashes are deterministic and unique, path length
                    limits are bypassed entirely.

            Separate Registry:
                A separate JSON registry maps hashed directories names back to real original
                paths. Only daemon (or authorised tools) can interpret that mapping.

            Integrity checks:
                Every backup file is validated with checksum before any read or restore
                operation. Corrupted or tampered objects are automatically discarded.

        - Atomic:
            Three-stage create/restore:
                1. Copy to a temporary path with ".vakt.back" suffix.
                2. Verify the checksum, that checks the copy is not corrupted or tampered.
                3. Atomically replace the target object (for restore)
                    or register the snapshot (for create).

            Atomic Registry writes:
                The JSON registry is first written to a temporary file, then os.replace()
                renames it over the real file. A crash during write leaves the original
                registry intact.

            Crash Recovery via tumbler flag:
                Each path in raw registry contains a boolean field "processing".
                Before starting a restore operation, the store sets processing to True
                and automatically persists updated registry.
                After successful completion, it sets processing to False back.
                If the daemon crashes in the middle of a restore, processing remains True
                fot that object. It means object is not restored completely, but temporary
                copy of object is remains in a file system.
                On its next run, _recover_tumblers() checks the entire registry for any
                path objects whose processing parameter is True and removes them all,
                simultaneously resetting their "processing" flags to False.
                This design guarantees that orphaned temporary object survives a crash.
                This operation is either fully completed or cleanly rolled back at the next start.

            Validation before read:
                Every snapshot is validated by its checksum before it is returned by get()
                or used in restore(). If snapshot is broken, it is automatically dropped and the
                latest valid snapshot is used instead (or None if none remain).

        - Journaled:
            Dedicated Journal file:
                Every operation (create, restore, get, delete, clear, and etc...) is logged
                to saj_operations.log that located next to the registry file.

            Level Marks:
                - Each public methods logs an INFO entry before starting and another
                    one after successful completion. A missing completion log is a clear
                    signal that an operation did not finish cleanly.
                - Not public internal operations that works in file system, logs a DEBUG
                    entry to show what happened and what dont happened in internal operations.
                - All Validations are logs a WARNING entry if object did not pass validation.

            Live Monitoring:
                Developers and system administrators can watch the journal in real time to
                understand what the store is doing. After crash, the journal helps reconstruct
                which operation was interrupted.

            No Internal Rotation:
                The journal file grows indefinitely. The user is solely responsible for log
                rotation, archival and deletion (e.g., via logrotate). This is intentional,
                the store makes no assumptions about external logging infrastructure.

    In a short:
        SAJSnapshotsRegistryStore is not just another disk-based registry. It is a Secure,
        Atomic, Journaled implementation that you can trust in production environments
        where crashes, concurrency, and untrusted processes are concern. The name
        itself communicates the three guarantees, so any developer who sees the class
        knows exactly what expect without reading the full implementation.

    Storage Layout:
        Backup files and registry are stored under two separate locations
        provided via __init__:

            {backup_dir}/
            └── {sha256(original_path)}/        ← obfuscated directory
                └── {monotonic_timestamp}.bak   ← backup file

            {registry_dir}/
            ├── snapshots_registry.json         ← snapshot metadata
            └── saj_operations.log             ← operation journal

    Registry Layout:
        The registry maps each original path to a processing flag and an
        ordered list of snapshot metadata dicts:

            {
                "/etc/passwd": {
                    "processing": false,
                    "snapshots": [
                        {
                            "original_path": "/etc/passwd",
                            "backup_path":   "{backup_dir}/{hash}/1716134400.0.bak",
                            "checksum":      "sha256...",
                            "created_at":    1716134400.0,
                            "event_type":    "file_modified",
                            "description":   null
                        }
                    ]
                }
            }

        Snapshots are ordered by created_at ascending.
        The latest snapshot is always at index -1.

    Notes:
        - backup_dir and registry_path parent directories are created
            automatically if they do not exist.
        - Registry loaded from disk on initialization if the file exists.
        - Log file is located next to registry file.
        - Snapshot history per path is ordered by created_at ascending.
            The latest snapshot is always at index -1.
        - If backup verification fails after copying, create() returns a Snapshot
            with empty string fields so the calling handler or other upper layer objects
            can detect the failure by checking it, without raising exceptions
            that could crash the Dispatcher.
        - All methods log their before and after processing. if you ant to remove
            unnecessary noise from the internal method logs, you can process
            only necessary logs by filtering them using external management tools.
            For example you can filter by semantic name of the method prefix, adding
            it to the list of desired logs.
    """

    _LOG_FILENAME = "saj_operations.log"

    def __init__(
        self, backup_dir: str, registry_path: str, path_lock: BasePathLock
    ) -> None:
        """
        Initializes the store, configures the operation journal, loads persisted
        snapshots metadata form disk if the registry file exists and its a JSON type
        file with valid format of data and recovers any incomplete operations leftovers
        via the tumbler flag. Also initializes BasePathLock implementation methods, if
        implementation has acquire_shared() method uses it instead of simple acquire()
        to enable reading (without modifying) file system object while
        SAJSnapshotsRegistryStore processes with it.
        """
        self._backup_dir: Path = Path(backup_dir)
        self._registry_path: Path = Path(registry_path)
        self._registry: dict[str, list[Snapshot]] = {}
        self._raw_registry: dict[str, dict] = {}
        self._acquire: Callable[[str], None] = (
            path_lock.acquire_shared  # type: ignore[assignment]
            if hasattr(path_lock, "acquire_shared")
            else path_lock.acquire
        )

        self._release: Callable[[str], None] = path_lock.release
        self._log: Logger = self._setup_logger()

        self._log.info(
            "(__init__) start: backup_dir=%s registry_path=%s",
            self._backup_dir,
            self._registry_path,
        )

        self._load()
        self._recover_tumblers()

        self._log.info(
            "(__init__) done: loaded %d paths, lock=%s",
            len(self._registry),
            type(path_lock).__name__,
        )

    def create(self, event: Event) -> Snapshot:
        """
        Creates a physical backup of the file system object described by the
        given event, registers the snapshot metadata and returns it.
        Acquires a shared lock before copying to block writes during backup.
        Verifies the backup integrity via checksum after copying. Registries
        the snapshot only after successful verification.
        Returns an empty Snapshot if copying or checksum verification fails,
        allowing the caller to detect failure without exceptions.
        """
        self._log.info("(create) start: path=%s", event.path)

        path = event.path
        timestamp = monotonic()
        backup_path = self._backup_dir / f"{hash_path(path)}/{timestamp}.back"
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        _empty = Snapshot(
            original_path=path,
            backup_path="",
            checksum="",
            created_at=timestamp,
            event_type=event.event_type,
        )

        self._acquire(path)
        try:
            locked_path = Path(path).with_suffix(".vakt.lock")
            file_checksum = checksum(str(locked_path))

            copy2(locked_path, backup_path)

            if checksum(str(backup_path)) != file_checksum:
                self._log.warning("(create) fail: checksum mismatch path=%s", path)
                backup_path.unlink(missing_ok=True)
                return _empty

            snapshot = Snapshot(
                original_path=path,
                backup_path=str(backup_path),
                checksum=file_checksum,
                created_at=timestamp,
                event_type=event.event_type,
            )

            self._registry.setdefault(path, []).append(snapshot)
            self._raw_registry.setdefault(path, {"processing": False, "snapshots": []})
            self._raw_registry[path]["snapshots"].append(self._to_dict(snapshot))
            self._save()

            self._log.info("(create) done: path=%s backup=%s", path, backup_path)

        finally:
            self._release(path)

        return snapshot

    def get(self, path: str, index: int) -> Optional[Snapshot]:
        """
        Returns a validated Snapshot for the given path at the given index.
        Falls back to the latest valid snapshot if the index is out of range
        or its backup object fails validation.
        Returns None if no valid snapshots exist for the given path.
        """
        self._log.info("(get) start: path=%s index=%d", path, index)

        snapshots = self._registry.get(path)

        if not snapshots:
            self._log.warning("(get) fail: no snapshots for path=%s", path)
            return None

        try:
            snapshot = snapshots[index]
            real_index = index if index >= 0 else len(snapshots) + index
        except IndexError:
            snapshot = snapshots[-1]
            real_index = len(snapshots) - 1

        response = self._validate(path, real_index, snapshot)

        if response is None:
            self._log.warning("(get) fail: no valid snapshots remaining path=%s", path)
        else:
            self._log.info("(get) done: path=%s index=%d", path, real_index)

        return response

    def restore(self, path: str, index: int) -> None:
        """
        Restores the file system object at the given path to the state
        captured in the snapshot at the given index.
        Acquires a shared lock during restore to block writes while restoring.
        Copies the backup to a temporary file first, verifies its checksum,
        then atomatically replaces the target via os.replace().
        Logs a WARNING entry and returns if the path or index does not exist,
        or if there are no valid snapshots exist for path.
        """

        self._log.warning("(restore) start: path=%s index=%d", path, index)

        snapshot = self.get(path, index)

        if snapshot is None:
            self._log.warning("(restore) fail: no valid snapshot path=%s", path)
            return

        locked_path = Path(path).with_suffix(".vakt.lock")
        tmp_path = Path(path + ".vakt.back")

        self._acquire(path)

        try:
            self._raw_registry[path]["processing"] = True
            self._save()

            copy2(snapshot.backup_path, tmp_path)

            if checksum(str(tmp_path)) != snapshot.checksum:
                self._log.info("(restore) fail: checksum mismatch path=%s", path)
                tmp_path.unlink(missing_ok=True)
                self._raw_registry[path]["processing"] = False
                self._save()
                return

            replace(tmp_path, locked_path)
            self._raw_registry[path]["processing"] = False
            self._save()

            self._log.info("(restore) done: path=%s index=%d", path, index)

        finally:
            self._release(path)

    def delete(self, path: str, index: int) -> None:
        """
        Removes the Snapshot at the given index from both registries and
        deletes its pysical backup object from disk.
        Logs a WARNING entry and returns if the path or index does not exist.
        """
        self._log.info("(delete) start: path=%s index=%d", path, index)

        if not self._registry:
            self._log.warning("(delete) skip: registry is empty"
            return

        snapshots = self._registry.get(path)

        if not snapshots:
            self._log.warning("(delete) skip: path not found path=%s", path)
            return

        try:
            real_index = index if index >= 0 else len(snapshots) + index
            snapshot = snapshots[real_index]
        except IndexError:
            self._log.warning("(delete) skip: index out of range path=%s index=%d", path, index)
            return

        Path(snapshot.backup_path).unlink(missing_ok=True)
        self._remove(path, real_index)

        self._log.info("(delete) done: path=%s index=%d", path, real_index)

    def history(self, path: str) -> Sequence[Snapshot]:
        """
        Returns all Snapshot for the given path ordered by created_at
        ascending. Returns an empty sequence if none exist.
        Returns a shallow copy not original because this method
        is intended only for view not to manage.
        """
        self._log.info("(history): path=%s", path)
        return self._registry.get(path, []).copy()

    def show(self) -> Mapping[str, Sequence[Snapshot]]:
        """
        Returns all registered Snapshot objects.

        The returned collection is the live internal registry.
        Any direct modifications with snapshots must be applied to both
        the domain registry and the raw registry to keep them in sync.
        If you want to manage the entire registry, not the concrete object
        use public methods (add/delete/cleare/clear_all) of SnapshotsRegistryStore.
        """
        self._log.info("(show): called")
        return self._registry

    def show_raw(self) -> Mapping[str, dict]:
        """
        Returns the raw registry with all Snapshots metadata.

        this gives upper layer objects a serialization-friendly view
        without manually decomposing Snapshot domain objects. The same
        synchronization requirement applies: changes must be reflected
        in both registries.
        """
        self._log.info("(show_raw): called")
        return self._raw_registry

    def clear(self, path: str) -> None:
        """
        Removes all Snapshots for the given path from the registry and
        deletes their backup directories from disk immediately.
        Logs a WARNING entry and returns if no Snapshots exist for the
        given path. Persists updated registry after removing.
        """
        self._log.info("(clear) start: path=%s", path)

        if path not in self._registry:
            self._log.warning("(clear) skip: path not found path=%s", path)
            return

        rmtree(self._backup_dir / hash_path(path), ignore_errors=True)
        del self._registry[path]
        del self._raw_registry[path]

        self._save()
        self._log.info("(clear) done: path=%s", path)

    def clear_all(self) -> None:
        """
        Removes all Snapshots from the registry and deletes all backups
        directories from disk entirely. Logs a WARNING entry if the registry
        is already empty.
        """
        self._log.info("(clear_all) start: total=%d paths", len(self._registry))

        if not self._registry:
            self._log.warning("(clear_all) skip: registry is empty")
            return

        rmtree(self._backup_dir, ignore_errors=True)
        self._registry.clear()
        self._raw_registry.clear()

        self._save()
        self._log.info("(clear_all) done")

    def _recover_tumblers(self) -> None:
        """
        Detects and cleans up incomplete restore operations leftovers
        from previous crash. Called once on initialization after loading the
        registry. Any path with processing True flag inidicates that the daemon is
        crashed during restore. The leftover .vakt.back file is removed and
        rocessing flag is restored to False.
        """
        self._log.debug(
            "(_recover_tumblers) start: checking %d paths", len(self._raw_registry)
        )

        for path, data in self._raw_registry.items():
            if data["processing"] is True:
                tmp_path = Path(path + ".vakt.back")
                self._log.debug("(_recover_tumblers): removed leftover %s", tmp_path)
                tmp_path.unlink(missing_ok=True)
                data["processing"] = False

        self._save()
        self._log.debug("(_recover_tumblers) done")

    def _validate(
        self, path: str, index: int, snapshot: Snapshot
    ) -> Optional[Snapshot]:
        """
        Validates the existence and checksum integrity of the given
        snapshot backup. If validation fails, the snapshot is removed
        (via _remove() method from both registries and physical deletion).
        Then recursively validates the latest remaining snapshot for the path.
        Returns None if no vaid snapshots remain.
        """
        self._log.debug("(_validate) start: path=%s index=%d", path, index)

        backup_path = Path(snapshot.backup_path)

        if not backup_path.exists():
            self._log.warning(
                "(_validate) fail: backup missing path=%s backup=%s",
                path,
                snapshot.backup_path,
            )

        elif checksum(str(backup_path)) != snapshot.checksum:
            self._log.warning(
                "(_validate) fail: checksum mismatch path=%s backup=%s",
                path,
                snapshot.backup_path,
            )
        else:
            self._log.debug("(_validate) done: path=%s index=%d", path, index)
            return snapshot

        backup_path.unlink(missing_ok=True)
        self._remove(path, index)
        remaining = self._registry.get(path)

        if not remaining:
            return None
        return self._validate(path, -1, remaining[-1])

    def _remove(self, path: str, index: int) -> None:
        """
        Removes a single snapshot entry at the given index from both
        registries and persists updated registry immediately.
        If no snapshots remain for the path, removes the path key entirely.
        """
        self._log.debug("(_remove) start: path=%s index=%d", path, index)

        self._registry[path].pop(index)
        self._raw_registry[path]["snapshots"].pop(index)
        if not self._registry[path]:
            del self._registry[path]
            del self._raw_registry[path]

        self._save()
        self._log.debug(
            "(_remove) done: %d snapshots remaining for %s",
            len(self._registry.get(path, [])),
            path,
        )

    def _save(self) -> None:
        """
        Automatically persists the raw registry to the JSON file on disk.
        Writes to a temporary file first then renames it over the target
        via os.replace(). On the same filesystem os.replace() operation
        is atomic at the kernel level - if the process crashes during the write
        the original registry file remains intact.
        """
        self._log.debug(
            "(_save) start: persisting %d paths to %s",
            len(self._raw_registry),
            self._registry_path,
        )

        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._registry_path.with_suffix(".tmp")

        with open(tmp_path, "w", encoding="utf-8") as file:
            dump(self._raw_registry, file, indent=4)

        replace(tmp_path, self._registry_path)

        self._log.debug("(_save) done: written to %s", self._registry_path)

    def _load(self) -> None:
        """
        Loads snapshots metadata form the JSON registry on disk.
        Silently skips if the file does not exist, Also ensure that
        the provided file is in valid format if it exists.
        """
        if not self._registry_path.exists():
            return

        self._log.debug("(_load) start: reading registry from %s", self._registry_path)

        with open(self._registry_path, encoding="utf-8") as file:
            self._raw_registry = load(file)

        for path, data in self._raw_registry.items():
            self._registry[path] = [
                Snapshot(
                    original_path=raw["original_path"],
                    backup_path=raw["backup_path"],
                    checksum=raw["checksum"],
                    created_at=raw["created_at"],
                    event_type=EventType(raw["event_type"]),
                    description=raw["description"],
                )
                for raw in data["snapshots"]
            ]

        self._log.debug(
            "(_load) done: loaded %d paths, %d total snapshots",
            len(self._registry),
            sum(len(v) for v in self._registry.values()),
        )

    def _setup_logger(self) -> Logger:
        """
        Configures a dedicated FileHandler that writes operation logs to
        saj_operations.log located next to the registry file. Returns the
        configured logger instance. Logger - does not responsible for rotation
        and other external log managament things.!
        """
        log_path = self._registry_path.parent / self._LOG_FILENAME
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger = getLogger(__name__)
        logger.setLevel(DEBUG)

        if not logger.handlers:
            handler = FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
        return logger

    @staticmethod
    def _to_dict(snapshot: Snapshot) -> dict:
        """
        Converts a Snapshot domain object to a raw dict for JSON serialization.
        """
        return {
            "original_path": snapshot.original_path,
            "backup_path": snapshot.backup_path,
            "checksum": snapshot.checksum,
            "created_at": snapshot.created_at,
            "event_type": snapshot.event_type,
            "description": snapshot.description,
        }
