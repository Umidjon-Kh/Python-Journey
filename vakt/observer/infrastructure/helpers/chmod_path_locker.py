from __future__ import annotations

from json import dump, load
from os import chmod, environ, makedirs, replace, stat
from os.path import exists
from stat import S_IMODE
from typing import Any

from ...core import BasePathLocker


class ChmodPathLocker(BasePathLocker):
    """
    Implementation of BasePathLocker that supports multiple locking
    and provides exclusive and shared locking for file system objects by
    renaming them to .vak.lock suffixed path and restricting permissions
    via os.chmod().

    Why os.chmod() instead of fcntl.flock():
        fcntl.flock() provides advisory locking, it only blocks processes
        that explicitly check the lock. Common system tools like: cp, mv,
        vim, rsync, rename and most editors ignore it completely.
        To enforce real access restrictions against any external process
        (including uncooperative or suspicious ones), I use os.chmod()
        which changes file system permissions. This turns the lock into a
        mandatory access control: the kernel will deny all read/write/execute
        attempts regardless of whether a caller cooperates. Root remains
        the only exception, as the kernel never blocks superuser privileges.
        This behaviour is intentional for components that must block untrusted
        (suspect) processes while still allowing system-level recovery
        by root if it necessary.

    How is robust protection and guaranted restoration to
    original privileges ensured:
        The lock mechanism guarantees crash safety by writing original permission
        to persistent registry before modifying the filesystem object privileges.
        The registry acts as a transactional log: if the process dies before
        releasing the lock, the next startup reconciles the log against actual
        disk state and restores every stale object to its original name and
        privileges. No external cleanup is required, the guarantee is built into
        the design. Also that is the answer for why i renaming it with
        .vakt.lock suffix (to mark them as locked).

    Locking modes:
        - acquire():        Exclusive lock that sets permissions to 000.
                                All processes are blocked from accessing the object
                                except the superuser (root).
        - acquire_shared(): Shared lock that sets permission to 444.
                                All processes can read but can't modify object.
                                Intended for SnapshotsRegistryStore create operation
                                where reading must remain possible.

    Environment Variable (VAKT_SANCTUM):
        VAKT_SANCTUM - defines the root directory where the daemon stores
        persistent runtime data that must be protected  from external processes,
        including untrusted or suspicious ones. This variable is not specific
        to any single component (such as PathLock); it is shared convention for all
        subsystems that require a secure, stable location for critical data:
            (e.g., lock registries, snapshot metadata, instruction caches)
        The ChmodPathLocker implementation uses VAKT_SANCTUM as a concrete
        demonstration: if you are implementing a component that needs to preserve
        state across restarts while preventing accidental or malicious modification
        by external agents, you are strongly encouraged to respect VAKT_SANCTUM and
        fall back to a system-appropriate default (e.g., "/var/lib/.vakt").
        This provides a single, predictable control point for operators and ensures
        that all sensitive data resides within a trusted directory hierarchy.

    Notes:
        - replace() is atomic at the kernel level. A directory of
            any size is replaced in O(1) without copying its contents.
        - All methods that modifies or affect a file system object automatically
            inform the Dispatcher about it by incrementing the path suppression by
            one directly via self._ignoring_paths, provided from the configuration
            dictionary on initialization.
    """

    _DEFAULT_VAULT = "/var/lib/vakt/"
    _REGISTRY_FILENAME = "pathlock_registry.json"

    def __init__(self, config: dict[str, Any]) -> None:
        """
        Initializes the instance. If environment variable is not set,
        falls back to the default vault path for loading and saving
        the persistent registry. The registry is loaded only if the file
        exists and contains a valid JSON array of locked entries.Any errors raised
        during file reading or parsing are intentionally not caught and
        propagate to the caller - an invalid registry file at startup is
        a configuration error that must be visible immediately.
        """
        vault = environ.get("VAKT_SANCTUM", self._DEFAULT_VAULT)
        self._registry_path: str = vault + self._REGISTRY_FILENAME
        self._registry: dict[str, int] = {}
        self._ignoring_paths: dict[str, int] = config["ignoring_paths"]
        self._load()
        self._recover_all()

    def acquire(self, path: str) -> str:
        """
        Acquires an exclusive lock on the object at the given path and
        returns the path to the locked object as a string.

        Renames the object to original_path.vakt.lock and fully blocks
        object with zero privileges to all type of users, that prevents
        all external processes from reading and writing.
        Persists the lock state to the registry before any file system
        modification so that a crash mid-operation can be recovered.
        Silently skips if the path is not exists. If paths exists but
        already locked, it silently changes privileges to new one.
        """
        return self._lock(path, shared=False)

    def acquire_shared(self, path: str) -> str:
        """
        Acquires a shared lock on the object at the given path and
        returns the path to the locked object as a string.

        Renames the object to original_path.vakt.lock and apples only read
        privileges to all type of users, that prevents writing from
        external processes. Intented for SnapshotsRegistryStore and create
        operations where read access must remain possible during processing.
        Also uses same method self._lock() but with shared=True argument
        as self.acquire() and returns a renamed locked path.
        """
        return self._lock(path, shared=True)

    def release(self, path: str) -> None:
        """
        Releases the lock on the object at the given path.

        Recovers a concrete object recorded in the registry to the original state.
        If path is not found in registry or original_path.vakt.lock object does
        not exists, it means its already restored to original state. After recovery
        the updated registry persists immediately. Silently ignores if received
        path is not exist. Also informs the Dispatcher about affected paths
        by incrementing paths supression counters by one.
        """
        locked_path = path + ".vakt.lock"
        if not self._registry or not exists(locked_path):
            return

        original_privileges = self._registry.get(path, -1)

        if original_privileges != -1:
            chmod(locked_path, original_privileges)
            replace(locked_path, path)
            self._ignoring_paths[locked_path] = (
                self._ignoring_paths.get(locked_path, 0) + 1
            )
            self._ignoring_paths[path] = self._ignoring_paths.get(path, 0) + 1

        self._registry.pop(path, None)
        self._save()

    def _lock(self, path: str, shared: bool) -> str:
        """
        Core locking logic shared by acquire() and acquire_shared().

        Persists the entry first, then renames and changes privileges to concrete
        state depended on shared or not. Even if daemon crashes between rename or
        changing privileges, a recoverable state of path is already persisted
        in registry. If received path is already exists in registry, it silently
        changes privileges of locked path to new privileges.
        After all this returns renamed locked path as a string.
        Also informs the Dispatcher about affected paths by incrementing paths
        supression counters by one.
        """
        locked_path = path + ".vakt.lock"
        new_privileges = 0o444 if shared else 0o000

        if not exists(path):
            if exists(locked_path):
                chmod(locked_path, new_privileges)
                self._ignoring_paths[locked_path] = (
                    self._ignoring_paths.get(locked_path, 0) + 1
                )
            return locked_path

        original_privileges = S_IMODE(stat(path).st_mode)
        self._registry[path] = original_privileges
        self._save()

        replace(path, locked_path)
        chmod(locked_path, new_privileges)

        self._ignoring_paths[locked_path] = self._ignoring_paths.get(locked_path, 0) + 1
        self._ignoring_paths[path] = self._ignoring_paths.get(path, 0) + 1

        return locked_path

    def _recover_all(self) -> None:
        """
        Restores all objects recorded in the registry to their original state.

        Called once after initializing and loading all locked path entries.
        Iterates the registry and for each locked path entry:
            - If the .vakt.lock object exists: restores privileges and
                renames it back to original.
            - If it does not exist: the object was already restored
                so the stale entry is simply removes.

        If registry is empty silently ignores and does nothing.
        After recovery the registry is persisted to reflect the clean state.
        """
        if not self._registry:
            return

        for original_path, original_privileges in self._registry.items():
            locked_path = original_path + ".vakt.lock"

            if exists(locked_path):
                chmod(locked_path, original_privileges)
                replace(locked_path, original_path)
                self._ignoring_paths[locked_path] = (
                    self._ignoring_paths.get(locked_path, 0) + 1
                )
                self._ignoring_paths[original_path] = (
                    self._ignoring_paths.get(original_path, 0) + 1
                )

        self._registry.clear()
        self._save()

    def _load(self) -> None:
        """
        Loads locked path entries from the JSON registry file if it exists.
        If the file is missing, loading is skipped silently. However, if the
        file is present, it must be well-formed and not corrupted.
        This is not advisory - it is a strict requirement for
        critical data integrity.
        """
        if not exists(self._registry_path):
            return

        with open(self._registry_path, encoding="utf-8") as file:
            self._registry = load(file)

    def _save(self) -> None:
        """
        Automatically persists the registry to the JSON file on disk.

        Writes to a temporary file first then renames it over the target
        file via os.replace(). On the same filesystem os.replace() is
        atomic at the kernel level - if the process crashes during write
        the original registry file remains intact.
        """
        makedirs(self._registry_path.rsplit("/", maxsplit=1)[0], exist_ok=True)
        tmp_path = self._registry_path + ".tmp"

        with open(tmp_path, "w", encoding="utf-8") as file:
            dump(self._registry, file, indent=4)

        replace(tmp_path, self._registry_path)

    def describe(self) -> dict[str, str]:
        return {
            "ignoring_paths": (
                "dict[str, int] - required. Injected automatically by Bootstrap. "
                "No additional configuration is required for this implementation."
            ),
        }
