from collections.abc import Sequence
from typing import Any, Optional

from ..core import Policy
from ..exceptions import ConfigurationError, InvalidPolicyError


def check_policy_requirements(
    policies: Sequence[Any],
    max_size: Optional[int],
    evictions_limit: Optional[int],
) -> None:
    """
    Validates that all provided policies have their
    requirement satisfied and inherited from base abstract class 'Policy'.

    Checks if any policy requires_max_size and evictions_limit,
    and raises InvalidPolicyError if they are not provided.

    Args:
        policies: Sequence of users custom policies
        max_size: Max size of cache storage
        eviction_limit: Count of eviction candidates per eviction cycle.

    Raises:
        InvalidPolicyError: if any policy is not instance of Policy.
        ConfigurationError: if any policy does not have their requirements satisfied.
    """
    for policy in policies:
        if not isinstance(policy, Policy):
            raise InvalidPolicyError(
                "Received object from policies sequence must be inherited from 'Policy' class, "
                f"got {type(policy).__name__!r}"
            )
        if policy.requires_max_size and max_size is None:
            raise ConfigurationError(
                f"{policy.__class__.__name__} requires max_size to be set."
            )
        if policy.requires_max_size and evictions_limit is None:
            raise ConfigurationError(
                f"{policy.__class__.__name__} requires evictions_limit to be set."
            )
