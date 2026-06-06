from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .event import EventType


@dataclass(slots=True, frozen=True)
class Snapshot:
    """
    An immutable helper-layer object representing a single backup of a file system object.

    Snapshot is a metadata container that holds all information about one specific
    physical backup. Its primary role is to serve as a verifiable identity record —
    enabling integrity checks and providing the location and context needed to
    restore a file system object to a past state.

    Snapshot objects are created and managed exclusively by SnapshotsRegistryStore
    implementations. SnapshotsRegistryStore is responsible for the full lifecycle
    of snapshots: storage, grouping, querying, and restoration. All snapshots
    belonging to the same file system object are kept together as a group, making
    it straightforward to retrieve the complete backup history of any specific object.
    All components that need to work with snapshots interact only with the
    SnapshotsRegistryStore implementation — never with Snapshot directly.

    Snapshot objects surface to the processing layer through Invokers such as
    BackupInvoker and RestoreInvoker, which call create() and restore() on the
    SnapshotsRegistryStore implementation. BackupInvoker places the resulting
    Snapshot into EventContext.metadata so that other handlers in the same
    processing cycle can access it without coupling to a specific field on EventContext.

    Attributes:
        - original_path: Absolute path to the file system object that was backed up.
                          Carried for informational purposes — most components already
                          know which paths they operate on, and external management
                          sees objects grouped by path. Useful as supplementary
                          context when inspecting a Snapshot in isolation.
        - backup_path:   Absolute path to the location where the physical backup
                          is stored. Used to locate and access the backup on disk.
        - checksum:      An implementation-defined integrity hash of the backed-up
                          content. Used to verify that the physical backup has not
                          been corrupted or tampered with since it was created.
                          The specific hashing algorithm is determined by the
                          SnapshotsRegistryStore implementation.
        - timestamp:     Monotonic timestamp of when this snapshot was created.
                          Used for ordering snapshot history and determining
                          relative age between snapshots of the same object.
        - event_type:    The type of file system event that triggered this backup.
                          Optional — populated by handlers during backup creation.
                          External objects cannot provide this field since they have
                          no awareness of internal EventType values.
        - description:   An optional human-readable description of the snapshot.
                          Can be provided by external management components or
                          generated automatically.

    Notes:
        - Snapshot is frozen because it describes a past state that must never be
            modified after creation. Any change to a backup's metadata would
            invalidate its role as a trustworthy historical record.
        - Snapshot contains no backup creation or restoration logic. All lifecycle
            operations are the exclusive responsibility of the SnapshotsRegistryStore
            implementation.
    """

    original_path: str
    backup_path: str
    checksum: str
    timestamp: float
    event_type: Optional[EventType] = None
    description: Optional[str] = None
