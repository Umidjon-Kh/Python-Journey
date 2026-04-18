from collections.abc import Mapping, Sequence
from typing import Any, Tuple, Union, get_args, get_origin
from weakref import WeakKeyDictionary

from field import _MISSING, Field


class ValidatorDescriptor:
    """
    A descriptor that enforces validation rules whenever the attribute is set.
    Each time a new value is assigned to the managed attribute, the descriptor
    checks whether the value conforms to the predefined specifications. If the
    value does not meet the requirements, an appropriate exception is raised.
    """

    __slots__ = (
        "name",
        "annotation",
        "specs",
        "_storage",
    )

    def __init__(self, annotation: type, specs: Field) -> None:
        self.annotation = annotation
        self.specs = specs
        self._storage = WeakKeyDictionary()

    def __set_name__(self, owner: Any, name: str) -> None:
        self.name = name

    def __get__(self, instance: Any, owner: object) -> Any:
        if instance is None:
            return self

        elif instance in self._storage:
            return self._storage[instance]

        elif self.specs.default is not _MISSING:
            return self.specs.default

        else:
            raise AttributeError(f"{self.name!r} attribute value is not provided.")

    def __set__(self, instance: Any, value: Any) -> None:
        if self.specs.read_only and instance in self._storage:
            raise ValueError(f"{self.name} attribute value is only for reading.")
        self.conform_value(value)
        self._storage[instance] = value

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
        Returns (True, "") on success or (False, error_path) on first mismatch.

        Supports:
            - Primitives:       int, str, float, bool, etc.
            - Any:              always passes
            - Union / Optional: passes if any branch matches
            - Generic aliases:  list[int], dict[str, int], tuple[int, str]
            - Nested generics:  list[tuple[Union[int, float], str]]

        Args:
            value:      The value being validated.
            expected:   The expected type or annotation.
            deep_check: If True, validates elements inside collections recursively.
            _path:      Internal — tracks location for error messages.
                        Do not pass manually.

        Returns:
            tuple[bool, str]:
                - (True, "")           → value matches expected
                - (False, error_path)  → mismatch with full path description
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

    def conform_value(self, value: Any) -> None:
        """
        Validates value against the descriptor's annotation and Field specs.
        Raises TypeError with a full path description if validation fails.
        """
        matched, message = self._type_checker(
            value, self.annotation, self.specs.deep_check
        )
        if not matched:
            raise TypeError(f"'{self.name}': {message}")
