from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .event import EventType


@dataclass(frozen=True, slots=True)
class Snapshot:
    """
    An Immutable domain-layer object representing a single backup of
    a file system object.

    A Snapshot is creates by a Backuper after file system change is detected and
    only if one of the upper layer objects said to do a backup (instruction, client and etc..).
    it stores all information needed to verify integrity and restore the file
    to its previous state via RollBacker.

    All Snapshots are stored in SnapshotsStorage grouped by original object absolute path,
    allowing full history access per file system object.

    Attributes:
        - original_path: Absolute path of the file that was backed up.
                            Used by a RollBacker to know where to restore the object.
                            Also used as the key in SnapshotsStorage.
        - backup_path:   Absolute path were the backup copy is stored.
        - checksum:      SHA-256 hash of the backup file.
        - created_at:    Monotonic timestamp of when this snapshot was created.
                            Used for ordering a snapshots in history.
        - event_type:    The type of file system event that triggered this backup.
        - description:   Optional human-readable description of the snapshot.
                            Can be set by the user or generated automatically.

    Notes:
        - Snapshot is frozen because it describes a past state that
            must be never modified after creation.
        - Snapshot does not contain restore logic. All restoration
            is handled by RollBacker which receives the Snapshot as input.
        - SnapshotStorage groups by original path:
            {"/etc/passwd": [snapshot_1, snapshot_2, snapshot_3]}
            The sequence is ordered by created at ascending.
    """

    original_path: str
    backup_path: str
    checksum: str
    created_at: float
    event_type: EventType
    description: Optional[str] = None
