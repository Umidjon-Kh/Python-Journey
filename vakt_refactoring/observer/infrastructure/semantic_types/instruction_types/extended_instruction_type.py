from __future__ import annotations

from ....core import InstructionType


class ExtendedInstructionType(InstructionType):
    """
    Extended instruction types that extend the base InstructionType class
    with new, specific  instructions. These belongs to specific processors
    (handlers) that perform or responsible for executing the corresponding task.

    All types provided are not considered platform specific and can be used
    on different platforms with different handlers that are semantically
    related to those instruction types in some way.

    If you need to add new objects that are not platform-specific,
    it is recommended to add them to this class, thereby extending it.
    All flags of a given class will be automatically accepted
    and considered cross-latform.

    Notes:
        - Fully compatible with Instruction.types: Sequence[InstructionType]
            because ExtendedInstructionType inherits from InstructionType.
    """

    RESTORE = "restore"
    ANTIMUTATE = "antimutate"
