from collections import defaultdict
from collections.abc import Hashable, Sequence
from threading import Lock

from ..core import CacheEntry, Policy


class LFUPolicy(Policy):
    """
    Realization of evicting policy Least Frequently Used (LFU).
    Tracks access frequency of entries and evicts the least frequently used ones.

    Particular qualities:
        - Uses frequency dict to track how many times each key was accessed.
        - Uses buckets (defaultdict of set) to group keys by their frequency.
        - Tracks min_freq to find eviction candidates in O(1).
        - Also uses thread-safe lock to avoid race condition.
    """

    def __init__(self) -> None:
        """Initializes default internal stats to track frequency of keys."""
        self._freq: dict[Hashable, int] = {}
        self._buckets: defaultdict[int, set] = defaultdict(set)
        self._min_freq: int = 0
        self._lock: Lock = Lock()

    def on_add(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Calls when adding entry to the storage by upper layer object (ordinary orchestrator).
        Sets frequency of key to 1 and places it in bucket 1.
        Always resets min_freq to 1 since new entry is the least frequent.
        """
        with self._lock:
            self._freq[key] = 1
            self._buckets[1].add(key)
            self._min_freq = 1

    def on_access(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Calls when orchestrator gained access to an existing key.
        Moves key from current frequency bucket to the next one.
        Updates min_freq if current bucket becomes empty after moving.
        """
        with self._lock:
            if key not in self._freq:
                return

            freq = self._freq[key]
            self._freq[key] = freq + 1

            self._buckets[freq].discard(key)
            if not self._buckets[freq]:
                del self._buckets[freq]
                if self._min_freq == freq:
                    self._min_freq = freq + 1

            self._buckets[freq + 1].add(key)

    def on_remove(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Calls before removing entry from storage.
        Removes key from frequency dict and its bucket.
        """
        with self._lock:
            freq = self._freq.pop(key, None)
            if freq is None:
                return
            self._buckets[freq].discard(key)
            if not self._buckets[freq]:
                del self._buckets[freq]

    def evict_candidates(self, limit: int) -> Sequence[Hashable]:
        """
        Returns sequence of least frequently used keys to evict.
        Starts from min_freq bucket and moves to higher frequencies if needed.
        If total candidates are less than limit returns all available.
        """
        with self._lock:
            to_evict = []
            for freq in sorted(self._buckets.keys()):
                for key in self._buckets[freq]:
                    if len(to_evict) >= limit:
                        return to_evict
                    to_evict.append(key)
        return to_evict

    def is_valid(self, key: Hashable, entry: CacheEntry) -> bool:
        """LFU does not decide if key is valid or not, that's why it returns always True."""
        return True

    def on_clear(self) -> None:
        """
        Resets all internal stats to default (empty).
        Calls when clearing a whole storage in cache.
        """
        with self._lock:
            self._freq.clear()
            self._buckets.clear()
            self._min_freq = 0
