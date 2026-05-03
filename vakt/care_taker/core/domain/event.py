from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EventType(StrEnum):
    """
    Domain-level file system event types.

    StrEnum allows comparing with plain strings which is use-ful
    for matching and human-readable.

    For example it can be usable:
        In main objects:
            - watcher: to compare the observers's flag or mask with event type.
        In handlers:
            - logger: to show the event that happened in str not in confusing int.
            - notifier: to match event type with notifier condition that creates notify.
            - snapshots: to save a description of when this snapshot is created.

    Notes:
        - EventType is a StrEnum that defines the minimal, cross-platfrom abstraction
            of file system events. It includes only those event categories that can be reliably
            observed accross different operating systems and file systems implementations.
        - This abstraction is intentionally conservative: it excludes platfrom-specifics or
            inconsistently supported events (such as open, acces, or certain metadata changes)
            in order to provide a stable and portable contract for consumers.
        - For use cases that require higher fidelity or platfrom-specific semantics.
            EventType is designed to be extended. Custom enumerations for example:
            LinuxEventType, WindowsEventType - may introduce additional event
            categories aligned with the capabilities of underlying platform.
        - Such extensions are not automatically supported by the core processing
            pipeline. Consumers introducing custom event types are responsible for providing
            compatible processing components - such as specialized notifiers, dispatchers,
            or handlers - that expilicitly recognize and handle those extended semantics.

        In other words, extending the event model requires corresponding extensions in
        the event handling layer to ensure correct propagation and interpretation of
        platform-specific events.
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
    An Immutable, domain-level object used to
    represent a single changes in the file system.

    Attributes:
        - path:       absolute path of changed file or directory.
        - event_type: what kind of change occurred.
        - timestamp:  monotonic timestamp captured by the watcher at
                      the moment of kernel delivered the event.
    Notes:
        - it is immutable because the event describes an event that
            has already occurred in the file system.
    """

    path: str
    event_type: EventType
    timestamp: float
