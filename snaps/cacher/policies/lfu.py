from collections import defaultdict
from collections.abc import Hashable, Sequence
from threading import Lock

from ..core import CacheEntry, Policy


class LFUPolicy(Policy):
    """
    Realization of evicting policy Least Frequently Used (LFU).
    Tracks access frequency of entries and evicts the least frequently used ones.

    Particular qualities:
        - Uses buckets (defaultdict of set) to group keys by their frequency
        - Uses entry.access_count as single source of truth for current frequency
        - Tracks min_freq to find eviction candidates without scanning all keys
        - Also uses thread-safe lock to avoid race condition
    """

    def __init__(self) -> None:
        """Initializes default internal stats to track frequency of keys."""
        self._buckets: defaultdict[int, set] = defaultdict(set)
        self._min_freq: int = 0
        self._lock: Lock = Lock()

    def on_add(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Calls when putting new or updating existing value in cache.
        Orchestrator guarantees on_remove is called before on_add on update,
        so this method always receives a fresh key with access_count = 1.
        Always resets min_freq to 1 since added entry is the least frequent.
        """
        with self._lock:
            self._buckets[entry.access_count].add(key)
            self._min_freq = entry.access_count  # always 1

    def on_access(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Calls after getting access to entry (entry.touch() already completed).
        old bucket = access_count - 1, new bucket = access_count.
        Updates min_freq if old bucket becomes empty after moving.
        """
        with self._lock:
            old_freq = entry.access_count - 1
            new_freq = entry.access_count

            self._buckets[old_freq].discard(key)
            if not self._buckets[old_freq]:
                del self._buckets[old_freq]
                if self._min_freq == old_freq:
                    self._min_freq = new_freq

            self._buckets[new_freq].add(key)

    def on_remove(self, key: Hashable, entry: CacheEntry) -> None:
        """
        Calls before removing entry from cache.
        Uses entry.access_count to find the right bucket directly.
        """
        with self._lock:
            freq = entry.access_count
            self._buckets[freq].discard(key)
            if not self._buckets[freq]:
                del self._buckets[freq]

    def evict_candidates(self, limit: int) -> Sequence[Hashable]:
        """
        Returns sequence of least frequently used keys to evict.
        Walks from min_freq upward until limit is reached.
        """
        with self._lock:
            to_evict = []
            freq = self._min_freq
            while len(to_evict) < limit and freq in self._buckets:
                for key in self._buckets[freq]:
                    if len(to_evict) >= limit:
                        break
                    to_evict.append(key)
                freq += 1
        return to_evict

    def is_valid(self, key: Hashable, entry: CacheEntry) -> bool:
        """LFU does not decide if key is valid or not, that's why it returns always True."""
        return True

    def on_clear(self) -> None:
        """Resets all internal stats to default. Calls when clearing storage."""
        with self._lock:
            self._buckets.clear()
            self._min_freq = 0
