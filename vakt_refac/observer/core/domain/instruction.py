from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

from .event import EventType


class LevelType(StrEnum):
    """
    Dispatcher-layer object LevelType is a semantic classification
    label used to mark the level of a file system object change.
    It does not perform any evaluation or decision-making on its own.

    It is intended to provide way to describe
    the signature of an event in the context of specific object,

    For example:
        reading a sensitive file such "/etc/passwd" may be classified as SAFE,
        while modifications to the same file would be classified as a CRITICAL or SUSPICIOUS
        event though both are derived from different underlying file system events.

    Notes:
        - LevelType is used only for tagging and categorization of events after they are
            produced by the file system event layer.
        - It does not define rules, logic or heuristics for determining event severity.
            This is responsibility belongs to external processing components.

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


class InstructionType(StrEnum):
    """
    Domain-level instruction action types.
    StrEnum allows comparing with plain strings which is useful
    for matching and human-readable serialization.

    InstructionType defines what actions should be performed
    when a matching events occurs. It is designed to be extended
    with custom action types for specific use cases.

    For example:
        - LOG:      - record the event via Logger handlers
        - BACKUP:   - create a snapshot via Backuper handler
        - NOTIFY:   - notify the user via Notifier handler

    Notes:
        - InstructionType is a StrEnum that defines the minimal set of
            actions that can be performed on a file system event.
        - It is designed to be extended. Custom enumerations for example:
            CustomInstructionType - may introduce additional action types
            aligned with the capabilities of custom handlers.
        - Such extensions are not automatically supported by the core processing
            pipeline, Consumers introducing custom instruction types are
            responsible for providing compatible handlers that explicitly
            recognize and handle those extended action types.

        In other words, an InstructionType is similar to an EventType object,
        but it serves to describe what to do with a specific file system event.
    """

    LOG = "log"
    BACKUP = "backup"
    NOTIFY = "notify"


@dataclass(slots=True, frozen=True)
class Instruction:
    """
    An Immutable, dispatcher-layer object that represents a pre-defined
    behavioral contract for a specific class of file system events.

    An Instruction is not created in response to a single event -
    it is defined in advance by the user or system configuration,
    and describes what actions should be taken when matching event occurs.

    Unlike Event (which describes what happened), Instruction describes what
    should happen as a consequence. It is the bridge between observation
    and action in the pipeline.

    Attributes:
        - event_types: Collection of EventType values this instruction applies to.
                        An incoming event matches if its type is in the collection.
                        If None, instruction applies to all event types.
        - paths:       Glob patterns of file system paths the instruction applies to.
                        If None, instruction applies to all paths.
        - level:       Semantic classification of event.
                        Used by handlers to decide how to present or react to the event.
        - shoulds:     Collection of InstructionType values that define what actions
                        should be performed when a matching event occurs.
                        If None, no actions are performed.

    Notes:
        - Instruction is frozen because behavioral contracts must not change at runtime.
            Any modification requires creating a new Instruction.
        - Instruction does not contain processing logic. It is a pure data object.
        - Multiple Instructions may match a single event. Resolution strategy
            (e.g. priority, first-match) is the responsibility of InstructionRegistry.
        - If you use a Custom EventType you need to provide it inherited from EventType and
            add handlers that support those custom event types.
        - If you use a Custom InstructionType you need to provide it inherited from
            InstructionType and add handlers that support those custom instruction types.
        - In path glob patterns field if you want to apply instruction to all
            objects in a directory use "/*" at the end of the directory name.
            If you want to apply instruction to all objects recursively use "/**".

    Example:
        event_types: Sequence[FILE_MODIFIED, DIR_RENAMED]
        paths:       Sequence["/etc/passwd", "/usr/local/*"]
        level:       LevelType.SUSPICIOUS
        shoulds:       Sequence[InstructionType.LOG, InstructionType.BACKUP]
    """

    event_types: Optional[Sequence[EventType]] = None
    paths: Optional[Sequence[str]] = None
    level: LevelType = LevelType.INFO
    types: Optional[Sequence[InstructionType]] = None
