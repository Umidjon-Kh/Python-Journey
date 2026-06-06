from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence

from ...domain import Event, Instruction
from .port_protocol import PortProtocol


class BaseInstructionRegistry(PortProtocol):
    """
    Abstract base class for all instruction registry implementations.

    Combines two responsibilities:
        1. Storage — manages a collection of domain Instruction objects.
        2. Matching — selects the most appropriate Instruction for an
            incoming Event using its own matching strategy.

    This separation allows developers to supply custom storage and matching
    logic without touching the pipeline. Examples:
        - S3InstructionRegistry:        stores Instructions metadata in cloud.
        - PriorityInstructionRegistry:  matches by explicit priority rules.
        - CompositeInstructionRegistry: chains multiple strategies together.

    Instruction Return Protocol:
        get() must always return a valid Instruction. If no registered
        instruction matches the event, the implementation must fall back
        to a default Instruction — either determined automatically or
        supplied by the client during configuration.

    Persistence Advisory:
        Implementations are strongly advised to persist registry state after
        every modification. The Observer daemon itself only calls get() and
        never modifies the registry, but the Overseer may concurrently modify
        it through management sessions. A crash at any point must not result
        in data loss.

        Recommended approach:
            - Persist after every add(), delete(), or clear().
            - Use atomic writes (write to a temp file, then rename) to avoid
                corrupting the registry file on crash.
            - Restore persisted state during __init__.

    Why add() accepts a raw dict instead of an Instruction:
        Each registry implementation may require extra meta-parameters beyond
        the Instruction fields themselves (e.g., priority, group, pattern).
        Accepting a raw dict shifts construction and validation into the
        implementation, keeping the external API clean and implementation-agnostic.
        Use sample() to discover the expected structure before calling add().

    Notes:
        - get() is called by the Dispatcher inside its thread.
        - add(), delete(), clear(), show(), sample() are management-only —
            never called by the Dispatcher.
        - Thread-safety is not required by default. The Dispatcher only reads
            via get() and management operations occur in controlled Overseer sessions.
        - Graceful shutdown is handled by upper-layer objects, not the registry.
        - Must never propagate exceptions to the caller. All errors must be caught
            and handled internally.
    """

    @abstractmethod
    def add(self, raw_instruction: dict) -> bool:
        """
        Constructs and stores an Instruction from a raw parameter dictionary.

        The registry validates the dictionary and builds the Instruction
        internally. Returns False if required keys are missing or invalid.
        Use sample() to discover the expected structure before calling this.
        Persisting after add is strongly advised.
        Intended only for management tools, not the Dispatcher.
        """
        ...

    @abstractmethod
    def get(self, event: Event) -> Instruction:
        """
        Returns the most appropriate Instruction for the given Event.

        Applies the implementation's matching strategy. Falls back to a
        default Instruction if no registered instruction matches.
        Called by the Dispatcher within its thread.
        """
        ...

    @abstractmethod
    def delete(self, target: str) -> None:
        """
        Removes an Instruction identified by target.

        The meaning of target is implementation-defined (index, name, pattern).
        Silently ignores the request if target is not found.
        Persisting after deletion is strongly advised.
        Intended only for management tools.
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """
        Removes all Instructions from the registry.

        Silently ignores the request if the registry is already empty.
        Persisting after clearing is strongly advised.
        Intended only for management tools.
        """
        ...

    @abstractmethod
    def show(self) -> Sequence[dict]:
        """
        Returns all Instructions as raw parameter dictionaries.

        Each dict follows the same structure as sample() — the same keys
        that were used when the Instruction was added via add().
        Intended only for management tools.
        """
        ...

    @abstractmethod
    def sample(self) -> dict:
        """
        Returns a skeleton dictionary showing the expected structure for add().

        Includes all Instruction fields and any registry-specific meta-parameters
        (e.g., priority, group, pattern) with their expected types and whether
        they are required or optional. Call this before add() to discover
        what keys the registry expects.
        """
        ...
