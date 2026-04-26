"""Tests for InMemoryStorage."""

import pytest
from cacher.core import CacheEntry
from cacher.storages import InMemoryStorage


@pytest.fixture
def storage():
    return InMemoryStorage()


@pytest.fixture
def entry():
    return CacheEntry(value=42)


def test_get_missing_key_returns_none(storage):
    """get() returns None when key does not exist."""
    assert storage.get("missing") is None


def test_put_and_get(storage, entry):
    """put() stores entry and get() retrieves it."""
    storage.put("key", entry)
    assert storage.get("key") is entry


def test_put_overwrites_existing(storage):
    """put() overwrites existing entry under same key."""
    first = CacheEntry(value=1)
    second = CacheEntry(value=2)
    storage.put("key", first)
    storage.put("key", second)
    assert storage.get("key") is second


def test_delete_existing_key(storage, entry):
    """delete() removes existing entry."""
    storage.put("key", entry)
    storage.delete("key")
    assert storage.get("key") is None


def test_delete_missing_key_does_not_raise(storage):
    """delete() silently ignores missing keys."""
    storage.delete("nonexistent")  # should not raise


def test_contains_returns_true_for_existing(storage, entry):
    """contains() returns True for existing key."""
    storage.put("key", entry)
    assert storage.contains("key") is True


def test_contains_returns_false_for_missing(storage):
    """contains() returns False for missing key."""
    assert storage.contains("missing") is False


def test_size_empty(storage):
    """size() returns 0 for empty storage."""
    assert storage.size() == 0


def test_size_after_puts(storage):
    """size() returns correct count after insertions."""
    storage.put("a", CacheEntry(value=1))
    storage.put("b", CacheEntry(value=2))
    assert storage.size() == 2


def test_size_after_delete(storage):
    """size() decreases after delete."""
    storage.put("a", CacheEntry(value=1))
    storage.delete("a")
    assert storage.size() == 0


def test_clear_removes_all(storage):
    """clear() removes all entries."""
    storage.put("a", CacheEntry(value=1))
    storage.put("b", CacheEntry(value=2))
    storage.clear()
    assert storage.size() == 0
    assert storage.get("a") is None
    assert storage.get("b") is None


def test_keys_empty(storage):
    """keys() returns empty sequence for empty storage."""
    assert list(storage.keys()) == []


def test_keys_returns_all(storage):
    """keys() returns all stored keys."""
    storage.put("a", CacheEntry(value=1))
    storage.put("b", CacheEntry(value=2))
    assert set(storage.keys()) == {"a", "b"}
