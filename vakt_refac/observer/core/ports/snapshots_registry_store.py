from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Optional

from ..domain import Snapshot


class BaseSnapshotsRegistryStore(ABC):
    """
    Abstract base class for snapshots registry and storage.

    SnapshotsRegistryStore is responsible for two things at once:
        1. Registry - stores and manages Snapshot metadata objects
            grouped by original path.
        2. Store - physically stores and manages actual backup files
            and is responsible for their lifecycle including creation,
            restoration and deletion.

    This design is intentional - separating registry and store would
    create tight coupling between Backuper, RollBacker and storage
    implementations. By combining them, handlers only need to interact
    with one object without knowing where or how backups are stored.

    Snapshots are grouped by original path and ordered by created date ascending:
        {"/etc/passwd": [snapshot_0, snapshot_1, snapshot_2]}

    Snapshots are accessed by index (snapshot_N) where N is the position
    in the history sequence. The latest snapshot is always at index -1.

    Persistence Requirements:
        All implementations MUST persist the registry after every modification
        (create, delete, clear, clear_all) to prevent metadata loss on crash.
        This is not optional - it is a critical requirement for data integrity.
        If the daemon crashes between a backup creation and registry persistence,
        the backup file will exist on storage but will not be tracked by the registry.
        This leads to orphaned backup files that cannot be managed or restored.

        Recommended approach:
            - Persist registry immediately after every modification.
            - Use atomic write operations where possible to avoid corrupted
                registry files on crash during write.

        Graceful shutdown is handled by upper layer objects like Dispatcher.
        But it does not mean handlers do not require to respect graceful
        shutdown - some handlers may require it.

    Implementations Example:
        - DiskSnapshotsRegistryStore: stores backups on disk, registry in JSON.
        - S3SnapshotsRegistryStore: stores backups in S3, registry in JSON.

    Notes:
        - create(), get(), restore() are used by handlers in Dispatcher layer.
        - delete(), clear(), clear_all(), show() are intended only for external
            management utilities and are not used by the daemon itself.
        - By default does not require thread-safety as it is only used by handlers
            that operate in the Dispatcher layer.
    """

    @abstractmethod
    def create(self, path: str) -> Snapshot:
        """
        Creates a physical backup of the file system object at the given path,
        adds it to the registry and returns the created Snapshot.
        Implementations must persist the registry immediately after creation.
        """
        ...

    @abstractmethod
    def get(self, path: str, index: int) -> Optional[Snapshot]:
        """
        Returns a single Snapshot for the given path at the given index.
        Index follows standard Python sequence indexing,
        so -1 returns the latest snapshot.
        If provided index is out of range returns the latest snapshot
        without raising any exception.
        Returns None if no snapshots exist for the given path.
        """
        ...

    @abstractmethod
    def restore(self, path: str, index: int) -> None:
        """
        Restores the file system object at the given path to the state
        captured in the snapshot at the given index.
        If provided index is out of range restores the latest snapshot
        without raising any exception.
        Silently ignores if no snapshots exist for the given path.
        """
        ...

    @abstractmethod
    def history(self, path: str) -> Sequence[Snapshot]:
        """
        Returns all Snapshots for the given path ordered by created date ascending.
        Returns empty sequence if no snapshots exist for the given path.
        """
        ...

    @abstractmethod
    def show(self) -> Mapping[str, Sequence[Snapshot]]:
        """
        Returns the whole registry mapping that contains all Snapshot metadata.
        Intended only for external management utilities.
        """
        ...

    @abstractmethod
    def delete(self, path: str, index: int) -> None:
        """
        Removes a Snapshot from the registry at the given index and
        deletes the actual backup file from storage.
        Intended only for external management utilities.
        Silently ignores if path or index does not exist.
        Implementations must persist the registry immediately after deletion.
        """
        ...

    @abstractmethod
    def clear(self, path: str) -> None:
        """
        Removes all Snapshots for the given path from the registry
        and deletes all actual backup files for that path from storage.
        Intended only for external management utilities.
        Silently ignores if no Snapshots exist for the given path.
        Implementations must persist the registry immediately after clearing.
        """
        ...

    @abstractmethod
    def clear_all(self) -> None:
        """
        Removes all Snapshots from the registry and deletes all actual
        backup files from storage.
        Intended only for external management utilities.
        Silently ignores if registry is already empty.
        Implementations must persist the registry immediately after clearing.
        """
        ...
