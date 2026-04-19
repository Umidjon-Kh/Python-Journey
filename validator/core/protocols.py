from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Comparable(Protocol):
    """
    A structural protocol for objects that support all four rich comparison operators.

    Any class that implements __lt__, __le__, __gt__, and __ge__ implicitly
    satisfies this protocol and can be used wherever a Comparable is expected.
    """

    def __lt__(self, other: Any) -> bool: ...
    def __le__(self, other: Any) -> bool: ...
    def __gt__(self, other: Any) -> bool: ...
    def __ge__(self, other: Any) -> bool: ...
