from typing import Any, Callable, Dict, Hashable, Tuple

from ..exceptions import KeyGenerationError


def generate_key(
    func: Callable[..., Any],
    args: Tuple[Any, ...],
    kwds: Dict[str, Any],
) -> Hashable:
    """
    Generates a deterministic and hashable cache key
    from function call arguments.

    Key format:
         (
             func.__qualname__,
             args,
             tuple(sorted(kwds.items()))
         )

     Why __qualname__:
         Distinguishes methods/functions with same name
         in different classes or scopes.

     Why sorted(kwds.items()):
         Ensures stable ordering so:
             f(a=1, b=2)
         equals:
             f(b=2, a=1)

     Args:
         func:   Target callable.
         args:   Positional arguments.
         kwds: Keyword arguments.
     Returns:
         Hashable: Ready-to-use dictionary key.
     Raises:
         KeyGenerationError: If any part of the generated key is not hashable.
    """
    key = (
        func.__qualname__,
        args,
        tuple(sorted(kwds.items())),
    )

    try:
        hash(key)
    except TypeError as exc:
        raise KeyGenerationError(
            "Function arguments must contain only hashable values."
        ) from exc

    return key
