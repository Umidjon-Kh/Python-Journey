from abc import ABC, abstractmethod

from ...domain.configure import Configure


class PortProtocol(ABC):
    """
    PortProtocol is an internal, lightweight interface that captures the common
    contract shared by all port implementations. Its sole purposeis to remove
    duplication by defining once the mthdos every port must provide - requirements(),
    describe(), and the constructor signature - so that the ports author (me) do not
    repeat the same explenations. The Assembler has no knowledge of PortProtocol and
    works entirely with concrete classes, the protocol is purely mine convenience
    that keeps the codebase DRY (Do not Repaet Yourself) and self-documenting.
    """

    @abstractmethod
    def __init__(self, configure: Configure) -> None:
        """
        Initializes the port with a resolved dependency contract.

        The constructor accepts a single Configure object so that the
        Assembler deals with arbitrary signatures. All dependencies
        are declared in one place, supplier roles are strictly seperated
        (internal and client), and the Assembler simply populates the contract.

        This design spares both the Assembler and the ports author (me) from the
        combinatorial complexity of "what and how an implementation receives".
        There is no need to account for optional parameters, positional arguments,
        or varying signatures across diferrent ports implementations. A validated
        Configure is the single source of thruth.

        For the full dependency contract and informations about Configure read
        Configure class documentation.
        """
        ...

    @abstractmethod
    def requirements(self) -> Configure:
        """
        Returns the Configure dependency contract.

        Defines precisely which internal objects of Assembler and
        client parameters (with validation/conversation) are required.
        Should follow NYR principle - internal requirements never include
        client-specific values but with one exception.
        For full information, it is recommended to read the documentation
        of the Configure class.
        """
        ...

    @abstractmethod
    def describe(self) -> str:
        """
        Returns a one-sentence description of the port implementation purpose.
        Used by the Overseer to present the implementation to the client.
        Answers the question: "What is this implementation and what is it intended for?"
        """
        ...
