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

    Current State — Informal Contracts:
        Everything you see in this file — and everything connected to how
        management objects interact with implementations — may change. The
        project has taken too long already, and I (Umidjon) cannot afford
        to delay delivery any further.

        For now, all parties that build management objects work under
        informal, unwritten contracts between themselves and the
        implementations they manage. There is no enforced shared law, no
        automatic wiring, no global roles. blueprint() is filled manually
        by the implementation. It works — but it is NYR, and I know it.

    What Is Coming — I Promise:
        I will completely redo how BluePrints and management interaction
        work. When that time comes, here is what lands:

        - @blueprint() decorator — methods that carry it will register
            themselves in the BluePrint automatically. No more building
            it by hand. Full customisation and overrides built in.
        - A formal shared law — a concrete contract that defines exactly
            what is permitted and what is not between implementations and
            the management objects that talk to them. Anyone consuming the
            API will know what to expect without reading source.
        - Global role plugins — RegistryPersonality, InvokerPersonality,
            and others. A port declares its role; the framework wires the
            appropriate management behaviour automatically.
        - MethodSpec evolution — the ability to declare what must happen
            after a method completes: a successful update emits a view
            refresh command, a deletion triggers a cleanup hook, and so on.
            The view does not rebuild from scratch. MethodSpec becomes a
            full lifecycle declaration, not just a requirements contract.

        Until then: what is here is interim. It is correct enough to ship.
        It is not what this system deserves.

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
        - All methods exposed through blueprint() must declare proper named
            parameters — never a raw dict as the sole argument. The management
            layer invokes them as method(**resolved), where resolved is the
            output of MethodSpec.resolve(). A method signature must therefore
            match the keys declared in its MethodSpec requirements exactly —
            plain arguments and **kwargs are permitted, a raw dict is not.
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
