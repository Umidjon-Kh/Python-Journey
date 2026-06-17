from __future__ import annotations

from collections.abc import Sequence

from ..core import (
    AssemblyProtocol,
    BaseHandler,
    BaseInstructionRegistry,
    BasePathLocker,
    BaseSnapshotsRegistryStore,
    BaseWatcher,
)


class InfraContainer:
    """
    A static registry that holds all available infrastructure implementations
    grouped by their role and port abstractions.

    InfraContainer acts as a bridge between the Assembler and infrastructure
    implementation developers. It does not create, manage, or instantiate
    anything — it simply holds references to all registered implementation
    classes, giving the Assembler the ability to discover, present, and
    instantiate them on demand.

    How it works:
        A developer creates a concrete implementation of any core port and
        registers it by adding the class directly to the corresponding sequence
        in this file. Not instances — classes. The Assembler is solely responsible
        for instantiation, gathering all requirements from itself and from the
        client. InfraContainer serves purely as a registry that holds references
        to those implementations. This is intentional — implementation developers
        never need to touch the Assembler internals to make their work visible and
        usable. This follows the NYR (Not in Your Responsibility) principle.
        The author of this project (that is me, Umidjon) strongly dislikes
        unnecessary churn — changing or rewriting entire sections of code
        for trivial reasons.

    Why InfraContainer is not instantiated and not a dataclass:
        InfraContainer was never designed to be an object — it is a bridge registry,
        not something that exists anywhere outside the Assembler itself. Even if an
        instance were created, it would provide no benefit and would only introduce
        unnecessary initialization overhead. A plain class keeps it simple,
        transparent, and easy to modify without any additional complexity.

    Why HeartBeater implementations are not stored here:
        Even though HeartBeater implementations live in the infrastructure layer,
        their instantiation logic is hardcoded directly into the Assembler — because
        HeartBeater does not belong to the Observer environment. It is owned by the
        Overseer (the server itself) and must never be presented to the client as a
        choice. HeartBeater does not follow the AssemblyProtocol — the Assembler
        selects the appropriate implementation automatically based on the current
        platform, not the client.

    Helpers Markup Protocol:
        Helpers are stored in a dedicated dict rather than flat sequences alongside
        watchers and handlers for two reasons: it cleanly separates main pipeline
        objects (Watcher, Handler, InstructionRegistry) from those that assist the
        pipeline without participating in it directly, and it gives the Assembler
        a uniform way to discover helper implementations for any port by key —
        without hardcoding any specific port type into its internals.

        Each key in the helpers dict is a tuple[str, type]:

            str — the role that implementations of this group play in the system.
                An empty string signals no special role beyond being a helper.
                A named role such as "registry" signals that implementations in
                this group belong to the registry family — they carry show() and
                uphold the Registry Agreement. Management-layer objects use this
                role to identify which helper groups they can interact with and
                what to expect from them.

            type — the port class itself. The Assembler uses it to locate all
                registered implementations for a given port when any pipeline
                object declares that port in its Configure requirements. It also
                performs issubclass(cls, BluePrintProtocol) on this value to
                determine whether implementations in this group are capable of
                interacting with management-layer objects — without the Assembler
                needing to know anything specific about the port.

        Adding a new helper port requires only one action: add a new entry to the
        helpers dict with the appropriate ("role", PortClass) key and an empty
        sequence as its value. No changes to the Assembler internals required —
        it finds the group by port class and works with it uniformly. The only
        contract: all helper port implementations must inherit from AssemblyProtocol.
    """

    watchers: Sequence[type[BaseWatcher]] = []
    handlers: Sequence[type[BaseHandler]] = []
    instruction_registries: Sequence[type[BaseInstructionRegistry]] = []
    helpers: dict[tuple[str, type], Sequence[type[AssemblyProtocol]]] = {
        ("", BasePathLocker): [],
        ("registry", BaseSnapshotsRegistryStore): [],
    }
