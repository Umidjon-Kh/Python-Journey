from __future__ import annotations

from ....core import EventType


class InotifyEventType(EventType):
    """
    File system event types for the lInux inotify kernel subsystem.

    Provides the complete event set observable via via inotify including
    higher-fidelity events not avialable on other platforms such as
    FILE_CLOSED_WRITE which fires once after a file is fully written and
    closed - eliminaiting noise of intermediate write events that
    FILE_MODIFIED would produce on every partial write.

    Notes:
        - Produced only by InotifyWatcher implementation.
        - System events IN_IGNORED, IN_UNMOUNT, IN_Q_OVERFLOW are
            handled internally by InotifyWatcher and never reach the buffer.
        - DIR_CLOSED_WRITE is omitted - directories cannot be opened
            for writing.
    """

    FILE_CREATED = "file_created"
    FILE_DELETED = "file_deleted"
    FILE_RENAMED = "file_renamed"
    FILE_MOVED = "file_moved"
    FILE_METADATA_CHANGED = "file_metadata_changed"
    FILE_ACCESSED = "file_accessed"
    FILE_OPENED = "file_opened"
    FILE_CLOSED_WRITE = "file_closed_write"
    FILE_CLOSED_NO_WRITE = "file_closed_no_write"

    DIR_CREATED = "dir_created"
    DIR_DELETED = "dir_deleted"
    DIR_RENAMED = "dir_renamed"
    DIR_MOVED = "dir_moved"
    DIR_METADATA_CHANGED = "dir_metadata_changed"
    DIR_ACCESSED = "dir_accessed"
    DIR_OPENED = "dir_opened"
