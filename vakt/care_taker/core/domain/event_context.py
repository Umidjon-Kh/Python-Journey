from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .event import Event
from .instruction import Instruction
from .snapshot import Snapshot


@dataclass(slots=True)
class EventContext:
    """
    A mutable dispatcher-layer object that represents the processing context
    of a single file system change.

    The EventContext is instantiated by the dispatcher after an event is retrieved
    from the buffer. The dispatcher puts event into an EventContext and enriches it with
    transient processing states. This enables components to reason about what has already
    happened and what has not yet been processed yet within the scope of the current event.

    EventContext instance are strictly ephemeral. They exist only during
    the lifecycle of event handling - from the moment the dispatcher pulls
    the event from the buffer until processing is complete. After that,
    the instance is discarded.

    Attributes:
        - event:              The Event instance currently being processed.
        - instruction:          The instruction associated with the current event.
        - backed_up:          Flag that indicates whether the object was backed up.
        - rolled_back:        Flag that indicates whether the object was rolled back.
        - snapshot:           Optional field that needed only to represent snapshot
                                if it was created by Backuper for this event.
        - processed_handlers: The counter that serves to let give knowledge about
                                how many handlers processed their work with current event.
        - handlers_count:     The count of how many handlers can process with current event.

    Notes:
        - Mutability is intentional. Handlers use the EventContext to track progress
            and mark which actions have already been performed. Each handler may
            update specific fields to indicate completion of its own responsibility.
        - EventContext does not implement any business logic or decision-making.
            All behavioral logic resides in the handlers. The object acts purely as a
            state carrier reflecting the current processing status of the event.
        - Both (processed_handlers and handlers_count) serves to give knowledge
            about how many handlers processed with current event for specific handlers variations.
    """

    event: Event
    instruction: Instruction
    backed_up: bool = False
    rolled_back: bool = False
    snapshot: Optional[Snapshot] = None
    processed_handlers: int = 0
    handlers_count: int = 0
