from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from ..domain import Event, Instruction


class BaseInstructionsRegistry(ABC):
    """
    Abstract base class for instruction registry.

    InstructionsRegistry is responsible for two things at once:
        1. Registry - stores and manages Instruction objects.
        2. Matcher - selects the most appropriate Instruction
            for an incoming Event based on its own matching strategy.

    This design enables developers to provide their own matching logic:
        - GlobInstructionsRegistry:     matches by glob patterns in Instruction.paths.
        - RegexInstructionsRegistry:    matches by regex patterns.
        - PriorityInstructionsRegistry: matches by priority rules.

    get() always returns an Instruction - if no matching Instruction is found,
    it returns a default Instruction provided via __init__ of the implementation.
    This guarantees that the Dispatcher always receives a valid Instruction.

    Why __init__ accepts config dictionary:
        Bootstrap is responsible for instantiating all implementations but operates only
        on abstractions without knowing the specific parameters each implementation
        requires. A config dictionary provides a uniform contract that all implementations
        validate whatever keys it needs. This keeps Bootstrap closed to modification
        when new implementations are added and avoids exposing implementation-specific
        parameters to upper layer objects.

    Why describe method:
        Since __init__ accepts an untyped config dict, there is no static way
        for upper layer objects or external tools to know which keys a specific
        implementation expects. describe() fills this gap by returning a human-readable
        explanation of all expected config keys, their types and whether they are required
        or optional. This turns the otherwise opaque config dictionary into a
        self-documenting contract that any developer or management tool can query at
        runtime withuot reading the source code.

    Persistence Advisory:
        All implementations recommend persisting registry after each modification
        to avoid data loss in the event of crash. Even if the daemon itself doesn't
        interact with methods that can modify the registry, it's impossible to predict
        what might happen during a modification by other components or when using
        external registry management utilities.

        Recommended approach:
            - Persist registry immediately after every modification.
            - Use atomic write operations where possible to avoid corrupted
                registry files on crash during write.
            - Load registry from persistent storage on initialization.

    Notes:
        - get() is used by Dispatcher to retrieve Instruction for each Event,
        - add(), delete(), clear(), show() are intended only for external
            management utilities and bootstrap configuration.
        - By default does not require thread-safety as it is only used
            by Dispatcher which operates in a single thread and does not modify registry.
        - All implementations not requires to respect graceful shutdown as it is
            responsibility of upper layer objects (Threads).
        - If the implementation does not use a configuration dictionary, it is
            recommended to simply ignore it, leaving it as an initialization
            argument to the linter stub.
    """

    @abstractmethod
    def __init__(self, config: dict[str, Any]) -> None:
        """
        Initializes all attributes of registry instance.

        Arg:
           config: A dictionary of string keys and dependency resources
                    required for concrete implementation.
        """
        ...

    @abstractmethod
    def add(self, instruction: Instruction) -> None:
        """
        Adds an Instruction to the registry.
        Recommends to persist the registry immediately after addition.
        """
        ...

    @abstractmethod
    def get(self, event: Event) -> Instruction:
        """
        Returns the most appropriate Instruction for the given Event
        based on the implementation matching strategy.
        Always returns a valid Instruction, fallback to default Instruction
        if no matching Instruction is found in the registry.
        Default Instruction is provided via __init__ of the implementation.
        """
        ...

    @abstractmethod
    def show(self) -> Sequence[Instruction]:
        """
        Returns all Instructions from the registry.
        Intended only for external management utilities.
        """
        ...

    @abstractmethod
    def delete(self, target: Any) -> None:
        """
        Removes an Instruction from the registry by the given target.
        Target type depends on the implementation - it can be an index,
        and object, a string or any other identifier.
        Intended only for external management utilities.
        Must silently ignore if target does not exist.
        Also recommends to persist registry after deletion.
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """
        Removes all Instructions from the registry.
        Intended only for external management utilities.
        Must silently ignore if the registry if already empty and
        also recommends to persists the registry after clearing.
        """
        ...

    @abstractmethod
    def describe(self) -> dict[str, str]:
        """
        Returns a dict where each key is the name of a config parameter
        this implementation expects, and each value is a human-readable
        description of that parameter including its type and whether
        it is required or optional.

        Intended for upper layer objects, Bootstrap and external management
        tools that need to know what to place in the config dict before
        instantiating this implementation. Allows runtime introspection
        without reading source code.
        """
        ...
