from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from ..domain import Event, Instruction


class BaseInstructionStorage(ABC):
    """
    Abstract base class for instruction registry storage.

    InstructionStorage is responsible for storing and managing
    Instruction objects and selecting the most appropriate one
    for an incoming Event. It acts as a registry and a matcher -
    each implementation defines its own logic for matching strategy.

    This design enables developers to provide their own matching logic:
        - GlobInstructionStorage: matches by glob patterns in Instruction.paths
        - RegexInstructionStorage: matches by regex patterns
        - PriorityInstructionStorage: matches by priority rules

    If no matching Instruction is found, get() returns None.
    In that case InstructionManager is responsible for providing
    a default Instruction to the Dispatcher.

    Persistence:
        - InstructionStorage loads Instruction from a config file on startup.
        - It does not persist changes automatically like SnapshotsStorage.
            Managing Instructions at runtime is responsibility of
            external management utilities.

    Notes:
        - delete() is not used by the daemon itself. It is intended
            only for external management utilities or interfaces.
        - Storage does not contain any business logic beyond matching.
            It is a pure registry of Instruction objects.
        - Storage does not require thread-safety, it is only used
            by InstructionManager which operates in Dispatcher layer
        - All storage implementations not strictly require to respect
            gracefully shutdown, cause it's responsibility of upper
            layer on base implementation.
    """

    @abstractmethod
    def add(self, instruction: Instruction) -> None:
        """
        Adds an Instruction to the registry,
        Not requires to respect shutdown gracefully event cause it is
        responsibility of upper layer objects.
        """
        ...

    @abstractmethod
    def get(self, event: Event) -> Optional[Instruction]:
        """
        Returns the most appropriate Instruction for the given Event
        based on the implementation matching strategy.
        Returns NoneType object if no matching Instruction is found.
        InstructionManager is responsible for handling the None case
        by providing a default Instruciton.
        """
        ...

    @abstractmethod
    def delete(self, target: Any) -> None:
        """
        Removes an Instruction from the registry by the given target.
        Target type depends on the implementation - it can be an index,
        an object, a string or any other identifier.
        Intended only for external management utilities.
        Should silently ignore if target does not exist.
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """
        Removes all Instructions from the registry.
        Intended only for external management utilities.
        Should silently ignore if registry is already empty.
        """
        ...
