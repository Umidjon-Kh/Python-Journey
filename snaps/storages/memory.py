from collections.abc import Hashable, Sequence
from threading import Lock
from typing import Optional

from ..core import CacheEntry, Storage


class InMemoryStorage(Storage):
    """
    Thread-safe storage that contains only cache entries.

    Uses a dictionary to store all entries,
    acces to which is protected by a threading.Lock lock.
    All methods that reads or changes internally stats uses this lock.

    Notes:
        - keys can be any object that is Hashable
        - in fact, read-only operations as (size/contains) don't necessarily have to thread-safe:
            in this class, it's only for consistency
    """

    def __init__(self) -> None:
        """Initializes empty storage in creating an instance."""
        self._data: dict[Hashable, CacheEntry] = {}
        self._lock: Lock = Lock()

    def get(self, key: Hashable) -> Optional[CacheEntry]:
        """
        Returns entry under the received key if key exists in storage,
        Otherwise returns None.
        """
        with self._lock:
            return self._data.get(key, None)

    def put(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Saves entry under the received key,
        if key exists updates entry.
        """
        with self._lock:
            self._data[key] = entry

    def delete(self, key: Hashable) -> None:
        """
        Removes entry under the received key if it exists,
        if it not exist just silently ignores (does nothing).
        """
        with self._lock:
            self._data.pop(key, None)

    def contains(self, key: Hashable) -> bool:
        """Returns True if provided key  exists in storage, otherwise False."""
        with self._lock:
            return key in self._data

    def size(self) -> int:
        """Returns current size of storage."""
        with self._lock:
            return len(self._data)

    def clear(self) -> None:
        """Completely removes all entries from storage."""
        with self._lock:
            self._data.clear()

    def keys(self) -> Sequence[Hashable]:
        """
        Returns sequence that contains keys that curreny stored in dictionary.
        Order of keys is not guaranted.
        """
        with self._lock:
            return list(self._data.keys())
