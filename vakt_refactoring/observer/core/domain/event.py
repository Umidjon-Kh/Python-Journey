from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .semantic_type import SemanticType


class EventType(SemanticType):
    """
    Base class for all file system event types.

    EventType serves as the common ancestor for all event type
    implementations both cross-platform and platform-specific.
    It enables type annotations that accept any event type regardless
    of the underlying platfrom or kernel subsystem/

    Subclass this to create platfrom-specific event types:
        - CrossPlatformEventType: cross-platform events
        - InotifyEventType: Linux inotify specific events
        - FanotifyEventType: Linux fanotify specific events
        - WindowsEventType: Windows specific events
    """


class CrossPlatformEventType(EventType):
    """
    Cross-platfrom file system event types.

    Defines the minimal, conservative set of file system events that can
    be reliably observed across different operating system and file system
    implementations. This is the default EventType implementation that
    should be used by all cross-platform components.

    Why conservative:
        This abstraction intentionally excludes platform-specific or
        inconsistently supported events such as file open, access, or
        certain metadata changes in order to provide a stable and portable
        contract for consumers regardless of the underlying platform.

    Extension:
        For platform-specific semantics create a subclass of EventType:
            - InotifyEventType: Linux inotify specific events
            - FanotifyEventType: Linux fanotify specific events
            - WindowsEventType: Windows specific events

        Such extensions are not automatically supported by the core
        processing pipeline. Consumers introducing custom event types
        are responsible for providing compatible handlers that explicitly
        recognize and handle those extended semnatics.

    Notes:
        - All values are lowercase strings for human readability.
        - File and directory events are separated for semantic clarity.
    """

    # File events
    FILE_CREATED = "file_created"
    FILE_DELETED = "file_deleted"
    FILE_MODIFIED = "file_modified"
    FILE_RENAMED = "file_renamed"
    FILE_MOVED = "file_moved"
    FILE_METADATA_CHANGED = "file_metadata_changed"

    # Directory events
    DIR_CREATED = "dir_created"
    DIR_DELETED = "dir_deleted"
    DIR_RENAMED = "dir_renamed"
    DIR_MOVED = "dir_moved"
    DIR_METADATA_CHANGED = "dir_metadata_changed"


@dataclass(frozen=True, slots=True)
class Event:
    """
    An immutable domain-level object representing a single
    change in the file system.

    Attributes:
        - path:          Absolute path of the changed file or directory.
        - event_type:    What kind of change occurred.
                            Accepts any EventType subclass value enabling
                            platform-specific event types to flow through
                            the pipeline without modification.
        - timestamp:     Monotonic timestamp captured by the watcher at
                            the moment the kernel delivered the event.
        - previous_path: Optional absolute path of changed file or directory,
                            serves to represent the previous path of object
                            before moving it.

    Notes:
        - Event is immutable because it describes something that has
            already occurred in the file system and must not be modified.
        - event_type is typed as EventType to accept both
            CrossPlatformEventType and any platform-specific subclass.
    """

    path: str
    event_type: EventType
    timestamp: float
    previous_path: Optional[str] = None
