from typing import Callable

from typing_extensions import Any


def field_validator(*fields) -> Callable[[Any], Any]:
    """
    Wrapper to wrap and add function to extra field_calidators in descriptor.

    Needs to add extra additional validator that calls
    after creating all class and triggers after descriptor calls
    confrom_value when setting attribute value.

    Args:
        *fields: name of all received attributes to send tham in to custom validator.

    Returns:
        Callable: that runs in setting attribute value.
    """

    def wrapper(func):
        func.__field_validator__ = fields
        return classmethod(func)

    return wrapper
