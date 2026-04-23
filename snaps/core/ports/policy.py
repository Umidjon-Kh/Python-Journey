from abc import ABC, abstractmethod
from collections.abc import Hashable, Sequence

from ..entry import CacheEntry


class Policy(ABC):
    """
    A **hooks** based eviction and validation policy.

    Policy does not manage storage or make decisions about when to evict an entry.
    it only does:
        - updates self data strctures in any events (on_*)
        - answers to questions:
            - which keys need to evict? (evict_candidates)
            - is entry valid yet

    Life-cycle (calls by orchestrator):
        1. On adding an entry -> on_add(key, entry)
        2. On access to entry (get) -> on_access(key, entry)
        3. On removing an entry -> on_remove(key)
        4. Before evicting an entry by orchestrator calls evict_candidates(limit)
        5. In every get before returning value calls is_valid(key, entry)

    Notes:
        - Policies has not access to storage.
          Instead of this it returns sequence of keys it wants to evict.
        - Only orchestrator deletes entries from storage.
        - The policy can store any internal state:
            (OrderedDict for LRU, counters for LFU, expiry dict for TTL and etc...)
    """

    @abstractmethod
    def on_access(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Hook: calls after getting access for entry (entry.touch() is already completed)
        """
        ...

    @abstractmethod
    def on_add(self, key: Hashable, entry: CacheEntry) -> None:
        """Hook: calls when putting new or updating exists value in cache."""
        ...

    @abstractmethod
    def on_remove(self, key: Hashable, entry: CacheEntry) -> None:
        """Hook: called before removing entry from cache."""
        ...

    @abstractmethod
    def evict_candidates(self, limit: int) -> Sequence[Hashable]:
        """
        Returns sequence of keys (maximum limit) that can be evicted.
        The policy itself decides in what order (LRU, LFU, TTL, etc...).
        """
        ...

    @abstractmethod
    def is_valid(self, key: Hashable, entry: CacheEntry) -> bool:
        """
        Checks whether an entry can be considered valid.
        Example: TTL - policy returns false, if time of life is expired.
        """
        ...

    @abstractmethod
    def on_clear(self) -> None:
        """
        Resets all internal self states.
        Triggers when clients calls clear in orchestrator to
        remove all entries and reset every polciy internal state.
        """
        ...
