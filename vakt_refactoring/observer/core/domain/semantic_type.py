from __future__ import annotations

from typing import Any


class SemanticTypesMeta(type):
    """
    Metaclass for SemanticType that wraps all uppercase string class
    attributes into SemanticType instances on class creation.

    This enables subsclassing of SemanticType without the restriction
    of StrEnum, while preserving type identity and isinstance checks.

    Why metaclass:
        StrEnum does not allow subclassing once members are defined.
        This metaclass solves that by automatically wrapping uppercase
        string constants into SemanticType instances at class creation time.
        Any subclass of SemanticType will have its string constants
        wrapped into that subclass type automatically.

    Notes:
        - Only uppercase attributes are wrapped (key.isupper()) to avoid
            wrapping methods or other non-constant string attributes.
        - Attributes starting with underscore are always skipped.
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple,
        namespace: dict[str, Any],
    ) -> SemanticTypesMeta:
        cls = super().__new__(mcs, name, bases, namespace)
        for key, value in namespace.items():
            if not key.startswith("_") and isinstance(value, str) and key.isupper():
                setattr(cls, key, cls(value))
        return cls


class SemanticType(str, metaclass=SemanticTypesMeta):
    """
    Base class for all semantic domain types in the pipeline.

    SemanticType uses a custom metclass instead of StrEnum to allow
    subclassing for domain-specific type extensions. It serves as the
    foundation for EventType, InstructionType, LevelType and any other
    semantic classification types in the system.

    Why not StrEnum:
        StrEnum in Python does not allow subclassing once members are defined.
        Since all semantic types in this project are designed to be extended
        by platform-specific or custom implementations, using StrEnum would
        prevent this extensibiliyty entirely.

    Why metaclass approach:
        SemanticTypesMeat automatically wraps all uppercase string constants
        into Semanticype instances at class creation time. This means:
            - isinstance(EventType.FILE_CREATED, EventType) -> True.
            - isinstance(InotifyEventType.FILE_ACCESSED, InotifyEventType) -> True.
            - isinstance(InstructionType.BACKUP, InstructionType) -> True.
            - All subclass constants are instances of their own subclass.
            - All values are fully compatible with plain string comparisons.

    Notes:
        - SemanticType is a str subclass so it is fully compatible with
            plain string comparisons and operations.
        - Subclasses automatically inherit this behavior through
            SemantictypesMeta without any additional configurations.
        - Do not add members to SemanticType directly - create
            domain-specific subclass for each semantic category.
    """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}={str(self)!r}"
