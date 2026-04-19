from collections.abc import Mapping, Sequence, Sized
from typing import Any, Tuple, Union, cast, get_args, get_origin

from .field import Field
from .protocols import Comparable


class ValidatorDescriptor:
    """
    A descriptor that validates and stores field values in instance.__dict__.

    Stores data directly in the instance dictionary using the field name
    as key — no WeakKeyDictionary, no recursion, no conflicts with __eq__.
    """

    __slots__ = ("name", "annotation", "specs")

    def __init__(self, annotation: type, specs: Field) -> None:
        self.annotation = annotation
        self.specs = specs

    def __set_name__(self, owner: Any, name: str) -> None:
        self.name = name

    def __get__(self, instance: Any, owner: object) -> Any:
        if instance is None:
            return self
        try:
            return instance.__dict__[self.name]
        except KeyError:
            raise AttributeError(f"{self.name!r}: attribute value is not provided")

    def __set__(self, instance: Any, value: Any) -> None:
        if self.specs.read_only and self.name in instance.__dict__:
            raise ValueError(f"{self.name!r}: attribute is read-only")
        instance.__dict__[self.name] = self.conform_value(value)

    @classmethod
    def _type_checker(
        cls,
        value: Any,
        expected: type,
        deep_check: bool = False,
        _path: str = "root",
    ) -> Tuple[bool, str]:
        """
        Recursively validates that value matches the expected type annotation.
        Returns (True, "") on success or (False, error_message) on mismatch.

        Supports:
            - Primitives:       int, str, float, bool, etc.
            - Any:              always passes
            - Union / Optional: passes if any branch matches
            - Generic aliases:  list[int], dict[str, int], tuple[int, str]
            - Nested generics:  list[tuple[Union[int, float], str]]

        Args:
            value:      The value being validated.
            expected:   The expected type or annotation.
            deep_check: If True, validates elements inside collections.
            _path:      Internal path tracker for error messages.
        """
        if expected is Any:
            return (True, "")

        origin = get_origin(expected)
        args = get_args(expected)

        if origin is Union:
            for candidate in args:
                matched, _ = cls._type_checker(value, candidate, deep_check, _path)
                if matched:
                    return (True, "")
            expected_repr = " | ".join(
                t.__name__ if hasattr(t, "__name__") else str(t) for t in args
            )
            return (
                False,
                f"[{_path}]: expected {expected_repr}, got {type(value).__name__!r}",
            )

        if origin is not None:
            if not isinstance(value, origin):
                return (
                    False,
                    f"[{_path}]: expected {origin.__name__}, got {type(value).__name__!r}",
                )
            if not args or not deep_check:
                return (True, "")
            if issubclass(origin, Mapping):
                for key, val in value.items():
                    matched, message = cls._type_checker(
                        key, args[0], deep_check, f"{_path} → key({key!r})"
                    )
                    if not matched:
                        return (False, message)
                    matched, message = cls._type_checker(
                        val, args[1], deep_check, f"{_path} → value({key!r})"
                    )
                    if not matched:
                        return (False, message)
                return (True, "")
            if issubclass(origin, Sequence):
                for index, item in enumerate(value):
                    matched, message = cls._type_checker(
                        item, args[0], deep_check, f"{_path} → [{index}]"
                    )
                    if not matched:
                        return (False, message)
                return (True, "")
            return (True, "")

        if not isinstance(value, expected):
            return (
                False,
                f"[{_path}]: expected {expected.__name__!r}, got {type(value).__name__!r}",
            )
        return (True, "")

    def _constraints_checker(self, value: Any) -> None:
        """Validates value against all Field constraints."""
        if self.specs.min_value is not None or self.specs.max_value is not None:
            if not isinstance(value, Comparable):
                raise TypeError(f"{self.name!r}: value must be comparable")
            if self.specs.min_value is not None and value < self.specs.min_value:
                raise ValueError(
                    f"{self.name!r}: value is less than minimum allowed {self.specs.min_value!r}"
                )
            if self.specs.max_value is not None and value > self.specs.max_value:
                raise ValueError(
                    f"{self.name!r}: value exceeds maximum allowed {self.specs.max_value!r}"
                )

        if self.specs.min_length is not None or self.specs.max_length is not None:
            if not hasattr(value, "__len__"):
                raise TypeError(f"{self.name!r}: value does not support len()")
            sized_value = cast(Sized, value)
            if (
                self.specs.min_length is not None
                and len(sized_value) < self.specs.min_length
            ):
                raise ValueError(
                    f"{self.name!r}: length {len(sized_value)} is less than minimum {self.specs.min_length!r}"
                )
            if (
                self.specs.max_length is not None
                and len(sized_value) > self.specs.max_length
            ):
                raise ValueError(
                    f"{self.name!r}: length {len(sized_value)} exceeds maximum {self.specs.max_length!r}"
                )

    def conform_value(self, value: Any) -> Any:
        """Runs all validation checks and returns the final value."""
        matched, message = self._type_checker(
            value, self.annotation, self.specs.deep_check
        )
        if not matched:
            raise TypeError(f"{self.name!r}: {message}")

        self._constraints_checker(value)

        if self.specs.choices is not None and value not in self.specs.choices:
            raise ValueError(
                f"{self.name!r}: value {value!r} is not in allowed choices"
            )

        if self.specs.validator is not None and not self.specs.validator(value):
            raise ValueError(f"{self.name!r}: value {value!r} failed custom validator")

        if self.specs.transformer is not None:
            return self.specs.transformer(value)

        return value
