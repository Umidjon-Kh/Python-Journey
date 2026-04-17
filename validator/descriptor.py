from collections.abc import Mapping, Sequence
from typing import Any, Union, get_args, get_origin
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

    def conform_value(self, value: Any) -> None:
        # validating for type of value
        pass

    @classmethod
    def _type_checker(cls, value: Any, expected: type) -> bool:
        """
        Checks type of received value for matching to expected type.
        If expected type is Union or Sequence object
        recursively checks every value in sequence.
        """
        if expected is Any:
            return True

        # Getting origin and origin args:
        # Union[int, float] -> origin = Union, args = (int, float)
        origin = get_origin(expected)
        args = get_args(expected)

        # Checking all args if expected union argument
        # if matches one of them returns True
        if origin is Union:
            return any(cls._type_checker(value, t) for t in args)

        # Guards from origin is None cause type_checker works recursively
        if origin is not None:
            if not isinstance(value, origin):
                return False
            # If not args just goes to upper frame.
            if not args:
                return True
            # Checks for dict lika mapping sequences
            if issubclass(origin, Mapping):
                return all(
                    cls._type_checker(k, args[0]) and cls._type_checker(v, args[1])
                    for k, v in value.items()
                )
            # Checks for ordinary sequences
            if issubclass(origin, Sequence):
                return all(cls._type_checker(item, args[0]) for item in value)

        return True
