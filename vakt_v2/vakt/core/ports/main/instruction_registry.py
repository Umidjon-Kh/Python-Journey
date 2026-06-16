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
        2. Disclosure — returning the complete raw metadata of all registered
            Instructions on demand, with no arguments required. This is the
            guaranteed baseline that any management-layer object can always
            rely on, regardless of which implementation is currently active.

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

        show() is the one exception: it stays on the port because it is
        universal — every registry, regardless of its internal model, is
        capable of returning its raw data with no arguments. It gives
        management-layer objects a guaranteed baseline they can always call
        without knowing anything about the specific implementation. The moment
        arguments or filtering become involved, that logic belongs in a
        dedicated method exposed through blueprint() instead.

    Who BaseInstructionRegistry is for:
        The Dispatcher calls get(). Management-layer objects such as
        RegistryManager call show() as a guaranteed baseline and interact
        with everything else through blueprint(). No other pipeline object
        ever holds a reference to a registry directly. BaseInstructionRegistry
        must never appear in any implementation's Configure requirements —
        it belongs to the Observer environment and is assembled by the
        Assembler itself.

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

    Notes:
        - get() is called by the Dispatcher inside its thread. Must never raise.
        - show() accepts no arguments. If an implementation has multiple
            presentation modes or filtering variations, the recommended approach
            is to expose a dedicated mode-setter method through blueprint()
            that changes how show() behaves — not to add arguments to show()
            itself. This preserves the universal contract.
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
    def show(self) -> Sequence[dict]:
        """
        Returns the complete raw metadata of all registered Instructions.

        Each dict in the returned sequence reflects the full internal
        representation of one registered Instruction as the implementation
        stores it — the same structure the implementation would use to
        reconstruct it. Returns an empty sequence if the registry contains
        no Instructions. Must never raise.
        """
        ...
