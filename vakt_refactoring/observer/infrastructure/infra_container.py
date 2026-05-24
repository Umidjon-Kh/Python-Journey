from __future__ import annotations

from collections.abc import Sequence

from ..core import (
    BaseHandler,
    BaseHeartBeater,
    BaseInstructionRegistry,
    BasePathLocker,
    BaseSnapshotsRegistryStore,
    BaseWatcher,
)


class InfraContainer:
    """
    A static registry that holds all available infrastructure
    implementations grouped by their port abstraction.

    InfraContainer acts as a postman - it does not create, manage
    or instantiate anything. It simply carries registered implementations
    and makes them available to any client that needs to know what
    implementations are available.

    How it works:
        A developer creates a concrete implementation of any core port
        and registers it by adding the class to the corresponding
        sequence directly in this file. No instantiation, no passing
        objects around - just a class reference placed in the right list.

        Any client such as a GUI, CLI or external management tool reads
        from InfraContainer directly, picks the implementations it needs
        and passes the chosen selection to Bootstrap as its environment
        for the assembly phase.

    Why a plain class and not a dataclass or instance:
        InfraContainer is not meant to be instantiated. It is a
        static carrier - a single well-known place where all available
        implementations live. Using a plain class with class-level
        attributes keeps it simple, transparent and easy to modify
        without any initialization overhead.

    Why classes and not instances:
        Bootstrap is responsible for instantiating implementations
        with the correct parameters during the assembly phase.
        Storing classes keeps InfraContainer decoupled from
        initialization details of each implementation.

    Notes:
        - InfraContainer does not validate implementations.
            It is the responsibility of the client to ensure that
            chosen implementations are compatible before passing
            them to Bootstrap.
        - All sequences are empty by default. Developers add
            their implementations by importing and placing them
            in the corresponding sequence in this file.
    """

    watchers: Sequence[type[BaseWatcher]] = []
    handlers: Sequence[type[BaseHandler]] = []
    heartbeaters: Sequence[type[BaseHeartBeater]] = []
    instruction_registries: Sequence[type[BaseInstructionRegistry]] = []
    snapshots_registry_stores: Sequence[type[BaseSnapshotsRegistryStore]] = []
    path_lockers: Sequence[type[BasePathLocker]] = []
