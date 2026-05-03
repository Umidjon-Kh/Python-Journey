from __future__ import annotations

from enum import StrEnum


class UserChoice(StrEnum):
    """
    Domain-level object that represents a user-defined
    response to a file system event.

    This enum is used to communicate user's decisions from interacion or
    decision-making components (handlers) back to higher-level objects
    that waits for it (e.g., dispatcher, recovery, or backup objects).

    It is typically produced by components that obtain or infer a user
    decision and that propagated upstream for further processing.

    Notes:
        - UserChoice defines a minimal, stable set of supported actions.
        - It is intentionally limited to ensure consistent behavior across objects.
        - It does not deffine how the decision is obtained.
        - If you want to introduce your own custom choices you need to extend this enum
            by creating object that inherited from UserChoice.
        - All consuming components must expilicitly support any custom values.
        - Unsupported values may result in undefined behavior.

    Choices:
        IGNORE   — user acknowledged but wants no action taken
        BACKUP   — user wants a snapshot created of current state
        ROLLBACK — user wants to restore the previous version
    """

    IGNORE = "ignore"
    BACKUP = "backup"
    ROLLBACK = "rollback"
