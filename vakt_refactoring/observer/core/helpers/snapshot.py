from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..domain import EventType


@dataclass(slots=True, frozen=True)
class Snapshot:
    """
    An Immutable domain-layer object representing a single backup of
    a file system object.

    SnapshotsRegistryStore is responsible for the creation, storage,
    and lifecycle management of snapshots. Snapshots themselves are owned
    by this store. External components such as Backuper and RollBacker
    interact with the store to create or remove snapshots.


    Snapshot object stores all information needed to verify integrity and restore
    the file system object to its previous state via RollBacker like components.
    All Snapshots are stored in SnapshotsRegistryStore grouped by original
    object absolute path, allowing full history access per file system object.

    Attributes:
        - original_path: Absolute path of file system object that was backed up.
                            Used by a specific roll backing components to know where
                            to restore the object. Also used as a key in registry.

        - backup_path:   Absolute path were the backup copy is stored.
                            Also used by a specific components to know where is
                            the backup.
        - checksum:      SHA-256 hash of backup file system object.
        - timestamp:     Monotonic timestamp of when this snapshot was created.
                            Used for ordering a snapshots in history.
        - event_type:    The type of file system event that triggered this backup.
        - description:   Optional human-readable description of the snapshot.
                            Can be set by the external objects or generated automatically.

    Notes:
        - Snapshot is frozen because it describes a past state that
            must never be modified after creation.
        - Snapshot does not contain restore logic. Restoration
            is handled by SnapshotsRegistryStore which receives path and index.
        - Snapshot is intended to be used by external management utilities
            that need full metadata about a backup. Handlers do not need
            to access Snapshot directly as SnapshotsRegistryStore handles
            all storage and restoration operations for them.
        - This implementation is not final and may be revised in future releases.
    """

    original_path: str
    backup_path: str
    checksum: str
    created_at: float
    event_type: EventType
    description: Optional[str] = None
