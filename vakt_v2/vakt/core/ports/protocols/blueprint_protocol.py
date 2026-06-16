from abc import ABC, abstractmethod

from ...domain import BluePrint


class BluePrintProtocol(ABC):
    """
    The plugin protocol that grants any port the ability to expose
    a managed public interface to the Overseer's management layer.

    BluePrintProtocol exists for one reason: the Assembler must have a
    reliable, uniform way to determine which implementation groups are
    capable of interacting with management-layer objects — such as
    RegistryManager — without knowing anything specific about the
    implementations themselves. A single issubclass check is all it takes.

    Unlike AssemblyProtocol — which the Assembler never explicitly checks
    for, simply working with its contract — BluePrintProtocol is known to
    the Assembler directly. It is the dividing line between implementations
    the Assembler treats as pure pipeline components and those it can offer
    to management-layer objects for client interaction.

    How the plugin works:
        Add BluePrintProtocol to a port's inheritance and every
        implementation of that port immediately inherits the obligation to
        produce a BluePrint. No changes to the Assembler internals required —
        it discovers the capability through issubclass at runtime. This is
        the Open/Closed principle in its most direct form: new manageable
        port families introduced without touching any existing machinery.

    Why only one method:
        blueprint() is the sole contract this protocol enforces. The actual
        business methods — register, unregister, restore, and whatever else
        an implementation exposes — live on the implementation itself, not
        on the protocol. BluePrint is the manifest that makes those methods
        discoverable and safely invokable by the management layer without
        any direct coupling to the implementation. The protocol has no
        business knowing what those methods are — BluePrint carries that
        responsibility entirely.

    Who BluePrintProtocol is for:
        Port classes only — not concrete implementations directly. A concrete
        implementation inherits the obligation implicitly by subclassing a
        port that already carries BluePrintProtocol. Adding BluePrintProtocol
        directly to a concrete implementation is a misuse of the pattern and
        breaks the layering contract this protocol was designed to enforce.

    Notes:
        - blueprint() is an instance method, not a classmethod. The management
            layer already holds the assembled instance — it calls blueprint()
            on it to open a management session, never before.
        - Every call to blueprint() must return a fresh BluePrint. Caching
            across sessions is never permitted — a stale BluePrint is a
            broken contract.
        - BluePrintProtocol carries no describe() — that obligation is already
            satisfied by AssemblyProtocol, which every manageable port inherits
            alongside this one. Repeating it here would be purely theatrical.
        - The Assembler is the only object that performs the issubclass check.
            No other component has any business inspecting BluePrintProtocol
            directly.
        - For full details about BluePrint, see its documentation.
    """

    @abstractmethod
    def blueprint(self) -> BluePrint:
        """
        Returns a fresh BluePrint manifest for this management session.

        Called once by the management layer at the start of each session
        to discover what methods this implementation exposes to the client.
        The returned BluePrint is the sole channel through which the
        management layer presents capabilities, collects client input, and
        safely invokes methods on this instance — all without any direct
        coupling to the implementation.

        Every call must produce a new BluePrint instance. The management
        layer holds it for the duration of a single session only — once
        the session ends, the BluePrint lives and dies with it.

        Must never raise.
        """
        ...
