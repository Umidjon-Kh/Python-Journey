"""Tests for key generation utilities."""

import pytest
from cacher.exceptions import KeyGenerationError
from cacher.utils import generate_auto_key, generate_template_key


def sample(a: int, b: int = 10) -> int:
    return a + b


def test_auto_key_positional_and_keyword_same():
    """f(1, 2) and f(a=1, b=2) produce the same key."""
    k1 = generate_auto_key(sample, (1, 2), {})
    k2 = generate_auto_key(sample, (1,), {"b": 2})
    k3 = generate_auto_key(sample, (), {"a": 1, "b": 2})
    assert k1 == k2 == k3


def test_auto_key_applies_defaults():
    """Default argument values are included in the key."""
    k1 = generate_auto_key(sample, (1,), {})
    k2 = generate_auto_key(sample, (1, 10), {})
    assert k1 == k2


def test_auto_key_different_args_produce_different_keys():
    """Different arguments produce different keys."""
    k1 = generate_auto_key(sample, (1, 2), {})
    k2 = generate_auto_key(sample, (1, 3), {})
    assert k1 != k2


def test_auto_key_includes_module_and_qualname():
    """Key contains module and qualname to avoid collisions."""
    key = generate_auto_key(sample, (1, 2), {})
    assert "sample" in key


def test_template_key_basic():
    """Template key formats correctly from arguments."""

    def f(user_id: int, lang: str = "en"): ...

    key = generate_template_key("user-{user_id}:lang-{lang}", f, (1,), {"lang": "ru"})
    assert key == "user-1:lang-ru"


def test_template_key_uses_defaults():
    """Template key applies default argument values."""

    def f(user_id: int, lang: str = "en"): ...

    key = generate_template_key("user-{user_id}:lang-{lang}", f, (42,), {})
    assert key == "user-42:lang-en"


def test_template_key_unknown_placeholder_raises():
    """Unknown placeholder in template raises KeyGenerationError."""

    def f(user_id: int): ...

    with pytest.raises(KeyGenerationError):
        generate_template_key("user-{user_id}:unknown-{xyz}", f, (1,), {})


def test_template_key_different_values_produce_different_keys():
    """Different argument values produce different template keys."""

    def f(x: int): ...

    k1 = generate_template_key("item-{x}", f, (1,), {})
    k2 = generate_template_key("item-{x}", f, (2,), {})
    assert k1 != k2
