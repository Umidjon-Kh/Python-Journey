from abc import ABC, abstractmethod

from ...domain import Configure


class PortProtocol(ABC):
    """
    Lightweight internal interface that captures the common contract
    shared by all port implementations. Its sole purpose is to eliminate
    duplication by defining once the methods every port must provide —
    __init__, requirements(), and describe() — so that port authors do not
    repeat the same explanations across every implementation.

    The Assembler has no knowledge of PortProtocol and works entirely
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

    @abstractmethod
    def requirements(self) -> Configure:
        """
        Returns the Configure dependency contract for this implementation.

        Defines precisely which internal objects the Assembler must supply
        and which parameters require explicit client input (with description
        and conversion/validation callable).

        Must follow the NYR (Not Your Responsibility) principle: internal_reqs
        must never include values that depend on client input. The only
        permitted exception is placing a concrete implementation class in
        internal_reqs — the Assembler will then resolve that implementation's
        own client requirements on behalf of this one.

        For full details see Configure class documentation.
        """
        ...

    @abstractmethod
    def describe(self) -> str:
        """
        Returns a one-sentence description of this implementation's purpose.

        Used by the Assembler when presenting available implementations
        to the client. Should answer: "What does this implementation do
        and what is it intended for?"
        """
        ...
