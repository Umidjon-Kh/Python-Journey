from __future__ import annotations

from ....core import InstructionType


class ExtendedInstructionType(InstructionType):
    """
    Extended instruction types for platform-specific handlers.

    Extends the base InstructionType with additional action semantics
    that are not part of the minimal cross-platform contract but are
    required by concrete handler implementations.

    Notes:
        - Fully compatible with Instruction.types: Sequence[InstructionType]
            because ExtendedInstructionType inherits from InstructionType.
        - BACKUP and LOG remain in core InstructionType as the minimal
            cross-platform baseline.
    """

    ALERT = "alert"
    QUARANTINE = "quarantine"
    RESTORE = "restore"
