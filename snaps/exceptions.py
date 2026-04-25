"""
General exceptions for entire "snap" cacher application.
All custom exceptions inherit from main exception CacherError.
"""


class CacherError(Exception):
    """Base exception for all cacher errors."""

    ...


class ConfigurationError(CacherError):
    """Raised when provided configs in dependecny injection is invalid."""

    ...


class KeyGenerationError(CacherError):
    """Raised when cant generate key for entry from provided arguments."""

    ...
