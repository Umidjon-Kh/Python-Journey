from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .event import Event
from .instruction import Instruction, InstructionType
from .snapshot import Snapshot


@dataclass(slots=True)
class EventContext:
    """
    A mutable dispatcher-layer object that represents the processing context
    of a single file system change.

    EventContext is instantiated by the Dispatcher after an event is retrieved
    from the buffer. It acts as a shared state carrier that all handlers read
    from and write to during the processing lifecycle of a single event.

    Why mutable:
        Handlers use EventContext to track progress and mark which actions
        have already been performed. Each handler may update specific fields
        to indicate completion of its own responsibility. Immutability would
        require handlers to return new objects on every change which would
        introduce unnecessary complexity and coupling.

    Lifecycle:
        EventContext is strictly ephemeral. It exists only during the lifecycle
        of event handling - from the moment the Dispatcher pulls the event from
        the buffer until all handlers have finished processing. After that,
        the instance is disappears.

    Handler Loop Mechanics:
        - processed_handlers: incremented by each non-phantom handler after
            completing its work. Used by the Dispatcher loop to determine
            when all handlers have finished.
        - handlers_count: total number of handlers that will process this event.
            Decremented by phantom handlers and handlers that cannot process
            the current event. Used together with processed_handlers to
            determine loop termination.
        - performed: a sequence of InstructionType values that represent completed
        actions. Used by specific handlers that depend on completion of
        certain actions before they can proceed. For example State Depended
        handlers that trigger only when specific actions have been performed
        by other handlers.

    Why performed uses InstructionType and not str:
        Using InstructionType provides type safety, IDE autocompletion and
        semantic clarity. It is also extensible - custom handlers can introduce
        their own InstructionType subclass values without touching core objects.
        This enables rich monitoring and auditing capabilities for phantom handlers.

    Why performed is separate from processed_handlers:
        processed_handlers is a mechanical counter for loop termination.
        performed is a semantic log of what actions were performed. Conflating
        the two would make it impossible to distinguish between "how many
        handlers ran" and "what specifically was performed" - two fundamentally
        different questions with different consumers.

    Attributes:
        - event:               The Event instance currently being processed.
        - instruction:         The Instruction associated with the current event.
                                Defines what actions should be performed.
        - snapshot:            Optional Snapshot created by a backup operation.
                                Set by Backuper-like handlers after creating a backup.
        - processed_handlers:  Counter of non-phantom handlers that have completed
                                their work for this event.
        - handlers_count:      Total number of handlers expected to process this event.
                                Decremented by phantom handlers and skipping handlers.
        - performed:                Sequence of InstructionType values representing
                                completed actions. Used by phantom handlers for
                                monitoring and auditing purposes.

    Notes:
        - EventContext does not implement any business logic or decision-making.
            All behavioral logic resides in the handlers.
        - performed sequence order reflects the order in which actions were completed.
            This can be used by phantom handlers to understand processing history.
        - Custom handlers should append their own InstructionType subclass values
            to performed to signal completion of custom actions.
        - Phantom handlers must decrement handlers_count on first contact to
            avoid infinite loop caused by multiple phantom handlers waiting
            for each other to finish.
    """

    event: Event
    instruction: Instruction
    snapshot: Optional[Snapshot] = None
    processed_handlers: int = 0
    handlers_count: int = 0
    performed: list[InstructionType] = field(default_factory=list)
