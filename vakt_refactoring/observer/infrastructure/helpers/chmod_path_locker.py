from __future__ import annotations

from collections.abc import Sequence
from json import dump, load
from os import chmod, environ, replace, stat
from pathlib import Path
from stat import S_IMODE
from sys import _getframe
from typing import Union

from ...core import BasePathLocker, ToolKit


class ChmodPathLocker(BasePathLocker):
    """
    Implementation of BasePathLocker that supports multiple locking
    and provides exclusive and shared locking for file system objects by
    renaming them to .vakt.lock suffixed path and restricting permissions
    via os.chmod().

    Why os.chmod() instead of fcntl.flock():
        fcntl.flock() provides advisory locking, it only blocks processes
        that explicity check the lock. Common system tools like: cp, mv,
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

    How is robust protection and guaranteed restoration to
    original privileges ensured:
        The lock mechanism guarantees crash safety by writing original permission
        to persistent registry before modifying the filesystem object privileges.
        The registry acts as a transactional log: if the process dies before
        releasing the lock, the next startup reconciles the log against actual
        disk state and restores every stale object to its original name and
        privileges. No external cleanup is required, the guarantee is built into the design.
        Also that is the answer for why i renaming it with .vakt.lock suffix (to mark them).

    Locking modes:
        - acquire():        Exclusive lock that sets permission to 000.
                                All processes are blocked from accessing the object
                                except the superuser (root).
        - acquire_shared(): Shared lock that sets permission to 444.
                                All processes can read but can't modify object.
                                Intented for SnapshotsRegistryStore restore/create
                                operations where reading must remain possible.

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

    Specific Difference from other Implementations:
        Unlike typical PathLocker implementations that only synchronize access,
        ChmodPathLocker actively modifies file system permissions (chmod) and
        renames objects. These modifications are observable as file system events.
        Without mitigation, the Watcher would capture them and the Dispatcher
        would process them as external changes - creating noise and potentially
        incorrect state transitions.

        To prevent this, ChmodPathLocker must inform the Dispatcher to temporarily
        ignore the affected paths. However, due to architectural layering,
        ChmodPathLocker has no direct access to the ignoring_paths dict: it is
        instantiated as a helper component, not as a handler, and therefore does
        not receive ToolKit directly.

        As a pragmatic solution, ChmodPathLocker uses sys._getframe() to walk up
        the call stack and locate the first ToolKit instance in the local variables
        of any frame. This is typically the ToolKit owned by the handler that
        invoked the lock. Once found, the suppress counter in ignoring_paths is
        incremented for each affected path, ensuring the Dispatcher discards
        self-generated events.

        Design rationale: This approach avoids refactoring the core interface,
        keeps the ignoring mechanism transparent, and localizes stack inspection
        to where it is strictly necessary.

    Notes:
        - replace() is atomic at the kernel level. A directory of
            any size is replaced in O(1) without copying its contents.
        - All methods that modifies or touchs a file system object automatically
            informs Dispatcher about it using self._register_ignore() method.
    """

    _DEFAULT_VAULT = "/var/lib/.vakt"
    _REGISTRY_FILENAME = "pathlock_registry.json"

    def __init__(self) -> None:
        """
        Initializes the instance. If the environment variable is not set,
        falls back to the default vault path for loading and saving the
        persistent registry. The registry is loaded only if the file exists
        and contains a valid JSON array of locked path entries.
        """
        vault = environ.get("VAKT_SANCTUM", self._DEFAULT_VAULT)
        self._registry_path: Path = Path(vault) / self._REGISTRY_FILENAME
        self._registry: dict[str, int] = {}
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
        If path is not found in registry or original_path.vakt.lock object does not exists,
        it means its already restored to original state.
        After recovery the updated registry persists immediately.
        Silently ignores if received path is not exist.
        """
        locked_path = Path(path + ".vakt.lock")
        if not self._registry or not locked_path.exists():
            return

        original_privileges = self._registry.get(path, -1)

        if original_privileges != -1:
            chmod(locked_path, original_privileges)
            replace(locked_path, path)
            self._register_ignore([locked_path, path])

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
        """
        original_path = Path(path)
        locked_path = original_path.with_suffix(".vakt.lock")
        new_privileges = 0o444 if shared else 0o000

        if not original_path.exists():
            if locked_path.exists():
                chmod(locked_path, new_privileges)
                self._register_ignore([locked_path])
            return str(locked_path)

        original_privileges = S_IMODE(stat(path).st_mode)
        self._registry[path] = original_privileges
        self._save()

        replace(original_path, locked_path)
        chmod(locked_path, new_privileges)

        self._register_ignore([locked_path, original_path])

        return str(locked_path)

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
            locked_path = Path(original_path + ".vakt.lock")

            if locked_path.exists():
                chmod(locked_path, original_privileges)
                replace(locked_path, original_path)
                self._register_ignore([locked_path, original_path])

        self._registry.clear()
        self._save()

    def _save(self) -> None:
        """
        Automatically persists the registry to the JSON file on disk.

        Writes to a temporary file first then renames it over the target
        file via os.replace(). On the same filesystem os.replace() is
        atomic at the kernel level - if the process crashes during write
        the original registry file remains intact.
        """
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._registry_path.with_suffix(".tmp")

        with open(tmp_path, "w", encoding="utf-8") as file:
            dump(self._registry, file, indent=4)

        replace(tmp_path, self._registry_path)

    def _load(self) -> None:
        """
        Loads locked path entries from the Json registry file if it exists.
        If the file is missing, loading is skipped silently. However, if the
        file is present, it must be well-formed and not corrupted.
        This is not advisory - it is a strict requirement for
        critical data integrity.
        """
        if not self._registry_path.exists():
            return

        with open(self._registry_path, encoding="utf-8") as file:
            self._registry = load(file)

    def _register_ignore(self, paths: Sequence[Union[str, Path]]) -> None:
        """
        Walks the call stack to locate the first ToolKit instance in local
        variables of any frame (typically owned by the handler that invoked
        the lock) and increments the suppress counter in ignoring_paths
        for each affected path by one.

        Each call accumulates independently: if the same path is registered
        multiple times across separate operations, Dispatcher will suppress
        exactly that many incoming events for it, preventing under-ignoring
        when a single handler performs several modifications on the same object.

        Silently does nothing if no object with ignoring_paths is found in
        the call stack.
        """
        frame = _getframe(1)

        while frame:
            for obj in frame.f_locals.values():
                if isinstance(obj, ToolKit):
                    for path in paths:
                        str_path = str(path)
                        obj.ignoring_paths[str_path] = (
                            obj.ignoring_paths.get(str_path, 0) + 1
                        )
                    return
            frame = frame.f_back
