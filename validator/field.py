from os import read
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
        "nullable",
        "read_only",
        "min_value",
        "max_value",
        "min_length",
        "max_length",
        "choices",
        "validator",
    )

    def __init__(
        self,
        default: Optional[Any] = _MISSING,
        nullable: bool = False,
        read_only: bool = False,
        min_value: Optional[Comparable] = None,
        max_value: Optional[Comparable] = None,
        min_lenght: Optional[int] = None,
        max_length: Optional[int] = None,
        choices: Optional[Container] = None,
        validator: Callable[[Any], bool] = lambda x: x,
    ) -> None:
        self.default = default
        self.nullable = nullable
        self.read_only = read_only
        self.min_value = min_value
        self.max_value = max_value
        self.min_length = min_lenght
        self.max_length = max_length
        self.choices = choices
        self.validator = validator
