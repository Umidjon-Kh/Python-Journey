"""End-to-end tests for @snap decorator."""

import time

import pytest
from cacher.exceptions import ConfigurationError
from cacher.presentations import snap


def test_function_called_only_once():
    """Decorated function is called only once for same arguments."""
    call_count = 0

    @snap()
    def f(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x * 2

    f(5)
    f(5)
    f(5)
    assert call_count == 1


def test_different_args_call_function_each_time():
    """Different arguments produce separate cache entries."""
    call_count = 0

    @snap()
    def f(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x

    f(1)
    f(2)
    f(3)
    assert call_count == 3


def test_none_value_is_cached():
    """None return value is cached and not recomputed."""
    call_count = 0

    @snap()
    def f(x: int):
        nonlocal call_count
        call_count += 1
        return None

    f(1)
    f(1)
    assert call_count == 1
    assert f(1) is None


def test_cache_clear_resets_cache():
    """clear() causes next call to recompute."""
    call_count = 0

    @snap()
    def f(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x

    f(1)
    assert call_count == 1
    f.clear()  # type: ignore[stub]
    f(1)
    assert call_count == 2


def test_stats_attached_to_function():
    """stats() is attached to decorated function and returns correct data."""

    @snap()
    def f(x: int) -> int:
        return x

    f(1)
    f(1)
    f(2)

    stats = f.stats()  # type: ignore[stub]
    assert "metrics" in stats
    assert "storage" in stats
    assert stats["metrics"]["hits"] == 1
    assert stats["metrics"]["misses"] == 2


def test_ttl_policy_expires_entry():
    """TTL policy causes recomputation after expiry."""
    call_count = 0

    @snap(ttl=(0.05, False))
    def f(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x

    f(1)
    assert call_count == 1
    time.sleep(0.1)
    f(1)
    assert call_count == 2


def test_lru_policy_evicts_oldest():
    """LRU policy evicts least recently used entry."""
    call_count = 0

    @snap(lru=True, max_size=2, evictions_limit=1)
    def f(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x

    f(1)  # count=1
    f(2)  # count=2
    f(1)  # from cache
    f(3)  # count=3 — evicts 2
    f(2)  # count=4 — recomputed
    assert call_count == 4


def test_template_key():
    """Template key produces correct cache behavior."""
    call_count = 0

    @snap(key="item-{item_id}:lang-{lang}")
    def f(item_id: int, lang: str = "en") -> str:
        nonlocal call_count
        call_count += 1
        return f"{item_id}-{lang}"

    f(1, lang="en")
    f(1, lang="en")  # from cache
    f(1, lang="ru")  # different key — recomputed
    assert call_count == 2


def test_invalid_max_size_raises():
    """Non-integer max_size raises ConfigurationError."""
    with pytest.raises(ConfigurationError):

        @snap(lru=True, max_size="big", evictions_limit=1)
        def f(): ...


def test_negative_max_size_raises():
    """Negative max_size raises ConfigurationError."""
    with pytest.raises(ConfigurationError):

        @snap(lru=True, max_size=-1, evictions_limit=1)
        def f(): ...


def test_lru_without_max_size_raises():
    """LRU without max_size raises ConfigurationError."""
    with pytest.raises(ConfigurationError):

        @snap(lru=True)
        def f(): ...


def test_invalid_ttl_type_raises():
    """Non-integer TTL value raises ConfigurationError."""
    with pytest.raises(ConfigurationError):

        @snap(ttl=("bad", False))  # type: ignore[test]
        def f(): ...
