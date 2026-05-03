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
    from the buffer. The dispatacher puts event into an EventContext and enriches it with
    transient processing states. This enables components to reason about what has already
    happened and what has not yet been processed yet within the scope of the current event.

    EventContext instance are strictly ephemeral. They exist only during
    the lifecycle of event handling - from the moment the dispatcher pulls
    the event from the buffer until processing is complete. After that,
    the instance is discarded.

    Attributes:
        - event:       The Event instance currently being processed.
        - instruction: The instruction associated with the current event.
        - backed_up:  Tombstone that defines backed up object of event or not.
        - rolled_back: Tombstone that defines rolled back object of event or not.
        - snapshot:    Optional field that needed only to represent snapshot
                        if it was created by Backuper for this event.

    Notes:
        - Mutability is intentional. Handlers use the EventContext to track progress
            and mark which actions have already been performed. Each handler may
            update specific fields to indicate completion of its own responsibility.
        - EventContext does not implement any business logic or decision-making.
            All behavioral logic resides in the handlers. The object acts purely as a
            state carrier reflecting the current processing status of the event.
    """

    event: Event
    instruction: Instruction
    backed_up: bool = False
    rolled_back: bool = False
    snapshot: Optional[Snapshot] = None
