from abc import ABC, abstractmethod

from ...domain import Configure


class AssemblyProtocol(ABC):
    """
    Lightweight internal interface that captures the common contract
    shared by all port implementations. Its sole purpose is to eliminate
    duplication by defining once the methods every port must provide —
    __init__, requirements(), and describe() — so that port authors do not
    repeat the same explanations across every implementation.

    The Assembler has no knowledge of AssemblyProtocol and works entirely
    with concrete classes. This protocol is purely a convenience that
    keeps the codebase DRY and self-documenting.
    """

    @abstractmethod
    def __init__(self, configure: Configure) -> None:
        """
        Initializes the port with a resolved dependency contract.

        Accepting a single Configure object means the Assembler never
        deals with arbitrary constructor signatures. All dependencies
        are declared in one place, supplier roles are strictly separated
        (internal and client), and the Assembler simply populates the
        contract before calling this constructor.

        This design spares both the Assembler and port authors from the
        combinatorial complexity of varying signatures across different
        implementations. A validated Configure is the single source of truth.

        For the full dependency contract see Configure class documentation.
        """
        ...

    @classmethod
    @abstractmethod
    def requirements(cls) -> Configure:
        """
        Returns the Configure dependency contract for this implementation.

        Defines precisely which internal objects the Assembler must supply
        and which parameters require explicit client input (with description
        and conversion/validation callable).

        Must follow the DECLARATION PROTOCOL defined in Configure:
            - internal_reqs must never include resources that require direct
                client input. Such resources belong in client_reqs.
            - Two forms are permitted in internal_reqs for resources that
                indirectly involve the client:
                "port:PortName" — client chooses the implementation.
                "concrete:PortName::ImplementationName" — implementation is
                hard-wired; Assembler resolves its client_reqs on behalf of
                this one.
            - Main pipeline objects must never appear in any requirements.

        For full details see Configure class documentation.
        """
        ...

    @classmethod
    @abstractmethod
    def describe(cls) -> str:
        """
        Returns a one-sentence description of this implementation's purpose.

        Used by the Assembler when presenting available implementations
        to the client. Should answer: "What does this implementation do
        and what is it intended for?"
        """
        ...
