from typing import Any

from .field import _MISSING
from .meta import MetaValidator


class Model(metaclass=MetaValidator):
    """
    Base class for all validated models.

    Provides automatic field validation, type checking, and constraint
    enforcement via MetaValidator metaclass and ValidatorDescriptor.

    Features:
        - Automatic __init__ with required field enforcement
        - __repr__, __eq__, __hash__ out of the box
        - to_dict() for serialization
        - __post_init__ hook for custom post-initialization logic
        - Optional __slots__ via slots=True class argument

    Usage:
        class User(Model, slots=True):
            name: str
            age: int = Field(min_value=0, max_value=150)

        user = User(name="John", age=25)
        print(user)          # User(name='John', age=25)
        print(user.to_dict()) # {"name": "John", "age": 25}
    """

    def __init__(self, **kwargs: Any) -> None:
        for field_name, field_info in self.__class__.__fields__.items():
            if field_name in kwargs:
                setattr(self, field_name, kwargs[field_name])
            elif field_info.specs.default_factory is not None:
                setattr(self, field_name, field_info.specs.default_factory())
            elif field_info.specs.default is not _MISSING:
                setattr(self, field_name, field_info.specs.default)
            else:
                raise TypeError(
                    f"{self.__class__.__name__}() missing required field: {field_name!r}"
                )

        self.__post_init__()

    def __repr__(self) -> str:
        fields = ", ".join(
            f"{k}={getattr(self, k)!r}" for k in self.__class__.__fields__
        )
        return f"{self.__class__.__name__}({fields})"

    def __eq__(self, other: object) -> bool:
        if type(self) is not type(other):
            return False
        return all(
            getattr(self, k) == getattr(other, k) for k in self.__class__.__fields__
        )

    def __hash__(self) -> int:
        return id(self)

    def to_dict(self) -> dict[str, Any]:
        """Returns all fields as a plain dictionary."""
        return {k: getattr(self, k) for k in self.__class__.__fields__}

    def __post_init__(self) -> None: ...
