from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from typing import Any, Optional

from ...domain import Snapshot
from ..main.port_protocol import PortProtocol


class BaseSnapshotsRegistryStore(PortProtocol):
    """
    Abstract base class for all snapshot registry and storage implementations.

    SnapshotsRegistryStore is a helper infrastructure component designed to give
    handlers the ability to create and restore backups of file system objects.
    It is not a core pipeline element and does not participate in event processing
    directly.

    Its existence decouples handlers like BackupInvoker and RestoreInvoker from
    each other's implementation details and from the specifics that play a critical
    role in real-world backup operations — such as how BackupInvoker created the
    backup, where it is stored, under what name, whether it was encrypted, whether
    it was created correctly or is corrupted, or whether a backup even exists despite
    BackupInvoker having appended its flag to ctx.performed. In short,
    SnapshotsRegistryStore plays a key role for this class of handlers, simplifying
    their work and providing a single API through which different handlers can
    communicate — a contract in the form of an object.

    SnapshotsRegistryStore is simultaneously responsible for three things:
        1. Registering and managing Snapshot metadata objects, stored in groups
            per concrete file system object.
        2. Storing and managing the physical backup files themselves, and owning
            their full lifecycle — including creation, restoration, and deletion.
        3. Thread-safety — both internal handlers and external management objects
            operating under client commands must be able to work concurrently
            without race conditions.

    Backup Creation Protocol and sample() template:
        SnapshotsRegistryStore exposes a sample() method — similar to
        InstructionRegistry — that returns a skeleton dictionary for callers to
        fill with snapshot-specific fields before passing to create(). However,
        not every object that calls create() will have the specific implementation
        in its Configure requirements, leaving the implementation choice to the client.
        To avoid invalid construction and runtime crashes, the implementation itself
        must fill in any fields specific to its own storage strategy that the caller
        cannot be expected to know.

    Storage and History Protocol:
        All implementations must store snapshots in groups keyed by the original
        file system object. This is mandatory so that clients and other components
        are not confused — restore(), history(), clear(), and delete() all accept
        path regardless of implementation. Whether the implementation stores groups
        under the literal original path, a hash of it, or something else is an internal
        detail. The path must always resolve to the correct group. History returned by
        history() must always be ordered from oldest to newest, regardless of
        internal storage order.

    Integrity and Safety Protocol:
        All implementations MUST persist the registry after every modification
        (create, delete, clear, clear_all) to avoid metadata loss on crash. This is
        not optional — it is a critical requirement for data integrity. If the server
        crashes during backup creation and registry persistence, the backup file may
        exist on disk while the registry no longer tracks it, leading to orphaned
        backup objects that cannot be managed or restored.

        Furthermore, all implementations must verify that a backup was successfully
        created or restored by comparing checksums to detect corruption. Yes, it is
        expensive — but it is safe, mfks.

        When working with physical file system objects, implementations must mark all
        intermediate objects with the appropriate suffix — .vakt.bckp, .vakt.tmp, or
        .vakt.old — depending on the task and the semantics of the object. This gives
        users and other components the ability to manually recover or remove leftover
        and failed objects.

        Recommended approach:
            - Verify backup integrity at every move via checksum comparison.
            - Prefer atomic operations (rename or move) wherever possible.
            - Register in the registry before modifying or moving the physical backup,
                so that snapshot.checksum can be compared against the post-move checksum.
            - Use atomic writes with .vakt.tmp in the registry store itself.
            - Validate group integrity on every method call that contacts a group —
                check for existence and remove from the registry if the backup is gone.

    Why sample():
        Unlike InstructionRegistry, SnapshotsRegistryStore is used by both
        internal handlers and external management tools. External tools have no
        knowledge of implementation-specific fields such as compression settings,
        encryption config, or storage tier. Internal handlers that do not declare
        the specific implementation in their Configure requirements — which is
        intentional, as the implementation choice belongs to the client — also cannot
        know those fields. sample() provides a discoverable contract: callers fill in
        what they know, and the implementation fills in the rest.

    Why target: Any instead of a concrete type:
        Different implementations identify snapshots differently — by integer index,
        ISO timestamp, checksum hash, or UUID. Callers discover the expected type
        from the results of show() or history(). Regardless of implementation, if
        target is invalid or the specified target is not found, the implementation
        must fall back to the latest valid snapshot in the group by default.

    Example implementations:
        - LocalSnapshotsRegistryStore: stores backups on disk, registry in JSON.
        - S3SnapshotsRegistryStore: stores backups in S3, registry in a remote store.

    Notes:
        - create(), delete(), restore() may be used by internal objects — primarily
            handlers, though any object may request them through its Configure
            requirements.
        - clear(), clear_all(), show() are intended only for external management
            objects or utilities.
        - create() method returns None if Not-Specific required keys are invalid
            or missing. That serves as an expression of snapshot creation is failed.
        - Must never propagate exceptions to the caller. All errors must be caught
            and handled internally.
    """

    @abstractmethod
    def create(self, raw_snapshot: dict) -> Optional[Snapshot]:
        """
        Constructs, stores, and returns a Snapshot from a filled sample dictionary.

        The implementation validates and builds the Snapshot internally, filling in
        any implementation-specific fields the caller could not provide. Persists the
        registry after creation. Returns None if required keys are missing or
        invalid. That serves as an expression of snapshot creation is failed.
        Use sample() to discover the expected structure before calling.
        """
        ...

    @abstractmethod
    def restore(self, path: str, target: Any) -> bool:
        """
        Restores the file system object at path to the state captured by target.

        If target is invalid or not found, falls back to the latest snapshot in the
        group. Verifies integrity via checksum before and after restoration.
        Marks intermediate objects with .vakt.tmp or .vakt.old suffixes.
        Returns False if path has no snapshots or failed to restore, Otherwise
        returns True if restore operation is succesfully completed.
        """
        ...

    @abstractmethod
    def delete(self, path: str, target: Any) -> bool:
        """
        Removes the snapshot identified by target from the group at path.

        If target is invalid or not found, removes the latest snapshot in the group.
        Removes the physical backup file and persists the registry after deletion.
        Returns False if the group does not exist or failed to remove, Otherwise
        returns True if remove operation is succesfully completed.
        Intended for both internal components and external management tools.
        """
        ...

    @abstractmethod
    def clear(self, path: str) -> None:
        """
        Removes all snapshots and their physical backups for the group at path.

        Persists the registry after clearing. Silently ignores if the group does
        not exist. Intended only for external management tools.
        """
        ...

    @abstractmethod
    def clear_all(self) -> None:
        """
        Removes all snapshots and physical backups across all groups.

        Persists the registry after clearing. Intended only for external
        management tools.
        """
        ...

    @abstractmethod
    def history(self, path: str) -> Sequence[Snapshot]:
        """
        Returns all snapshots for the group at path, ordered oldest to newest.

        Validates group integrity before returning — removes entries from the
        registry if their physical backup no longer exists on disk. Returns an
        empty sequence if the group does not exist.
        """
        ...

    @abstractmethod
    def show(self) -> Sequence[dict]:
        """
        Returns all snapshot metadata across all groups as raw dictionaries.

        Each dict reflects the same structure as sample(). Intended only for
        external management tools such as a RegistryManager presenting the full
        registry to the client.
        """
        ...

    @abstractmethod
    def sample(self) -> dict:
        """
        Returns a skeleton dictionary showing the expected structure for create().

        Includes all Snapshot fields and any implementation-specific parameters
        (e.g., compression, encryption, storage tier) with their expected types and
        whether they are required or optional. Call this before create() to discover
        what keys the implementation expects.
        """
        ...
