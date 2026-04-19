from typing import Any, Callable, Container, Optional

_MISSING = object()


class Field:
    """
    Configuration storage for a single validated field.

    All validation constraints and behaviors are defined here
    and passed to ValidatorDescriptor at class creation time.

    Args:
        default:         Default value for the field. Must be immutable.
        default_factory: Callable that returns a new default value each time.
                         Use for mutable defaults like list, dict, set.
        read_only:       If True, field cannot be reassigned after first set.
        min_value:       Minimum allowed value (must support comparison).
        max_value:       Maximum allowed value (must support comparison).
        min_length:      Minimum allowed length (value must support len()).
        max_length:      Maximum allowed length (value must support len()).
        choices:         Container of allowed values.
        deep_check:      If True, validates elements inside collections recursively.
        validator:       Custom callable that returns bool. Called after type check.
        transformer:     Callable that transforms value before storing.
    """

    __slots__ = (
        "default",
        "default_factory",
        "read_only",
        "min_value",
        "max_value",
        "min_length",
        "max_length",
        "choices",
        "deep_check",
        "validator",
        "transformer",
    )

    def __init__(
        self,
        default: Any = _MISSING,
        default_factory: Optional[Callable[[], Any]] = None,
        read_only: bool = False,
        min_value: Optional[Any] = None,
        max_value: Optional[Any] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        choices: Optional[Container] = None,
        deep_check: bool = False,
        validator: Optional[Callable[[Any], bool]] = None,
        transformer: Optional[Callable[[Any], Any]] = None,
    ) -> None:
        self.default = default
        self.default_factory = default_factory
        self.read_only = read_only
        self.min_value = min_value
        self.max_value = max_value
        self.min_length = min_length
        self.max_length = max_length
        self.choices = choices
        self.deep_check = deep_check
        self.validator = validator
        self.transformer = transformer
