"""
General exceptions for entire "snap" cacher application.
All custom exceptions inherit from main exception CacherError.
"""


class CacherError(Exception):
    """Base exception for all cacher errors."""

    ...


class KeyGenerationError(CacherError):
    """Raised when cant generate key for entry from provided arguments."""

    ...


class ConfigurationError(CacherError):
    """Raised when provided configs in dependecny injection is invalid."""

    ...


class InvalidPolicyError(ConfigurationError):
    """Raised when provided custom policy is invalid."""

    ...
