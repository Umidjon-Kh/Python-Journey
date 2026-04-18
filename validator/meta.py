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

    Supports:
        - Automatic descriptor injection for all annotated fields
        - Field spec validation at class definition time (not at runtime)
        - Inheritance — fields are collected from the full MRO
        - Optional __slots__ generation via slots=True class argument
        - Annotated[type, Field(...)] syntax for full type checker compatibility

    Usage:
        # Standard syntax:
        class User(Model):
            name: str = Field(min_length=1)
            age: int = Field(min_value=0, max_value=150)

        # Annotated syntax (Pyright friendly):
        class User(Model):
            name: Annotated[str, Field(min_length=1)]
            age: Annotated[int, Field(min_value=0, max_value=150)]

        # Mixed:
        class User(Model, slots=True):
            name: Annotated[str, Field(min_length=1)]
            age: int = Field(min_value=0)
            role: str = "admin"
    """

    __fields__: dict[str, FieldInfo]

    def __new__(
        mcls,
        name: str,
        bases: tuple,
        namespace: dict,
        slots: bool = False,
        **kwargs: Any,
    ) -> "MetaValidator":
        annotations: dict = namespace.get("__annotations__", {})
        patched = dict(namespace)
        fields: dict[str, FieldInfo] = {}

        for field_name, annotation in annotations.items():
            # ── Resolve Annotated[type, Field(...)] ──────────────────────────
            if get_origin(annotation) is Annotated:
                annotated_args = get_args(annotation)
                real_annotation = annotated_args[0]
                field_from_annotated = next(
                    (a for a in annotated_args[1:] if isinstance(a, Field)),
                    None,
                )
                raw = namespace.get(field_name, _MISSING)

                # Cannot use Field in both Annotated and as default value
                if field_from_annotated is not None and isinstance(raw, Field):
                    raise TypeError(
                        f"{name!r} attribute {field_name!r}: cannot use Field in both "
                        f"Annotated and as default value"
                    )

                # Cannot have multiple Field in Annotated
                field_list = [a for a in annotated_args[1:] if isinstance(a, Field)]
                if len(field_list) > 1:
                    raise TypeError(
                        f"{name!r} attribute {field_name!r}: only one Field allowed in Annotated"
                    )

                if field_from_annotated is not None:
                    specs = field_from_annotated
                elif raw is _MISSING:
                    specs = Field()
                elif isinstance(raw, Field):
                    specs = raw
                else:
                    specs = Field(default=raw)
                annotation = real_annotation

            # ── Standard syntax ──────────────────────────────────────────────
            else:
                raw = namespace.get(field_name, _MISSING)
                if raw is _MISSING:
                    specs = Field()
                elif isinstance(raw, Field):
                    specs = raw
                else:
                    specs = Field(default=raw)

            # ── Validate Field specs at class definition time ─────────────────
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
                    f"{name!r} attribute {field_name!r}: default value must be immutable"
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

            descriptor = ValidatorDescriptor(annotation, specs)
            patched[field_name] = descriptor
            fields[field_name] = FieldInfo(
                annotation=annotation,
                specs=specs,
                descriptor=descriptor,
            )

        if slots:
            patched["__slots__"] = ()

        cls = super().__new__(mcls, name, bases, patched, **kwargs)

        # Collect inherited fields from full MRO (excluding object)
        inherited: dict[str, FieldInfo] = {}
        for base in reversed(cls.__mro__[1:]):
            inherited.update(getattr(base, "__fields__", {}))

        inherited.update(fields)
        cls.__fields__ = inherited

        return cls
