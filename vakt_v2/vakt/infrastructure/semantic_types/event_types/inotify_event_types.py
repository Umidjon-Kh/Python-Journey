from __future__ import annotations

from ....core.domain import EventType


class INotifyEventType(EventType):
    """
    File system event types for implementations that observe via the
    Linux inotify kernel subsystem.

    Provides a complete and granular event set that includes types
    unavailable on other platforms, intended for consumers that want
    fine-grained file system observation through inotify.

    All events are split into two groups: file events and directory events.
    Directory events deliberately omit CLOSE_WRITE and CLOSE_NO_WRITE —
    directories cannot be opened for writing, so those events are
    meaningless in a directory context.

    Why MODIFIED is not provided:
        inotify's IN_MODIFY fires on every write syscall, flooding the
        buffer with high-frequency noise before the file is even closed.
        CLOSE_WRITE captures the same intent — a file was changed — but
        fires exactly once when the writer closes the file descriptor.
        Consumers who want to detect modifications should use CLOSE_WRITE
        instead. If the goal is to detect or prevent unauthorized access
        rather than modification, FILE_OPENED or FILE_ACCESSED are the
        appropriate choices.

    Why system events are not provided:
        IN_IGNORED, IN_UNMOUNT, and IN_Q_OVERFLOW are internal inotify
        signals that do not represent meaningful file system changes and
        have no place in the processing pipeline. Implementations that
        need to react to these signals (e.g., rescan on IN_UNMOUNT or
        IN_Q_OVERFLOW) must handle them internally without surfacing them
        as domain events.

    Notes:
        - Produced only by BaseWatcher implementations that use the
            inotify kernel subsystem.
        - System events IN_IGNORED, IN_UNMOUNT, IN_Q_OVERFLOW are not
            provided. Implementations that need to handle them must do
            so internally.
        - CLOSE_WRITE and CLOSE_NO_WRITE are omitted for directories —
            directories cannot be opened for writing.
        - Implementations are responsible for determining whether an event
            belongs to a file or a directory. inotify delivers this information
            via the IN_ISDIR flag on each event — implementations must check
            this flag themselves and produce the appropriate INotifyEventType
            (FILE_* or DIR_*) accordingly.
    """

    # File events
    FILE_CREATED = "file_created"
    FILE_DELETED = "file_deleted"
    FILE_RENAMED = "file_renamed"
    FILE_MOVED = "file_moved"
    FILE_METADATA_CHANGED = "file_metadata_changed"
    FILE_ACCESSED = "file_accessed"
    FILE_OPENED = "file_opened"
    FILE_CLOSED_WRITE = "file_closed_write"
    FILE_CLOSED_NO_WRITE = "file_closed_no_write"

    # Directory events
    DIR_CREATED = "dir_created"
    DIR_DELETED = "dir_deleted"
    DIR_RENAMED = "dir_renamed"
    DIR_MOVED = "dir_moved"
    DIR_METADATA_CHANGED = "dir_metadata_changed"
    DIR_ACCESSED = "dir_accessed"
    DIR_OPENED = "dir_opened"
