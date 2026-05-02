from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

from .event import EventType


class LevelType(StrEnum):
    """
    Dispatcher-layer object LevelType is a semantic classification
    label used to mark the level of a file system object change.
    It does not perfomr any evaluation or decision-making on its own.

    It is intended to provide a consistend way to describe
    the signature of an event in the context of a specific object.

    For example:
        reading a sensitive file such as /etc/passwd may be classified as a SAFE,
        while modifications to the same file would be classified as CRITICAL or UN-SAFE,
        even though both are devired from different underlying file system events.

    Notes:
        - LevelType is used only for tagging and categorization of events after they are
            produced by the file system event layer.
        - It does not define rules, logic or heuristics for determining event severity.
            This responsibility belongs to external processing components.

    Marks:
        SAFE - expected, non-risky operations
        INFO - neutral informational changes
        WARNING - potentially important but not harmful
        SUSPICIOUS - unexpected or potentially risky behavior
        CRITICAL - high-impact or potentially or security-relevant changes
    """

    SAFE = "safe"
    INFO = "info"
    WARNING = "warning"
    SUSPICIOUS = "suspicious"
    CRITICAL = "critical"


@dataclass(slots=True, frozen=True)
class Instruction:
    """
    An Immutable, dispatcher-layer object that represents a pre-defined
    behavioral contract for a specific class of file system events.

    An instruction is not created in response to a single event -
    it is defined in advance by the user or system configuration,
    and describes hat actions should be taken when a matching event occurs.

    InstructionManager is responsible for matching incoming Events against
    all registered Instructions in InstrcutionsStorage and
    selecting the most appropriate one. If no match is found in storage,
    a default Instruction is used.

    Unlike Event (which describes what happened), Instrcution describes what
    should happen as a consequence. It is the bridge between observation and action
    in the pipe line.

    Attributes:
        - event_types:    Collection of EventType values this instruction applies to.
                            An incoming event matches if its type is in this collection.
        - paths:         Glob patterns of filesystem paths this instruction applies to.
        - level:         Semantic classification of the event path.
                            Used by handlers to decide how to present or react to the event.
        - should_log:    Whether the matched event should be recorded by the Logger (default=True).
        - should_backup: Whether a Snapshot should be created by the Backuper (default=False).
        - should_notify: Whether the user should be notified via a Notifier (default=False).
        - rollback_target: Optional reference to a specific Snapshot to roll back to (default=None).
                            Notifier will offer the user avialable options.

    Notes:
        - Instruction is frozen because behavioral contracts must not change at runtime.
            Any modifications requires creating a new instruction.
        - Instruction does not contain processing logic. it is a pure data object.
        - Multiple Intructions may match a single Event, Resolution strategy
            (e.g. priority, first-match) is the responsibility of InstructionManager.
        - If you use Custom Event Type you need to provide it inherited from EventType and
            add handlers that supports that custom event type.
        - rollback_target attribute value must be Hashable format object
            that points to the snapshot in the snapshots_storage
    """

    event_types: Optional[Sequence[EventType]] = None
    paths: Optional[Sequence[str]] = None
    level: Optional[LevelType] = None
    should_log: bool = True
    should_backup: bool = False
    should_notify: bool = False
    rollback_target: Optional[Hashable] = None
