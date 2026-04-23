from abc import ABC, abstractmethod
from collections.abc import Hashable

from typing_extensions import Optional

from .entry import CacheEntry


class BaseBackend(ABC):
    """
    Abstract base class for all cache storage backends.

    A backend is responsible only for storing and retrieving CacheEntry
    objects by key. It should not contain cache policy logic such as TTL,
    eviction strategy, or access tracking unless explicitly designed for it.
    """

    @abstractmethod
    def get(self, key: Hashable) -> Optional[CacheEntry]:
        """
        Retrieve cache entry by key.

        Args:
            key: Unique cache key.

        Returns:
            CacheEntry: if object founded by key, None otherwise.
        """
        ...

    @abstractmethod
    def set(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Store cache entry under the given key.

        Args:
            key: Unique cache key.
            entry: CacheEntry object to store.
        """
        ...

    @abstractmethod
    def delete(self, key: Hashable) -> None:
        """
        Removes entry by received key.

        Args:
            key: Cache key to delete.
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """
        Removes all entries from backend storage.
        """
        ...

    @abstractmethod
    def has(self, key: Hashable) -> bool:
        """
        Checks whether key exists in backend.

        Args:
            key: Cache key.

        Returns:
            bool: True if key exists, otherwise False.
        """
        ...
