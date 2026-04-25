from collections import OrderedDict
from collections.abc import Hashable, Sequence
from threading import Lock

from ..core import CacheEntry, Policy


class LRUPolicy(Policy):
    """
    Realization of evicting policy Least Recently Used (LRU).
    Stores order of acces to entries and evicts the most unused entries.

    Particular qualities:
        - Uses OrderedDict from collections to store all keys in order of use
        - On acces to any entry moves it's key to end of the dict (to remember it as recently used)
        - Also uses thread-safe lock to avoid race condition
    """

    def __init__(self) -> None:
        """Initializes default internal stats (empty ordered_dict) to track order of keys."""
        self._order: OrderedDict[Hashable, None] = OrderedDict()
        self._lock: Lock = Lock()

    def on_add(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Calls when adding entry to the storage by upper layer object (ordinary orchestrator).
        Adds key of entry to end of the ordered dict. (like it was just used)
        """
        with self._lock:
            self._order[key] = None
            self._order.move_to_end(key)

    def on_access(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Calls when orchestrator gained acces to an existing key.
        Moves key to the end of dict (updates recently used order).
        """
        with self._lock:
            self._order.move_to_end(key)

    def on_remove(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Calls before removing entry from storage.
        Removes key from internal storage (ordered dict).
        """
        with self._lock:
            self._order.pop(key, None)

    def evict_candidates(self, limit: int) -> Sequence[Hashable]:
        """
        Returns sequence that contains key of most unused entries to evict.
        If keys to evict is more that limit returns only limit size keys.
        """
        with self._lock:
            to_evict = []
            for key in self._order.keys():
                if len(to_evict) >= limit:
                    break
                to_evict.append(key)

        return to_evict

    def is_valid(self, key: Hashable, entry: CacheEntry) -> bool:
        """LRU does not decides key is valid or not, that's why it returns always True."""
        return True

    def on_clear(self) -> None:
        """
        Resets internal storage to default (empty).
        Calls when clearing a whole storage in cache.
        """
        with self._lock:
            self._order.clear()
