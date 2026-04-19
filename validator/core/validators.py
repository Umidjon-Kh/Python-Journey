from typing import Callable

from typing_extensions import Any


def field_validator(*fields) -> Callable[[Any], Any]:
    """
    Decorator that needs to add extra additional validators that changes or checks
    value when before setting it in the attribute of the class.
    Triggers after descriptor completes validating with standard validators and
    runs before the transformer to work properly.

    Args:
        *fields: name of all received attributes to send tham in to custom validator.

    Returns:
        Callable: that runs in setting attribute value.
    """

    def wrapper(func):
        func.__field_validator__ = fields
        return classmethod(func)

    return wrapper
