from __future__ import annotations

from collections.abc import Mapping, Sequence
from json import dump, load
from logging import DEBUG, FileHandler, Formatter, Logger, getLogger
from os import makedirs, replace
from os.path import exists, isfile
from pathlib import Path
from shutil import copy2, copytree, rmtree
from time import monotonic
from typing import Any, Optional

from ...core import (
    BasePathLocker,
    BaseSnapshotsRegistryStore,
    Event,
    EventType,
    Snapshot,
)
from ..utils import checksum, hash_path


class SAJSnapshotsRegistryStore(BaseSnapshotsRegistryStore):
    """
    [existing class docstring — update Atomic section to mention .old approach for dirs,
    update _recover_tumblers section to mention .old recovery,
    update Notes to reflect ignoring_paths via config]
    """

    _LOG_FILENAME = "saj_operations.log"

    def __init__(self, config: dict[str, Any]) -> None:
        """
        Initializes the store from config dict. Configures the operation journal,
        loads persisted snapshots metadata from disk if the registry file exists,
        and recovers any incomplete operations via the tumbler flag.
        Any errors raised during file reading or parsing are intentionally not
        caught and propagate to the caller.
        """
        self._backup_dir: str = config["backup_dir"] + "/.vakt.backups"
        self._registry_path: str = config["registry_path"]
        self._path_locker: BasePathLocker = config["path_locker"]
        self._ignoring_paths: dict[str, int] = config["ignoring_paths"]
        self._registry: dict[str, list[Snapshot]] = {}
        self._raw_registry: dict[str, dict] = {}

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
            type(self._path_locker).__name__,
        )

    def create(self, event: Event) -> Snapshot:
        """
        Creates a physical backup of the file system object described by the
        given event. Supports both files and directories. Acquires a shared lock
        if available, verifies checksum after copying, registers snapshot only
        after successful verification. Returns an empty Snapshot on failure.
        """
        self._log.info("(create) start: path=%s", event.path)

        path = event.path
        timestamp = monotonic()
        backup_dir = self._backup_dir + "/" + hash_path(path)
        backup_path = backup_dir + "/" + str(timestamp) + ".back"
        makedirs(backup_dir, exist_ok=True)

        _empty = Snapshot(
            original_path=path,
            backup_path="",
            checksum="",
            created_at=timestamp,
            event_type=event.event_type,
        )

        if hasattr(self._path_locker, "acquire_shared"):
            locked_path = self._path_locker.acquire_shared(path)
        else:
            locked_path = self._path_locker.acquire(path)

        try:
            original_checksum = checksum(locked_path)

            if isfile(locked_path):
                copy2(locked_path, backup_path)
            else:
                copytree(locked_path, backup_path)

            self._ignoring_paths[backup_path] = (
                self._ignoring_paths.get(backup_path, 0) + 1
            )

            if checksum(backup_path) != original_checksum:
                self._log.warning("(create) fail: checksum mismatch path=%s", path)
                if isfile(backup_path):
                    Path(backup_path).unlink(missing_ok=True)
                else:
                    rmtree(backup_path, ignore_errors=True)
                return _empty

            snapshot = Snapshot(
                original_path=path,
                backup_path=backup_path,
                checksum=original_checksum,
                created_at=timestamp,
                event_type=event.event_type,
            )

            self._registry.setdefault(path, []).append(snapshot)
            self._raw_registry.setdefault(path, {"processing": False, "snapshots": []})
            self._raw_registry[path]["snapshots"].append(self._to_dict(snapshot))
            self._save()

            self._log.info("(create) done: path=%s backup=%s", path, backup_path)

        finally:
            self._path_locker.release(path)

        return snapshot

    def get(self, path: str, index: int) -> Optional[Snapshot]:
        """
        Returns a validated Snapshot for the given path at the given index.
        Falls back to the latest valid snapshot if index is out of range or
        backup fails validation. Returns None if no valid snapshots exist.
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
        Restores the file system object at the given path to the state captured
        in the snapshot at the given index. Supports both files and directories.
        For files: copy to .vakt.back then atomically replace via os.replace().
        For directories: atomically rename original to .old, copy backup, remove .old.
        Uses tumbler flag for crash recovery. Silently returns if no valid snapshot exists.
        """
        self._log.info("(restore) start: path=%s index=%d", path, index)

        snapshot = self.get(path, index)

        if snapshot is None:
            self._log.warning("(restore) fail: no valid snapshot path=%s", path)
            return

        locked_path = self._path_locker.acquire(path)

        try:
            self._raw_registry[path]["processing"] = True
            self._save()

            if isfile(locked_path):
                tmp_path = path + ".vakt.back"
                copy2(snapshot.backup_path, tmp_path)
                self._ignoring_paths[tmp_path] = (
                    self._ignoring_paths.get(tmp_path, 0) + 1
                )

                if checksum(tmp_path) != snapshot.checksum:
                    self._log.warning("(restore) fail: checksum mismatch path=%s", path)
                    Path(tmp_path).unlink(missing_ok=True)
                    self._raw_registry[path]["processing"] = False
                    self._save()
                    return

                replace(tmp_path, locked_path)
                self._ignoring_paths[locked_path] = (
                    self._ignoring_paths.get(locked_path, 0) + 1
                )

            else:
                old_path = path + ".vakt.old"
                replace(locked_path, old_path)
                self._ignoring_paths[old_path] = (
                    self._ignoring_paths.get(old_path, 0) + 1
                )

                copytree(snapshot.backup_path, path)
                self._ignoring_paths[path] = self._ignoring_paths.get(path, 0) + 1

                if checksum(path) != snapshot.checksum:
                    self._log.warning("(restore) fail: checksum mismatch path=%s", path)
                    rmtree(path, ignore_errors=True)
                    replace(old_path, path)
                    self._raw_registry[path]["processing"] = False
                    self._save()
                    return

                rmtree(old_path, ignore_errors=True)

            self._raw_registry[path]["processing"] = False
            self._save()
            self._log.info("(restore) done: path=%s index=%d", path, index)

        finally:
            self._path_locker.release(path)

    def delete(self, path: str, index: int) -> None:
        """
        Removes the Snapshot at the given index from both registries and
        deletes its physical backup from disk.
        Logs WARNING and returns if path or index does not exist.
        """
        self._log.info("(delete) start: path=%s index=%d", path, index)

        if not self._registry:
            self._log.warning("(delete) skip: registry is empty")
            return

        snapshots = self._registry.get(path)

        if not snapshots:
            self._log.warning("(delete) skip: path not found path=%s", path)
            return

        try:
            real_index = index if index >= 0 else len(snapshots) + index
            snapshot = snapshots[real_index]
        except IndexError:
            self._log.warning(
                "(delete) skip: index out of range path=%s index=%d", path, index
            )
            return

        backup = snapshot.backup_path
        if isfile(backup):
            Path(backup).unlink(missing_ok=True)
        else:
            rmtree(backup, ignore_errors=True)

        self._remove(path, real_index)
        self._log.info("(delete) done: path=%s index=%d", path, real_index)

    def history(self, path: str) -> Sequence[Snapshot]:
        """
        Returns all Snapshots for the given path ordered by created_at ascending.
        Returns an empty sequence if none exist. Returns a shallow copy.
        """
        self._log.info("(history): path=%s", path)
        return self._registry.get(path, []).copy()

    def show(self) -> Mapping[str, Sequence[Snapshot]]:
        """Returns the live internal registry mapping."""
        self._log.info("(show): called")
        return self._registry

    def show_raw(self) -> Mapping[str, dict]:
        """Returns the raw registry as a serialization-friendly mapping."""
        self._log.info("(show_raw): called")
        return self._raw_registry

    def clear(self, path: str) -> None:
        """
        Removes all Snapshots for the given path and deletes their backup
        directory from disk. Logs WARNING if path not found.
        """
        self._log.info("(clear) start: path=%s", path)

        if path not in self._registry:
            self._log.warning("(clear) skip: path not found path=%s", path)
            return

        rmtree(self._backup_dir + "/" + hash_path(path), ignore_errors=True)
        del self._registry[path]
        del self._raw_registry[path]

        self._save()
        self._log.info("(clear) done: path=%s", path)

    def clear_all(self) -> None:
        """
        Removes all Snapshots and deletes all backup directories.
        Logs WARNING if registry is already empty.
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

    def describe(self) -> dict[str, str]:
        return {
            "backup_dir": (
                "str - required. Absolute path to the directory where backup "
                "files will be stored. A .vakt.backups subdirectory is created automatically."
            ),
            "registry_path": (
                "str - required. Absolute path to the JSON registry file. "
                "Parent directories are created automatically. "
                "Errors during reading or parsing propagate to the caller."
            ),
            "path_locker": (
                "BasePathLocker - required. Injected automatically by Bootstrap. "
                "Used to acquire shared or exclusive locks during create and restore."
            ),
            "ignoring_paths": (
                "dict[str, int] - required. Injected automatically by Bootstrap. "
                "Incremented for every path touched during file system operations."
            ),
        }

    def _recover_tumblers(self) -> None:
        """
        Detects and cleans up incomplete create and restore operations from
        previous crash. For incomplete restores of files: removes .vakt.back leftover.
        For incomplete restores of directories: removes incomplete restored directory
        and renames .vakt.old back to original path.
        Processing flag is reset to False after recovery.
        """
        self._log.debug(
            "(_recover_tumblers) start: checking %d paths", len(self._raw_registry)
        )

        for path, data in self._raw_registry.items():
            if data["processing"] is not True:
                continue

            back_path = path + ".vakt.back"
            old_path = path + ".vakt.old"

            if exists(back_path):
                Path(back_path).unlink(missing_ok=True)
                self._log.debug("(_recover_tumblers): removed leftover %s", back_path)

            if exists(old_path):
                if exists(path):
                    rmtree(path, ignore_errors=True)
                replace(old_path, path)
                self._log.debug(
                    "(_recover_tumblers): restored %s from %s", path, old_path
                )

            data["processing"] = False

        self._save()
        self._log.debug("(_recover_tumblers) done")

    def _validate(
        self, path: str, start_index: int, snapshot: Snapshot
    ) -> Optional[Snapshot]:
        """
        Validates snapshots starting from the given index using a while loop.
        Removes invalid snapshots and tries the next latest one.
        Returns None if no valid snapshots remain.
        """
        self._log.debug("(_validate) start: path=%s index=%d", path, start_index)

        index = start_index

        while True:
            snapshots = self._registry.get(path)
            if not snapshots:
                return None

            current = snapshots[index] if index < len(snapshots) else snapshots[-1]
            real_index = index if index < len(snapshots) else len(snapshots) - 1
            backup = current.backup_path

            if not exists(backup):
                self._log.warning("(_validate) fail: missing backup=%s", backup)
            elif checksum(backup) == current.checksum:
                self._log.debug("(_validate) done: path=%s index=%d", path, real_index)
                return current
            else:
                self._log.warning(
                    "(_validate) fail: checksum mismatch backup=%s", backup
                )

            if isfile(backup):
                Path(backup).unlink(missing_ok=True)
            else:
                rmtree(backup, ignore_errors=True)

            self._remove(path, real_index)
            index = -1

    def _remove(self, path: str, index: int) -> None:
        """
        Removes a single snapshot entry at the given index from both
        registries. Removes the path key entirely if no snapshots remain.
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
        Atomically persists the raw registry to disk via write-to-temp-then-replace.
        """
        self._log.debug(
            "(_save) start: persisting %d paths to %s",
            len(self._raw_registry),
            self._registry_path,
        )

        makedirs(self._registry_path.rsplit("/", 1)[0], exist_ok=True)
        tmp_path = self._registry_path + ".tmp"

        with open(tmp_path, "w", encoding="utf-8") as file:
            dump(self._raw_registry, file, indent=4)

        replace(tmp_path, self._registry_path)
        self._log.debug("(_save) done: written to %s", self._registry_path)

    def _load(self) -> None:
        """
        Loads snapshots metadata from the JSON registry on disk.
        Silently skips if the file does not exist. Errors during reading
        or parsing propagate to the caller intentionally.
        """
        if not exists(self._registry_path):
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
        saj_operations.log located next to the registry file.
        """
        log_path = self._registry_path.rsplit("/", 1)[0] + "/" + self._LOG_FILENAME
        makedirs(log_path.rsplit("/", 1)[0], exist_ok=True)
        logger = getLogger(__name__)
        logger.setLevel(DEBUG)

        if not logger.handlers:
            handler = FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
        return logger

    @staticmethod
    def _to_dict(snapshot: Snapshot) -> dict:
        """Converts a Snapshot domain object to a raw dict for JSON serialization."""
        return {
            "original_path": snapshot.original_path,
            "backup_path": snapshot.backup_path,
            "checksum": snapshot.checksum,
            "created_at": snapshot.created_at,
            "event_type": snapshot.event_type,
            "description": snapshot.description,
        }
