from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence

from ...domain import Event, Instruction
from ..protocols import AssemblyProtocol, BluePrintProtocol


class BaseInstructionRegistry(AssemblyProtocol, BluePrintProtocol):
    """
    Abstract base class for all instruction registry implementations.

    BaseInstructionRegistry is simultaneously responsible for two things:
        1. Matching — given an incoming Event, return the most appropriate
            Instruction for it. This is the only thing the pipeline ever
            asks of a registry.
        2. Disclosure — exposing registry state through show(). This is the
            guaranteed method every port that adopts the Registry Agreement
            carries, giving the management layer a reliable entry point
            regardless of which implementation is active.

    Why only get() and show():
        The Dispatcher is the sole pipeline object that ever touches a
        registry at runtime, and all it ever needs is a matching Instruction
        for a given Event. add(), delete(), clear(), were never pipeline
        requirements — they were management requirements that leaked
        into the port and imposed a rigid API on every implementation
        regardless of whether that implementation even supports them.
        BluePrintProtocol fixes this: every implementation now surfaces its
        own management interface through blueprint(), where it declares
        exactly the methods it actually has — no more, no less. Two
        registries with completely different management models can coexist
        behind the same port without either being forced to lie about
        what it offers.

        show() is the one exception: it stays on the port as the guaranteed
        baseline every registry exposes. Its arguments — what it accepts,
        what it returns based on those arguments — are declared by each
        implementation in its own MethodSpec inside blueprint(). An
        implementation that requires no filtering declares a MethodSpec with
        no requirements; one that offers filtering declares the parameters it
        needs. Either way, the management layer always finds show() and always
        reaches it through the standard BluePrint flow.

    show() as a Registry Agreement:
        No BaseRegistry exists in this codebase — nor is one planned.
        Registry ports differ enough in pipeline role, structure, and observer
        contract that unifying them under a shared abstract base would trade
        clarity for a constraint that solves nothing the pipeline actually needs.

        BluePrintProtocol is the contract between ports that want their
        implementations to interact with management tools. show() is a
        narrower declaration on top of that: any port that carries show()
        is identifying itself as belonging to the registry role — signalling
        that its implementations can, at minimum, expose their state to the
        management layer. That is the Registry Agreement: an informal
        convention between ports that share that role, not a formal law
        enforced by shared inheritance.

        Declaring show() on the port is not strictly required by design —
        BluePrintProtocol alone already ensures management tools can reach
        the implementation. show() is declared here as a cushion: the abstract
        method forces every concrete implementation to provide it, preventing
        anyone from building an implementation that silently omits it.

        Every port that carries show() upholds the agreement by existing.
        That is all the enforcement this convention needs.

    Who BaseInstructionRegistry is for:
        The Dispatcher calls get(). Management-layer objects such as
        RegistryManager reach show() through the BluePrint flow as a guaranteed
        entry point and interact with everything else through blueprint(). No
        other pipeline object ever holds a reference to a registry directly.
        BaseInstructionRegistry must never appear in any implementation's
        Configure requirements — it belongs to the Observer environment and
        is assembled by the Assembler itself.

    Instruction Return Protocol:
        get() must always return a valid Instruction. If no registered
        Instruction matches the incoming Event, the implementation must fall
        back to a default Instruction — either determined automatically or
        supplied by the client during configuration. get() never returns
        None and never raises.

    Persistence Advisory:
        Implementations are strongly advised to persist registry state after
        every modification. The Dispatcher only ever reads via get() — it
        never modifies. But management sessions running through the Overseer
        may modify the registry concurrently with active observation. A crash
        at any point must not result in data loss.

        Recommended approach:
            - Persist after every modification.
            - Use atomic writes (write to a .vakt.tmp file, then rename) to
                avoid corrupting the registry on crash.
            - Restore persisted state during __init__.

    Current State — Temporary Pragmatic Contract:
        Everything described here — including show() on the port, the Registry
        Agreement, and how the management layer currently reaches registry
        implementations — is a temporary, pragmatic arrangement. It ships
        because the project cannot wait any longer. show() itself may not
        survive the future redesign of the management system.

        The full picture of what is coming — @blueprint() decorator,
        formal shared law, global role plugins, MethodSpec evolution — is
        documented in BluePrintProtocol. That is where the promise lives.

    Notes:
        - get() is called by the Dispatcher inside its thread. Must never raise.
        - show(**kwargs) is invoked exclusively through the BluePrint flow —
            never called directly by the management layer. kwargs are the
            resolved output of the implementation's MethodSpec for show(),
            provided by the client during the management session.
        - Thread-safety for get() is not required by default — the Dispatcher
            only reads, and management modifications occur in controlled
            Overseer sessions.
        - Graceful shutdown is handled by upper-layer objects, not the registry.
        - Must never propagate exceptions to the caller. All errors must be
            caught and handled internally.
    """

    @abstractmethod
    def get(self, event: Event) -> Instruction:
        """
        Returns the most appropriate Instruction for the given Event.

        Applies the implementation's matching strategy against all registered
        Instructions. Falls back to a default Instruction if no registered
        Instruction matches — never returns None, never raises.
        Called by the Dispatcher within its thread.
        """
        ...

    @abstractmethod
    def show(self, **kwargs) -> Sequence[dict]:
        """
        Returns the raw metadata of registered Instructions.

        Invoked through the BluePrint flow — kwargs are the resolved output
        of the implementation's MethodSpec for this method, provided by the
        client during the management session. Each dict reflects the full
        internal representation of one registered Instruction as the
        implementation stores it — the same structure the implementation
        would use to reconstruct it. Returns an empty sequence if the registry
        contains no Instructions or no entries match the provided criteria.
        Must never raise.
        """
        ...
