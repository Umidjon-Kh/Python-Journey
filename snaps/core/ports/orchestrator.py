from abc import ABC, abstractmethod
from collections.abc import Hashable, Mapping
from typing import Any, Optional

# Created to avoid confusing a not found object with
# a NoneType object value of entries
NOT_FOUND = object()


class Orchestrator(ABC):
    """
    Main cache componenets manager - orchestrator.
    It owns the storage and set of the policies.
    It provides a high-level interface to clients.

    Orchestrator itself:
        - checks an entry validations by policies.
        - notifies policies about every event that happaned (hooks).
        - manages evicting candidates in sotrage limit is raised.
        - collects metrics (hits/misses/evicts)

    Clients as e.g. decorator works only with this interface.
    """

    @abstractmethod
    def get(self, key: Hashable) -> Optional[Any]:
        """
        Gets a value by key.

        If key does not exist:
            - increases missed counter value
            - returns None

        If key exists but policies consider it invalid:
            - increases missed counter value
            - deletes entry
            - returns None

        If key exists and its valid:
            - updates entry metadata
            - increases hits counter value
            - notifies policies by calling policy.on_access hook
            - returns value of entry
        """
        ...

    @abstractmethod
    def put(self, key: Hashable, value: Any) -> None:
        """
        Puts value in cache.

        If key is already exists:
            - creates new entry with received value
            - rewrites to storage under received key
            - notifies policies by calling policy.on_add hook
            - not calls evict_candidates cuase size is not increases

        If key is not exist:
            - creates new entry with received value
            - puts it to storage
            - notifies policies by calling policy.on_add hook
            - calls policy.evict_candidates in every policy if limited size of storage is raised
        """
        ...

    @abstractmethod
    def delete(self, key: Hashable) -> None:
        """Forcely remove an entry from the cache (notifies policies via on_remove)."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """
        Clears the storage - removes all entries from storage
        and resets internal states of policies (via on_clear).
        """
        ...

    @abstractmethod
    def stats(self) -> Mapping:
        """
        Returns mapping object that contains stats like:
            - size: curent count of entries
            - hits: count of hits
            - misses: count of misses
            - evictions: count of evicted entries
            - hit_rate: hits / (hits + misses)
        """
        ...
