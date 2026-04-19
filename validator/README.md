# Validator

A lightweight, Pydantic-inspired data validation library written in pure Python.
Built on top of Python's descriptor protocol and metaclasses — no dependencies.

## Installation

No installation required. Copy the `validator/` directory into your project.

## Quick Start

```python
from typing import Annotated
from validator import Field, Model

class User(Model):
    name: Annotated[str, Field(min_length=2, max_length=50)]
    age: Annotated[int, Field(min_value=0, max_value=150)]
    role: Annotated[str, Field(default="user", choices=["user", "admin"])]

user = User(name="John", age=25)
print(user)           # User(name='John', age=25, role='user')
print(user.to_dict()) # {"name": "John", "age": 25, "role": "user"}
```

## Field Options

| Option            | Type                    | Description                                                   |
| ----------------- | ----------------------- | ------------------------------------------------------------- |
| `default`         | `Any`                   | Default value. Must be immutable.                             |
| `default_factory` | `Callable[[], Any]`     | Factory for mutable defaults like `list`, `dict`.             |
| `read_only`       | `bool`                  | If `True`, field cannot be reassigned after first set.        |
| `min_value`       | `Any`                   | Minimum allowed value. Value must support comparison.         |
| `max_value`       | `Any`                   | Maximum allowed value. Value must support comparison.         |
| `min_length`      | `int`                   | Minimum allowed length. Value must support `len()`.           |
| `max_length`      | `int`                   | Maximum allowed length. Value must support `len()`.           |
| `choices`         | `Container`             | Allowed values. Value must be one of these.                   |
| `deep_check`      | `bool`                  | If `True`, validates elements inside collections recursively. |
| `validator`       | `Callable[[Any], bool]` | Custom validation function.                                   |
| `transformer`     | `Callable[[Any], Any]`  | Transforms value before storing.                              |

## Examples

### Default values

```python
class Config(Model):
    host: Annotated[str, Field(default="localhost")]
    port: Annotated[int, Field(default=8080)]
    tags: Annotated[list, Field(default_factory=list)]

config = Config()
print(config)  # Config(host='localhost', port=8080, tags=[])
```

### Read-only fields

```python
class Article(Model):
    id: Annotated[int, Field(read_only=True)]
    title: Annotated[str, Field()]

article = Article(id=1, title="Hello")
article.title = "World"  # OK
article.id = 2           # ValueError: 'id' is read-only
```

### Custom validator and transformer

```python
class User(Model):
    name: Annotated[str, Field(
        validator=lambda v: v.isalpha(),
        transformer=lambda v: v.strip().title(),
    )]

user = User(name="  john  ")
print(user.name)  # "John"
```

### Deep collection validation

```python
class Batch(Model):
    scores: Annotated[list[int], Field(deep_check=True)]

batch = Batch(scores=[1, 2, 3])       # OK
batch = Batch(scores=[1, "two", 3])   # TypeError: type mismatch at [1]
```

### Inheritance

```python
class Animal(Model):
    name: Annotated[str, Field()]

class Dog(Animal):
    breed: Annotated[str, Field()]

dog = Dog(name="Rex", breed="Labrador")
print(dog)  # Dog(name='Rex', breed='Labrador')
```

### Post-init hook

```python
class User(Model):
    first_name: Annotated[str, Field()]
    last_name: Annotated[str, Field()]
    full_name: Annotated[str, Field(default="")]

    def __post_init__(self) -> None:
        self.full_name = f"{self.first_name} {self.last_name}"

user = User(first_name="John", last_name="Doe")
print(user.full_name)  # "John Doe"
```

## Model Methods

| Method            | Description                                        |
| ----------------- | -------------------------------------------------- |
| `to_dict()`       | Returns all fields as a plain dictionary.          |
| `__post_init__()` | Override to add custom logic after initialization. |

## Architecture

validator/
└── core/
├── protocols.py — Comparable protocol
├── field.py — Field configuration class
├── descriptor.py — ValidatorDescriptor (stores data in instance.dict)
├── meta.py — MetaValidator metaclass + FieldInfo
└── model.py — Model base class

### How it works

1. **Class creation** — `MetaValidator.__new__` reads all `Annotated` annotations,
   wraps each into a `ValidatorDescriptor`, and injects it into the class.
2. **Assignment** — `ValidatorDescriptor.__set__` runs all validation checks
   and stores the value directly in `instance.__dict__`.
3. **Access** — `ValidatorDescriptor.__get__` reads directly from `instance.__dict__`.

## Syntax

Only `Annotated[type, Field(...)]` syntax is supported:

```python
# Correct
name: Annotated[str, Field(min_length=1)]

# Also correct — Field is optional
name: Annotated[str, Field()]

# Not supported
name: str = Field(min_length=1)
```

## Limitations

- `slots=True` is not supported — data is stored in `instance.__dict__`.
- No JSON schema generation.
- No serialization beyond `to_dict()`.
