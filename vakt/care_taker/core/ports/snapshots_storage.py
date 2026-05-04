from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..domain import Snapshot


class BaseSnapshotsStorage(ABC):
    """
    Abstract base class for snapshots registry storage.

    SnapshotsStorage is responsible for storing and managing
    Snapshot metadata objects in memory and persisting them to disk.
    It acts as a registry - it does not store the actual backup files,
    only the Snapshot domain objects that describes them.
    Actual backup files are stored on a disk at Snapshot.backup_path.

    Snapshots are grouped by original path and ordered by created date ascending:
        {"/etc/passwd": [snapshot_0, snapshot_1, snapshot_2]}

    Snapshots are accessed by index (snapshot_N) where N is the position
    in the history sequence, The latest snapshot is always at index -1.

    Persistence:
        - Storage persists registry to disk automatically on every add()
            to prevent metadata loss on crash.
        - If the daemon crashes, backup files remain on disk at their
            backup_path and registry can be recovered or rebuilt.
        - Graceful shutdown is handled by upper layer objects like Dispatcher
            to avoid crash while modifying registry file. Storage only ensures that
            every add() is persisted immediately. But it not means all handlers
            does not require to respect graceful shutdown, cause some handlers may
            require respecting graceful shutdown.

    Implementations Example:
        - DiskSnapshotsStorage: Uses when Backuper stores snapshots in disk.
        - S3SnapshotsStorage: Uses when Backuper stores in server or cloud.

    Notes:
        - delete() is not used by the daemon itself. It is intended
            only for external management utilities or interfaces
            that allow the user to manage snapshots without
            damaging registry metadata itself, manually deleting
            or doing any other operates with snapshots using
            not supported programs.
        - Storage does not contain any business logic,
            It is pure registry of Snapshot objects.
        - Storage does not require thread-safe, cause base implementation
            of storage does not used in shared memory threads or any other
            objects, it only used by Backuper and Rollbacker
            like objects in Dispatcher layer.
    """

    @abstractmethod
    def add(self, path: str, snapshot: Snapshot) -> None:
        """
        Adds a Snapshot to the registry under the given path
        and persists the updated registry to disk immediately.
        Not requires to respect shutdown gracefully event cause it is
        responsibility of upper layer objects.
        """
        ...

    @abstractmethod
    def get(self, path: str, index: int) -> Snapshot:
        """
        Returns a single Snapshot for given path at the given index.
        Index follows standard Python sequence indexing,
        so -1 returns latest snapshot. Also if provided index is higher
        than length of snapshots sequence, implementations must need to
        returns latest snapshot without raising any exception to avoid
        shutting down program cause of stupid guard:
            (Thats not best practice for programs like this cause they
            should not be susceptible to such small errors or trifles).
        """
        ...

    @abstractmethod
    def history(self, path: str) -> Sequence[Snapshot]:
        """
        Returns all Snapshots for the given path ordered
        by created date ascending. It's required for objects that need
        to work with all snapshots to enable client management with snapshots.
        """
        ...

    @abstractmethod
    def delete(self, path: str, index: int) -> None:
        """
        Removes a Snapshot from registry at the given index.
        Intended only for external management utilities.
        The implementations decides remove actual backup from path
        with snapshot metadata in registry or not, its not required option
        in base abstract class.
        Also like get this method should not raise any exceptions
        if objects under provided index is not exist. It need to silently
        ignore and does nothing.
        """
        ...

    @abstractmethod
    def clear(self, path: str) -> None:
        """
        Removes all Snapshots from the SnapshotsStorage for the given path.
        Intended only for external management utilities.
        Should silently ignore if no Snapshots exist for the given path.
        Ensure that implementation removes all metadata of all Snapshots
        for the given path.
        """
        ...

    @abstractmethod
    def clear_all(self) -> None:
        """
        Removes all Snapshots of all paths in the SnapshotsStorage.
        Intended only for external management utilities.
        Should silently ignore if Snapshots storage is already empty/
        Ensure that implementation removes all metadata from registry too.
        """
        ...
