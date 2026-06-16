from abc import ABC, abstractmethod

from ...domain import Configure


class AssemblyProtocol(ABC):
    """
    The common assembly contract that every Assembler-managed implementation
    must satisfy.

    AssemblyProtocol exists for one reason: the Assembler must be able to
    instantiate, introspect, and present any implementation without knowing
    anything specific about it. Three methods make this possible —
    __init__, requirements(), and describe() — and AssemblyProtocol defines
    them once so that implementation authors do not repeat the same contract
    across every class.

    The Assembler works exclusively with concrete classes and has no
    awareness of AssemblyProtocol itself. The protocol is a shared
    authoring convenience, not a runtime mechanism.
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
