from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from ..domain import (
    Event,
    EventType,
    Instruction,
    LevelType,
)
from ..ports import BaseInstructionStorage


class InstructionManager:
    """
    Dispatcher-layer service responsible for providing Instruction
    that returned from InstructionStorage implementation for an incoming Event.

    InstructionManager acts as a wrapper over BaseInstructionStorage implementations.
    It delegates matching logic to the storage implementation and
    guarantees that a valid Instruction is always returned by falling back
    to a default Instruction if no match is found.

    It also provides an interface for managing Instruction objects in storage
    which is intended to be used by external management utilities like GUI
    or any other interfaces.

    Attributes:
        - _storage: The instruction registry and matcher.
        - default: Fallback Instruction used when storage returns None.

    Notes:
        - InstructionManager does not implement any matching logic itself.
            All matching is delegated to BaseInstructionStorage get() method.
        - The default Instruction is a pure behavioral fallback.
            It should be defined to represent the safest possible behavior
            when no specific instruction matches the incoming event.
        - Why default Instruction attributes if not protected or private:
            Cause we need to use it in other interfaces of default Instruction
            data. That enables to give some specifics to glob events that
            not provided in InstructionsStorage.
        - add() constructs an Instruction from provided arguments and
            delegates to storage. This keeps Instruction creation logic
            in one place regardless of storage implementation.
        - All methods of InstructionManager not requires to respect shutdown_event
            gracefully cause it responsibility to Disptacher service.
    """

    def __init__(
        self,
        storage: BaseInstructionStorage,
        default: Optional[Instruction] = None,
    ) -> None:
        """Initializes all attributes of InstructionManager instance."""
        self._storage: BaseInstructionStorage = storage
        self.default: Instruction = default or Instruction()

    def get(self, event: Event) -> Instruction:
        """
        Returns the most appropriate Instruction for the given Event.
        Falls back to default Instruction if storage returns None.
        """
        return self._storage.get(event) or self.default

    def add(
        self,
        paths: Optional[Sequence[str]] = None,
        event_types: Optional[Sequence[EventType]] = None,
        level: Optional[LevelType] = None,
        should_log: bool = True,
        should_backup: bool = False,
        should_notify: bool = False,
    ) -> None:
        """
        Creates an Instruction from provided arguments and adds it to storage.
        Why some of the arguments is Optional:
            Cause if user wants to apply this Instruction for
            glob fields of Events in file system.
        """
        instruction = Instruction(
            paths=paths,
            event_types=event_types,
            level=level,
            should_log=should_log,
            should_backup=should_backup,
            should_notify=should_notify,
        )
        self._storage.add(instruction)

    def delete(self, target: Any) -> None:
        """
        Removes an Instruction from storage by the given target.
        Delegates to storage implementation.
        Intended only for external management utilities.
        """
        self._storage.delete(target)

    def clear(self) -> None:
        """
        Removes all Instructions from storage.
        Delegates to storage implementation.
        Also Intended only for external management utilities.
        """
        self._storage.clear()
