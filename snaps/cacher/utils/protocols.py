from collections.abc import Mapping
from typing import Any, Protocol, TypeVar

_R = TypeVar("_R", covariant=True)


class SnapFunction(Protocol[_R]):
    """
    Protocol for fucntions wrapped by @snap decorator.
    Adds .stats() and .clear() methods to be wrapped callable.
    Actually needed to stub linters as pyright.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> _R:
        """Calls the wrapped function."""
        ...

    def stats(self) -> Mapping:
        """Returns cache statistics: hits, misses, evictions, hit_rate."""
        ...

    def clear(self) -> None:
        """Clears the cache and resets all metrics."""
        ...
