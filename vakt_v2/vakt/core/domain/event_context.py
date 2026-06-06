from __future__ import annotations

from dataclasses import dataclass, field

from .event import Event
from .instruction import Instruction, InstructionType


@dataclass(slots=True)
class EventContext:
    """
    A mutable processing-level object that represents the processing context
    of a single file system change.

    EventContext is instantiated by the Dispatcher after an event is retrieved
    from the buffer. It acts as a shared carrier that all handlers read
    from and write to during the processing lifecycle of a single event.

    Why mutable:
        Handlers use EventContext to track progress and mark which actions
        have already been performed. Each handler may update specific fields
        to inidicate completion of its own responsibility. Immutability would
        require handlers to return new objects on every change which would
        introduce unnecessary complexity and coupling.

    Lifecycle:
        EventContext is strictly ephemeral. It exists only during the lifecycle
        of event handling - from the moment the Dispatcher pulls the event from
        the buffer until all handlers have finished processing. After that,
        the instance disappears.

    Handlers Loop Mechanics:
        - processed_handlers: increment b each non-phantom handler after
            completing its work. Used by the Dispatcher loop to determine
            when all handlers have finished.
        - handlers_count: total number of handlers that will process this event.
            Decremented by phantom handlers on first contact to exclude
            themselves from the termination condition. Used together with processed_handlers
            to determine loop termination (prevents infinite processing by phantom handlers).
        - performed: a sequence of InstructionType values that represent publicly
            completed actions. Not every handler appends to performed - only those
            whose completion needs to be observed by other handlers as a dependency
            signal. For example, BackupInvoker appends InstructionType.BACKUP so that
            SnapshotsRotator can check whether a backup was actually created before acting.
        - metadata: an open key-value buffer for inter-handler communication.
            Handlers may read and write arbitrary data keyed by any hashable value.
            This is the primary channel for passing rich results between handlers.
            For example, Antimutator stores the acquired lock under its own key so
            that an EndRunner handler can later either prompt the user to decide
            whether to release the locked object or automatically release it after
            a set period.

    Why performed uses InstructionType and not str:
        Using InstructionType provides type safety, IDE autocompletion and
        semantic clarity. It is also extensible - custom handlers can introduce
        their own InstructionType subclass values without touching core objects.
        This enables rich monitoring and auditing capabilities for phantom handlers.

    Why performed is separate from processed_handlers:
        processed_handlers is a mechanical counter for loop termination.
        performed is a semantic log of what actions were publicly signaled.
        Conflating the two would make it impossible to distinguish between
        "how many handlers ran" and "what specifically was performed" -
        two fundamentally different questions with different consumers.

    Why metadata instead of dedicated fields for handler results:
        Dedicated fields for every possible inter-handler result would couple
        EventContext to specific handler implementations and force every
        intermediate result into the typed domain model. metadata is an untyped
        open playground that allows any handler to store and retrieve rich
        structured data without modifying core domain objects. Handlers
        are responsible for defining their own key conventions to avoid
        accidental collisions with other handlers.

    Attributes:
        - event:              The Event instance currently being processed.
        - instruction:        The Instruction associated with the current event.
                                    Defines what actions should be performed.
        - processed_handlers: Counter of non-phantom handlers that have completed
                                    their work for this event.
        - handlers_count:     Total number of handlers expected to process this event.
                                    Decremented by phantom handlers on first contact.
        - performed:          Sequence of InstructionType values representing
                                    publicly completed actions that other handlers
                                    may depend on as a signal before proceeding.
        - metadata:           Open key-value buffer for inter-handler communication
                                    and temporary per-event state storage. Handlers
                                    may use their class name as a key, a hash for
                                    private communication or any other hashable key.

    Notes:
        - EventContext does not implement any business logic or decision-making.
            All behavioral logic resides in the handlers.
        - performed sequence order reflects the order in which actions were signaled.
            This can be used by phantom handlers to understand processing history.
        - Custom handlers should append their own InstructionType subclass values
            to performed to signal completion of custom actions that other
            handlers may depend on.
        - Phantom handlers must decrement handlers_count exactly once on first
            contact to avoid infinite loop caused by multiple phantom handlers
            waiting for each other to finish.
        - metadata is an open playground. Handlers are responsible for defining
            their own key conventions. No schema is enforced by EventContext.
            All data stored in metadata is ephemeral and exists only during
            the lifecycle of a single event.
    """

    event: Event
    instruction: Instruction
    handlers_count: int
    processed_handlers: int = field(default=0, init=False)
    performed: list[InstructionType] = field(default_factory=list, init=False)
    metadata: dict = field(default_factory=dict, init=False)
