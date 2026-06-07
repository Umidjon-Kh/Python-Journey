from __future__ import annotations

from collections.abc import Sequence

from ..core import (
    BaseHandler,
    BaseInstructionRegistry,
    BasePathLocker,
    BaseSnapshotsRegistryStore,
    BaseWatcher,
    PortProtocol,
)


class InfraContainer:
    """
    A static registry that holds all available infrastructure implementations
    grouped by their role and port abstractions.

    InfraContainer acts as a bridge between the Assembler and infrastructure
    implementation developers. It does not create, manage, or instantiate
    anything - it simply holds references to all registered implementation
    classes, giving the Assembler the ability to discover, present, and
    instantiate them on demand.

    How it works:
        A developer creates a concrete implementation of any core port and
        registers it by adding the class directly to the corresponding sequence
        in this file. Not instances - classes. The Assembler is solely responsible
        for instantiation, gathering all requirements from itself and from the
        client. InfraContainer serves purely as a registry that holds references
        to those implementations. This is intentional - implementation developers
        never need to touch the Assembler internals to make their work visible and
        usable. This follows the NYR (Not in Your Responsibility) principle.
        The author of this project (that is me, Umidjon) strongly dislikes
        unnecessary churn — changing or rewriting entire sections of code
        for trivial reasons.!

    Why InfraContainer is not instantiated and not a dataclass:
        InfraContainer was never designed to be an object - it is a bridge registry,
        not something that exists anywhere outside the Assembler itself. Even if an
        instance were created, it would provide no benefit and would only introduce
        unnecessary initialization overhead. A plain class keeps it simple,
        transparent, and easy to modify without any additional complexity.

    Why HeartBeater implementations are not stored here:
        Even though HeartBeater implementations live in the infrastructure layer,
        their instantiation logic is hardcoded directly into the Assembler - because
        HeartBeater does not belong to the Observer environment. It is owned by the
        Overseer (the server itself) and must never be presented to the client as a
        choice. HeartBeater does not follow the Port Protocol - the Assembler selects
        the appropriate implementation automatically based on the current platform,
        not the client.

    Why helpers are stored sperately in helpers: dict[str, Sequence]:
        At first glance this separation seems unnecessary - but its value becomes
        clear at scale. It cleanly separates main pipeline objects (Watcher,
        Handler, InstructionRegistry) from objects that assist the pipeline without
        participating in it directly.

        More importantly, it enables open-ended extensibility without touching the
        Assembler. The Assembler has no hardcoded knowledge of helper port types -
        that would violate the Open/Closed principle. When a new helper port is
        introduced, the developer simply adds a new key to the helpers dictionary under
        the port name, with its implementations as the value sequence. The Assembler
        will find them by that key when any object declares that port in its
        requirements - no changes to Assembler internals required.

        The only contract: all helpers port implementations must inherit from
        PortProtocol so the Assembler can work with them uniformly - discovering
        their requirements, presenting them to the client, and instantiating them
        correctly. The dict key must match the port name so the Assembler can locate
        all implementations for a given helper port when any object declares it
        in its requirements.
    """

    watchers: Sequence[type[BaseWatcher]] = []
    handlers: Sequence[type[BaseHandler]] = []
    instruction_registries: Sequence[type[BaseInstructionRegistry]] = []
    helpers: dict[str, Sequence[type[PortProtocol]]] = {
        BasePathLocker.__name__: [],
        BaseSnapshotsRegistryStore.__name__: [],
    }
