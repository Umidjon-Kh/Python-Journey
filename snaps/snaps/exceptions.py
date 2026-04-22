"""
Exceptions for the entire "Snaps" cacher  application.
All custom exceptions inherited from CacheError.
"""


class CacheError(Exception):
    """
    Base exception for all cacher errors.
    Uses to when need to catch all error to avoid shutting down the programm.
    """

    ...


class ConfigurationError(CacheError):
    """
    Raised when received params are not valid.
    Examples:
        ttl=-1: ttl param value must be positive integer.
        max_size=0: max_size param value must more than zero.
        max_size="abc": max_size param must be positive integer.
    """

    ...


class KeyGenerationError(CacheError):
    """
    Raised when cache key cannot be generated from callable arguments.
    Usually caused by unhashable objects (mutable) like list or dict.
    """

    ...


class NotFoundError(CacheError):
    """
    Raised when key of callable is not found in data.
    Used when user calls get method for object than not added to cache
    or cache is empty.
    """

    ...


class NonCallableError(ConfigurationError):
    """
    Raised when received callable is not valid.
    Inherited from ConfigError cause it receives only when wrapping object
    into the "@snaps" and raises as sub exception of ConfigurationError.
    """

    ...
