from collections.abc import Mapping, Sequence, Sized
from typing import Any, Tuple, Union, cast, get_args, get_origin
from weakref import WeakKeyDictionary

from .field import _MISSING, Field
from .protocols import Comparable


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
            raise AttributeError(f"{self.name!r} attribute value is not provided")

    def __set__(self, instance: Any, value: Any) -> None:
        if self.specs.read_only and instance in self._storage:
            raise ValueError(f"{self.name} attribute value is only for reading")
        final_result = self.conform_value(value)
        self._storage[instance] = final_result

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

    def _constraints_checker(self, value: Any) -> None:
        """
        Validate that the given value satisfies all value and length constraints
        defined in the provided `Field` specification.

        This method enforces:
            - Comparability:   If `min_value` or `max_value` is set, the value must
                               implement the `Comparable` protocol (supporting
                               ``<``, ``<=``, ``>``, ``>=``).
            - Numeric bounds:  `value >= specs.min_value` and
                               `value <= specs.max_value`.
            - Length support:  If `min_length` or `max_length` is set, the value
                               must support the built-in `len()` function (i.e.,
                               implement `__len__`).
            - Length bounds:   `len(value) >= specs.min_length` and
                               `len(value) <= specs.max_length`.

        Args:
            value:
                The value being validated.
            specs:
                A `Field` instance containing the constraint parameters:
                `min_value`, `max_value`, `min_length`, `max_length`.

        Raises:
            TypeError:
                - If `min_value` / `max_value` are set but `value` is not comparable.
                - If `min_length` / `max_length` are set but `value` does not
                  support `len()`.
            ValueError:
                - If `value` is outside the allowed numeric bounds.
                - If the length of `value` is outside the allowed length bounds.

        Returns:
            None: The method completes silently if all constraints are satisfied.
        """
        if self.specs.min_value is not None or self.specs.max_value is not None:
            if not isinstance(value, Comparable):
                raise TypeError(
                    f"{self.name!r} attribute value must need to be comparable"
                )

            if self.specs.min_value is not None and value < self.specs.min_value:
                raise ValueError(
                    f"{self.name!r} attribute value less than minimum allowed {self.specs.min_value}"
                )
            if self.specs.max_value is not None and value > self.specs.max_value:
                raise ValueError(
                    f"{self.name!r} attribute value is greater than maximum allowed {self.specs.max_value!r}"
                )

        if self.specs.min_length is not None or self.specs.max_length is not None:
            if not hasattr(value, "__len__"):
                raise TypeError(f"{self.name!r} attribute value does not support len()")

            sized_value = cast(Sized, value)

            if (
                self.specs.min_length is not None
                and len(sized_value) < self.specs.min_length
            ):
                raise ValueError(
                    f"{self.name!r} attribute value length less than minimum allowed {self.specs.min_length!r}"
                )

            if (
                self.specs.max_length is not None
                and len(sized_value) > self.specs.max_length
            ):
                raise ValueError(
                    f"{self.name!r} attribute value length greater than maximum allowed {self.specs.max_length!r}"
                )

    def conform_value(self, value: Any) -> Any:
        """
        Validates value against the descriptor's annotation and Field specs.
        Raises TypeError with a full path description if validation fails.
        """
        matched, message = self._type_checker(
            value, self.annotation, self.specs.deep_check
        )
        if not matched:
            raise TypeError(f"{self.name!r}: {message}")

        self._constraints_checker(value)

        if self.specs.choices is not None and value not in self.specs.choices:
            raise ValueError(
                f"{self.name!r}: value {value!r} is not in allowed choices {self.specs.choices}"
            )

        if self.specs.validator is not None and not self.specs.validator(value):
            raise ValueError(f"{self.name!r}: value {value!r} failed custom validator")

        if self.specs.transformer is not None:
            return self.specs.transformer(value)

        return value
