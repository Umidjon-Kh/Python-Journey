from abc import ABC, abstractmethod
from collections.abc import Hashable, Sequence
from typing import Optional

from ..entry import CacheEntry


class Storage(ABC):
    """
    A storage that is responsible only for stroing the cache objects themselves,
    has no knowledge of the objects of the upper layers as the orchestrators or policies.

    Requirements for realization:
        - All methods must be thraed-safe, if cache uses multi-threading enviroment.
        - Should not throw exceptions related to business logic (only I/O or memory errors).
        - Key must be hashable objects (ordinary str).
        - recording stores with all metadata (CacheEntry).

    What can be realized:
        - InMemoryStorage (in memory, using dict)
        - RedisStorage (from Redis)
        - InDiskStorage (saves memory in disk)
    """

    @abstractmethod
    def get(self, key: Hashable) -> Optional[CacheEntry]:
        """
        Returns recorded entry under the key if it was already recorded,
        otherwise returns None.
        """
        ...

    @abstractmethod
    def put(self, key: Hashable, entry: CacheEntry) -> None:
        """Saves recording under the received key or updates entry if it exists."""
        ...

    @abstractmethod
    def delete(self, key: Hashable) -> None:
        """
        Removes record under the received key if entry is not None,
        otherwise just silently ignores (does nothing).
        """
        ...

    @abstractmethod
    def contains(self, key: Hashable) -> bool:
        """Checks key exitsts or not."""
        ...

    @abstractmethod
    def size(self) -> int:
        """Returns size of storage."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clears all records in storage."""
        ...

    @abstractmethod
    def keys(self) -> Sequence[Hashable]:
        """Returns sequence of keys in storage (order is not guaranted)."""
        ...
