from __future__ import annotations


class EventTypeMeta(type):
    """
    Metaclass for EventType that wraps all string class attributes
    into EventType instances on class creation.

    This enables subclassing of EventType without the restrictions
    of StrEnum, while preserving type identity and isinstance checks.

    Why metaclass:
        StrEnum does not allow subclassing once members are defined.
        This metaclass solves that by automatically wrapping string
        constants into EventType instances at class creation time.
        Any subclass of EventType will have its string constants
        wrapped into that subclass type automatically.
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple,
        namespace: dict,
    ) -> EventTypeMeta:
        cls = super().__new__(mcs, name, bases, namespace)
        for key, value in namespace.items():
            if not key.startswith("_") and isinstance(value, str) and key.isupper():
                setattr(cls, key, cls(value))
        return cls


class EventType(str, metaclass=EventTypeMeta):
    """
    Base class for all file system event types.

    EventType uses a custom metaclass instead of StrEnum to allow
    subclassing for platform-specific event type extensions.

    Why not StrEnum:
        StrEnum in Python does not allow subclassing once members
        are defined. Since EventType is designed to be extended by
        platform-specific implementations such as InotifyEventType
        or FanotifyEventType, using StrEnum would prevent this
        extensibility entirely.

    Why metaclass approach:
        EventTypeMeta automatically wraps all string constants into
        EventType instances at class creation time. This means:
            - isinstance(InotifyEventType.FILE_ACCESSED, EventType) → True
            - InotifyEventType.FILE_ACCESSED == "file_accessed" → True
            - All subclass constants are instances of their own subclass

    Notes:
        - EventType is a str subclass so it is fully compatible with
            plain string comparisons and operations.
        - Subclasses automatically inherit this behavior through
            EventTypeMeta without any additional configuration.
        - Do not add members to EventType directly - use
            CrossPlatformEventType for cross-platform events and
            create platform-specific subclasses for extended events.
    """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}={str(self)!r}"
