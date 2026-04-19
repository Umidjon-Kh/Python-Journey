from typing import Annotated

from core import Field, Model, field_validator


class Person(Model):
    name: Annotated[str, Field(min_length=3, max_length=20, read_only=True)]
    age: Annotated[int, Field(min_value=16, max_value=30)]
    country: Annotated[str, Field(choices=["Uzb", "Ru", "USA"])]
    income: Annotated[int, Field(min_value=0)]

    @field_validator("name")
    def validate_name(cls, value: str) -> str:
        if value.startswith(" "):
            raise ValueError("name cannot start with space")
        return value


p = Person(name="Umidjon", age=18, country="Uzb", income=10000)
print(p.country)
print(p.income)
