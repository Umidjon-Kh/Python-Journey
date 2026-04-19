from typing import Annotated, Any, Callable

from core import Field, Model


def transfrom_to_coin(country: str) -> Callable[[Any], int]:
    def transform(count: int) -> int:
        if country == "Ru":
            return count * 100
        elif country == "USA":
            return count * 100
        return count

    return transform


class Person(Model):
    name: Annotated[str, Field(min_length=3, max_length=20, read_only=True)]
    age: Annotated[int, Field(min_value=16, max_value=30)]
    country: Annotated[str, Field(choices=["Uzb", "Ru", "USA"])]
    income: Annotated[int, Field(min_value=0)]


p = Person(name="Umidjon", age=18, country="Uzb", income=10000)
print(p.country)
print(p.income)
