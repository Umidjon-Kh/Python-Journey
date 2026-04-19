from collections.abc import Container, MutableMapping, MutableSequence, MutableSet
from typing import Annotated, Any, NamedTuple, get_args, get_origin

from .descriptor import ValidatorDescriptor
from .field import _MISSING, Field
from .protocols import Comparable


class FieldInfo(NamedTuple):
    """Stores full metadata for a single validated field."""

    annotation: type
    specs: Field
    descriptor: ValidatorDescriptor


class MetaValidator(type):
    """
    Metaclass that automatically wraps annotated class attributes
    into ValidatorDescriptor instances at class creation time.

    Only Annotated[type, Field(...)] syntax is supported.

    Usage:
        class User(Model):
            name: Annotated[str, Field(min_length=1)]
            age: Annotated[int, Field(min_value=0, max_value=150)]
            role: Annotated[str, Field(default="user")]
    """

    __fields__: dict[str, FieldInfo]

    def __new__(
        mcls,
        name: str,
        bases: tuple,
        namespace: dict,
        **kwargs: Any,
    ) -> "MetaValidator":
        annotations: dict = namespace.get("__annotations__", {})
        patched = dict(namespace)
        fields: dict[str, FieldInfo] = {}

        for field_name, annotation in annotations.items():
            if get_origin(annotation) is not Annotated:
                raise TypeError(
                    f"{name!r} attribute {field_name!r}: must use "
                    f"Annotated[type, Field(...)] syntax"
                )

            annotated_args = get_args(annotation)
            real_annotation = annotated_args[0]

            field_list = [a for a in annotated_args[1:] if isinstance(a, Field)]
            if len(field_list) > 1:
                raise TypeError(
                    f"{name!r} attribute {field_name!r}: only one Field allowed in Annotated"
                )

            specs = field_list[0] if field_list else Field()

            # ── Validate Field specs ──────────────────────────────────────────
            if specs.default is not _MISSING and specs.default_factory is not None:
                raise TypeError(
                    f"{name!r} attribute {field_name!r}: cannot set both 'default' and 'default_factory'"
                )
            if specs.default_factory is not None and not callable(
                specs.default_factory
            ):
                raise TypeError(
                    f"{name!r} attribute {field_name!r}: default_factory must be callable"
                )
            if specs.default is not _MISSING and isinstance(
                specs.default, (MutableMapping, MutableSequence, MutableSet)
            ):
                raise TypeError(
                    f"{name!r} attribute {field_name!r}: default must be immutable. Use default_factory instead"
                )
            if specs.validator is not None and not callable(specs.validator):
                raise TypeError(
                    f"{name!r} attribute {field_name!r}: validator must be callable"
                )
            if specs.transformer is not None and not callable(specs.transformer):
                raise TypeError(
                    f"{name!r} attribute {field_name!r}: transformer must be callable"
                )
            if specs.min_value is not None and not isinstance(
                specs.min_value, Comparable
            ):
                raise TypeError(
                    f"{name!r} attribute {field_name!r}: min_value must be comparable"
                )
            if specs.max_value is not None and not isinstance(
                specs.max_value, Comparable
            ):
                raise TypeError(
                    f"{name!r} attribute {field_name!r}: max_value must be comparable"
                )
            if specs.min_length is not None and not isinstance(specs.min_length, int):
                raise TypeError(
                    f"{name!r} attribute {field_name!r}: min_length must be integer"
                )
            if specs.max_length is not None and not isinstance(specs.max_length, int):
                raise TypeError(
                    f"{name!r} attribute {field_name!r}: max_length must be integer"
                )
            if not isinstance(specs.deep_check, bool):
                raise TypeError(
                    f"{name!r} attribute {field_name!r}: deep_check must be boolean"
                )
            if not isinstance(specs.read_only, bool):
                raise TypeError(
                    f"{name!r} attribute {field_name!r}: read_only must be boolean"
                )
            if specs.choices is not None and not isinstance(specs.choices, Container):
                raise TypeError(
                    f"{name!r} attribute {field_name!r}: choices must be a container"
                )

            descriptor = ValidatorDescriptor(real_annotation, specs)
            patched[field_name] = descriptor
            fields[field_name] = FieldInfo(
                annotation=real_annotation,
                specs=specs,
                descriptor=descriptor,
            )

        cls = super().__new__(mcls, name, bases, patched, **kwargs)

        inherited: dict[str, FieldInfo] = {}
        for base in reversed(cls.__mro__[1:]):
            inherited.update(getattr(base, "__fields__", {}))
        inherited.update(fields)
        cls.__fields__ = inherited

        return cls
