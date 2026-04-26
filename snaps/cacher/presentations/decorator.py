from collections.abc import Callable, Sequence
from functools import wraps
from typing import Any, Optional, cast

from ..core import (
    NOT_FOUND,
    MetricsCollector,
    Policy,
    Storage,
)
from ..exceptions import ConfigurationError
from ..metrics import InMemoryMetrics
from ..orchestrators import CompositeOrchestrator, SimpleOrchestrator
from ..policies import LFUPolicy, LRUPolicy, TTLPolicy
from ..storages import InMemoryStorage
from ..utils import (
    SnapFunction,
    check_policy_requirements,
    generate_auto_key,
    generate_template_key,
)


def snap(
    # Orchestrator dependency args
    max_size: Optional[Any] = None,
    evictions_limit: Optional[Any] = None,
    key: Optional[Any] = None,
    # Custom policies and default policies cfg
    policies: Optional[Sequence[Any]] = None,
    ttl: Optional[tuple[float, bool]] = None,
    lru: Optional[bool] = None,
    lfu: Optional[bool] = None,
    # Custom storage to use
    storage: Optional[Any] = None,
    # Custom metrics to use
    metrics: Optional[Any] = None,
) -> Callable:
    """
    Realization of presentation in the form of decorator.
    This decorator needed to cachify all function calls to return entry from
    cache if its was already recorded into a cache.

    Args:
        max_size:
            Max count of entries in cache. If cache raises a max size orchestrator
            evicts invalid entries from cache, but to work this operation orchestrator
            needs policies that requires max size and evictions limit count.

        evictions_limit:
            Count of candidates that needs to evict from cache,
            all three objects: ('evictions_limit', 'max_size', 'policy that requires max_size')
            depends on each other.

        policies:
            Users cutsom policies that inherited from abstract port 'Policy' with their own logic.

        ttl:
            TTL - (Time-To-Live) policy that decides expired entry or not,
            dont needs max_size for work, argument must be in tuple(int, bool)
            that decides how much time to live of entry and which mode to use:
                sliding: True - determines expired or not from last acces
                sliding: False - determines expired or not from creation date.

        lru:
            LRU - (Least-Recently-Used) policy that decides invalid entries or not
            from how recently it used, evicts only old entries that not used recently.
            Needs max_size and evictions limit to work.

        lfu:
            LFU - (Least-Frequently-Used) policy that decides invalid entries or not
            from how frequently is used, evicts only most unused entries.
            Needs max_size and evictions limit to work.

        storage:
            Custom storage from user if dont wants to use default storage that saves
            all entries cache in memory.
            Note: currently only one variation of storage, but in feature i add another vairations.
    """
    # ----- Validating policies and orchestrator attrs -----------
    # 1. Action: check and validate default policies
    approved_policies = def_policies_checker(ttl, lru, lfu, max_size, evictions_limit)

    # 2. Action: check the user custom policies
    if policies is not None:
        check_policy_requirements(policies, max_size, evictions_limit)
        approved_policies += list(policies)

    # ---- Validating other received arguments
    # 1. Action: check the user custom storage
    approved_storage = InMemoryStorage()
    if storage is not None:
        if not isinstance(storage, Storage):
            raise ConfigurationError(
                "Received object storage must be inherited from 'Storage' class, "
                f"got {type(storage).__name__}"
            )

        approved_storage = storage

    # 2. Action: check the user custom metrics collector
    approved_metrics = InMemoryMetrics()
    if metrics is not None:
        if not isinstance(metrics, MetricsCollector):
            raise ConfigurationError(
                "Received object metrics must be inherited from 'MetricsCollector' class, "
                f"got {type(metrics).__name__}"
            )

        approved_metrics = metrics

    if key is not None:
        if not isinstance(key, str):
            raise ConfigurationError(
                f"Received key argument must be str, got {type(key).__name__!r}"
            )

    # ---- Creating Orchestrator depended in policies count --------
    if len(approved_policies) <= 1:
        orchestrator = SimpleOrchestrator(
            policy=approved_policies[0] if approved_policies else None,
            storage=approved_storage,
            metrics=approved_metrics,
            max_size=max_size,
            eviction_limit=evictions_limit,
        )

    else:
        orchestrator = CompositeOrchestrator(
            policies=approved_policies,
            storage=approved_storage,
            metrics=approved_metrics,
            max_size=max_size,
            eviction_limit=evictions_limit,
        )

    # ----- Wrapping callable ----------
    def decorator(func: Callable) -> SnapFunction:
        @wraps(func)
        def wrapper(*args: Any, **kwds: Any) -> Any:
            # generation of key to cache storage
            if key is not None:
                cache_key = generate_template_key(key, func, args, kwds)
            else:
                cache_key = generate_auto_key(func, args, kwds)

            result = orchestrator.get(cache_key)
            if result is NOT_FOUND:
                result = func(*args, **kwds)
                orchestrator.put(cache_key, result)

            return result

        # Adding clear and stats method to wrapper
        setattr(wrapper, "clear", orchestrator.clear)
        setattr(wrapper, "stats", orchestrator.stats)

        return cast(SnapFunction, wrapper)

    return decorator


def def_policies_checker(
    ttl: Optional[tuple[float, bool]],
    lru: Optional[bool],
    lfu: Optional[bool],
    max_size: Optional[Any],
    evictions_limit: Optional[Any],
) -> list[Policy]:
    """
    Validates that all default policies have their requirements satisfied.

    Checks if any default policy is included and all it's requirements is satisfied:
        ttl: defaulf TTLPolicy configurations that dont needs any requirements.
        lru: default LRUPolicy is included or not if included checks it too.
        lfu: default LFUPolicy is included or not if included checks it too.

    Raises:
        ConfigurationError: if any policy does not have their requirements satisfied.
    """
    policies = []

    if ttl is not None:
        if not isinstance(ttl[0], (float, int)):
            raise ConfigurationError(
                f"TTLPolicy first argument must be integer not {type(ttl[0]).__name__!r}."
            )
        if not isinstance(ttl[1], bool):
            raise ConfigurationError(
                f"TTLPolicy second argument 'sliding' must be boolean got {type(ttl[1]).__name__!r}"  # type: ignore[union-attr]
            )

        policies.append(TTLPolicy(ttl=ttl[0], sliding=ttl[1]))

    if lru is not None:
        if max_size is None or evictions_limit is None:
            raise ConfigurationError(
                "LRUPolicy requires 'max_size' and 'evictions_limit' to be set."
            )

        policies.append(LRUPolicy())

    if lfu is not None:
        if max_size is None or evictions_limit is None:
            raise ConfigurationError(
                "LFUPolicy requires 'max_size' and 'evictions_limit' to be set."
            )

        policies.append(LFUPolicy())

    if max_size is not None or evictions_limit is not None:
        if not isinstance(max_size, int) or isinstance(max_size, bool):
            raise ConfigurationError(
                f"Argument 'max_size' must be positive integer got {type(max_size).__name__!r}."
            )

        if max_size <= 0:
            raise ConfigurationError(
                f"Argument 'max_size' must be positive integer got {max_size}."
            )

        if not isinstance(evictions_limit, int) or isinstance(evictions_limit, bool):
            raise ConfigurationError(
                f"Argument 'evictions_limit' must be positive integer got {type(evictions_limit).__name__!r}."
            )

        if evictions_limit <= 0:
            raise ConfigurationError(
                f"Argument 'evictions_limit' must be positive integer got {evictions_limit}."
            )

    return policies
