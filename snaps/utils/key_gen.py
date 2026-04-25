from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from ..exceptions import KeyGenerationError


def generate_auto_key(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    """
    Generates a deterministic cache key from function signature.
    Uses inspect.signature to normalize positional and keyword arguments,
    so f(1, b=2) and f(a=1, b=2) produce the same key.
    Also applies default values so f(1) and f(1, timeout=30) match
    when timeout=30 is the default.

    Key format:
        "{module}.{name}:(('arg', value), ...)"

    Why __module__:
        Prevents collisions between same-named functions in different modules.
        Example: users.get_user and posts.get_user won't conflict.

    Why tuple(bound.arguments.items()):
        Produces stable and unique repr compared to OrderedDict.

    Args:
        func:   Target callable.
        args:   Positional arguments.
        kwargs: Keyword arguments.

    Returns:
        str: Ready-to-use cache key.

    Raises:
        KeyGenerationError: If arguments cannot be bound to function signature.
    """
    try:
        sig = inspect.signature(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        args_repr = repr(tuple(bound.arguments.items()))
        return f"{func.__module__}.{func.__qualname__}:{args_repr}"
    except TypeError as exc:
        raise KeyGenerationError(
            "Failed to generate cache key from function arguments."
        ) from exc


def generate_template_key(
    template: str,
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    """
    Generates a cache key from a user-provided template string.
    Template is formatted using bound function arguments so both
    positional and keyword arguments are available by parameter name.

    Example:
        @snap(key="user-{user_id}")
        def get_user(user_id: int): ...
        # get_user(42) → "user-42"

    Args:
        template: Format string with parameter names as placeholders.
        func:     Target callable.
        args:     Positional arguments.
        kwargs:   Keyword arguments.

    Returns:
        str: Ready-to-use cache key.

    Raises:
        KeyGenerationError: If template contains unknown placeholders
                            or arguments cannot be bound.
    Note:
        - The idea to create such a key generator was taken from EzyGang (not code, only idea).
    """
    try:
        sig = inspect.signature(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        return template.format(**bound.arguments)
    except (TypeError, KeyError) as exc:
        raise KeyGenerationError(
            f"Failed to format cache key template '{template}': {exc}"
        ) from exc
