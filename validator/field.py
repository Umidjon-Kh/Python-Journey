from typing import Any, Callable, Container, Optional

from .protocols import Comparable

# Constant to mark not provided arguments
_MISSING = object()


class Field:
    """
    This is a storage class designed to hold all the configuration settings.
    These configs are responsible for providing the descriptor with everyting
    it needs in order to check and properly validate the data that was passed in,
    based on the specific attributes that were originally provided to it.
    """

    __slots__ = (
        "default",
        "deep_check",
        "read_only",
        "min_value",
        "max_value",
        "min_length",
        "max_length",
        "choices",
        "custom_func",
    )

    def __init__(
        self,
        default: Optional[Any] = _MISSING,
        deep_check: bool = False,
        read_only: bool = False,
        min_value: Optional[Comparable] = None,
        max_value: Optional[Comparable] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        choices: Optional[Container] = None,
        custom_func: Callable[[Any], bool] = lambda x: x,
    ) -> None:
        self.default = default
        self.deep_check = deep_check
        self.read_only = read_only
        self.min_value = min_value
        self.max_value = max_value
        self.min_length = min_length
        self.max_length = max_length
        self.choices = choices
        self.custom_func = custom_func
