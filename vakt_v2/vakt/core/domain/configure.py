from __future__ import annotations

from typing import Any, Callable


class Configure:
    """
    The dependency declaration contract between an AssemblyProtocol
    implementation and its two suppliers: the Assembler (internal) and
    the client (external).

    Configure is the single artifact that every AssemblyProtocol
    implementation must produce through its requirements() classmethod.
    It declares precisely what the implementation needs and from whom —
    nothing more, nothing less. The Assembler reads it, satisfies internal
    requirements from its own environment, collects client requirements
    through the Overseer, and calls resolve() to populate the contract
    before passing it to __init__. This is the entire assembly contract
    in one object.

    Why two separate fields:
        internal_reqs and client_reqs strictly partition all requirements.
        internal_reqs names resources the Assembler provisions from its own
        environment — shutdown_event, occupied_paths, or other implementations
        via the port: and concrete: prefixes. client_reqs names everything
        that requires a human response — values, paths, thresholds — paired
        with a description and a Callable that validates or converts the raw
        string input before it reaches the implementation.

    Why Configure avoids setattr and getattr:
        Configure is a declaration object, not a state container. Dynamic
        attribute setting would turn it into a mutable scratchpad, blurring
        the line between declaration and resolution and making attribute
        presence checks with hasattr the only way to know what has been
        supplied — fragile by design. Instead, resolve() delivers a clean,
        structured result directly into self.resolved, a public mapping the
        implementation reads from __init__ via configure.resolved["internal"]
        and configure.resolved["client"]. No setattr, no getattr, no hidden
        state — just a clear contract populated in one explicit call.

    Why _provided exists:
        The Assembler may need to surface the current provision state of
        client requirements back to the client mid-session — for example,
        to show what has already been supplied and what is still missing.
        _provided stores every raw client-supplied string under its
        requirement name, updated each time resolve() is called. client_reqs()
        reads from _provided so the Assembler can present each requirement
        alongside its current value, not just its description.

    Client Requirements Dictionary structure:
        client_reqs is dict[str, tuple[str, Callable[[str], Any]]]:
            - The str in the tuple is a human-readable description of the
                parameter — its purpose and expected value, presented to
                the client by the Assembler before they supply a value.
            - The Callable receives the client-supplied string, validates or
                transforms it, and must always return the result. The return
                value is what ends up in resolved["client"]. A Callable that
                returns None on success would silently replace the client value
                with None — always return the object itself.

    DECLARATION PROTOCOL:
        Implementations must never declare in internal_reqs any resource that
        requires an explicit client decision or direct client input. Such resources
        must always be declared in client_reqs. This is a hard requirement for
        correct instance creation — the Assembler cannot arbitrarily choose
        client-facing values without violating the NYR (Not Your Responsibility)
        principle.

        There are two permitted exceptions for resources that indirectly involve
        the client without requiring direct raw input:

        1. Port dependency — declared as "port:PortName":
            The Assembler presents all registered implementations of that port
            to the client and asks them to choose one. The chosen implementation
            is then instantiated and injected. The client selects the
            implementation, but never supplies raw values directly.

        2. Concrete implementation dependency — declared as
            "concrete:PortName::ImplementationName":
            The implementation hard-wires which dependency implementation to use.
            The Assembler takes full responsibility for instantiating it and
            recursively collecting its client_reqs on behalf of the outer
            implementation — without involving the client in the implementation
            choice itself.

        Both forms are valid in internal_reqs precisely because the client is
        never asked to supply raw values directly — the Assembler mediates the
        entire resolution process.

        Main pipeline objects (BaseWatcher, BaseHandler, BaseInstructionRegistry)
        must never appear in any requirements — neither as ports nor as concrete
        implementations. Only helper ports and their implementations are permitted.
        Main pipeline objects belong exclusively to the Observer environment and
        are assembled by the Assembler itself.

    Occupied Paths Protocol:
        Any implementation that declares occupied_paths in internal_reqs
        must follow this protocol strictly.

        Why occupied_paths exists and who it is for:
            Server components generate filesystem events as a natural side
            effect of their own operations — acquiring locks, creating backups,
            rotating snapshots, and so on. These self-generated events reach
            the Watcher just like any external change would. Whether the
            Watcher can tell the difference depends entirely on how deeply
            it integrates with the kernel.

            Watcher implementations that hook deep into the kernel's
            notification layer receive rich metadata about every event —
            including which process initiated it. Such implementations can
            identify self-generated events directly from that metadata and
            drop them without any external help.

            Watcher implementations that observe at the surface level —
            receiving only the path and the type of change, with no visibility
            into who within the server initiated it — have no such ability.
            They see a change and cannot tell whether it came from outside
            or from the server itself. occupied_paths is the shared contract
            that gives these surface-level Watchers the information they need:
            a live mapping of every path currently being operated on by the
            server. Before enqueuing any event, a surface-level Watcher checks
            occupied_paths — if the path is there, the event is self-generated
            and must be dropped silently.

        occupied_paths holds two distinct claim types side by side:

            Exact claims — direct path keys:
                occupied_paths[path] = count
                Signals that the object at this exact path is currently being
                operated on. count is a reference counter — more than one
                component may hold a concurrent claim on the same path.

            Recursive claims — nested under the "recursive" sentinel key:
                occupied_paths["recursive"][path] = count
                Signals that the object at this path and every descendant
                beneath it are currently being operated on. "recursive" is a
                safe sentinel: valid paths always start with "/" so no real
                path can ever collide with it. The inner dict follows the same
                reference-counting discipline as the outer one — count is
                decremented on release and the entry is deleted when it hits
                zero. When "recursive" itself becomes empty it is deleted from
                occupied_paths entirely, so the mapping never accumulates dead
                weight. Registering a recursive claim is always the caller's
                responsibility — the component that holds the exact claim on
                the same path never registers it on the caller's behalf.

        Vakt Suffix Rule:
            Never register a path that carries a .vakt.** suffix in
            occupied_paths. Always register the original clean path — the one
            that existed before any vakt-marking rename. When an object is
            renamed from file.txt to file.txt.vakt.lock on disk, the claim
            goes under "file.txt", not "file.txt.vakt.lock". Registering the
            suffixed name would silently break the Watcher's lookup — the
            Watcher strips the vakt suffix to recover the original path, and
            expects to find exactly that original path in occupied_paths.

            One exception: if a parent directory in the path already carries a
            .vakt.** suffix in its own name — meaning the parent itself is a
            vakt-marked object — then children of that parent may be registered
            under their full paths, vakt-marked parent segment included. The
            parent's marker is not the child's marker. A child born in a locked
            house is not itself the lock.

        Registering a claim — before starting any self-generated operation:

            Exact claim:
                occupied_paths[path] = occupied_paths.get(path, 0) + 1

            Recursive claim (when the operation covers the full tree under path):
                recursive = occupied_paths.setdefault("recursive", {})
                recursive[path] = recursive.get(path, 0) + 1

        Releasing a claim — after all operations on that path are complete:

            Exact claim:
                occupied_paths[path] -= 1
                if occupied_paths[path] == 0:
                    del occupied_paths[path]

            Recursive claim:
                recursive = occupied_paths["recursive"]
                recursive[path] -= 1
                if recursive[path] == 0:
                    del recursive[path]
                if not recursive:
                    del occupied_paths["recursive"]

            Never delete a path directly without decrementing first — multiple
            components may hold concurrent claims on the same path, and a
            direct delete would silently invalidate all of them.

        Watcher Lookup Protocol:
            Surface-level Watcher implementations must check occupied_paths
            before enqueuing each event. The check follows three steps in
            strict order — if any step returns True, the event is self-generated
            and must be dropped silently, never enqueued:

            Step 1 — exact match:
                occupied_paths.get(event_path, 0) > 0

            Step 2 — recursive match:
                any(
                    event_path.startswith(p + "/") and count > 0
                    for p, count in occupied_paths.get("recursive", {}).items()
                )

            Step 3 — vakt suffix strip, then repeat steps 1 and 2:
                idx = event_path.rfind(".vakt.")
                if idx != -1:
                    clean = event_path[:idx]
                    repeat step 1 on clean
                    repeat step 2 on clean

            rfind is mandatory here — not find. A path may contain a
            vakt-marked parent directory somewhere in its ancestry, which
            means ".vakt." can appear earlier in the string than the suffix
            on the object itself. find would match that earlier occurrence
            and strip too much, producing a wrong clean path. rfind always
            finds the rightmost ".vakt." — the one that belongs to the
            object, not to a parent.

            Deep-integration Watcher implementations that receive kernel-level
            event metadata must check whether the initiating process matches
            the server's own process and drop the event if it does. For such
            implementations, occupied_paths filtering is not required and may
            be skipped entirely.

    Usage Example:
        @classmethod
        def requirements(cls) -> Configure:
            return Configure(
                internal_reqs=(
                    "shutdown_event",
                    "occupied_paths",
                    "concrete:BaseSnapshotsRegistryStore::LocalSnapshotsRegistryStore",
                    "port:BasePathLocker",
                ),
                client_reqs={
                    "registry_path": (
                        "Absolute path to the persistent registry JSON file.",
                        Path,
                    ),
                    "rotation": (
                        "Snapshot rotation delay in seconds. Must be greater than zero.",
                        lambda x: x if int(x) > 0 else (_ for _ in ()).throw(ValueError()),
                    ),
                },
            )

    Notes:
        - All implementations must respect the DECLARATION PROTOCOL.
        - client_reqs() never exposes Callables — only the description and the
            currently provided raw value (or "Empty" if not yet supplied).
        - resolve() accepts client in the same dict[str, tuple[str, str]] format
            that client_reqs() returns — the Assembler fills in the values and
            passes the structure straight through without any restructuring.
        - resolve() follows the same error protocol as MethodSpec.resolve():
            KeyError if a required key is absent, ValueError if the Callable
            raises. No partial result is ever produced.
        - resolved is public by design — implementations read from it directly
            in __init__ via configure.resolved["internal"] and
            configure.resolved["client"]. No helper methods or indirection needed.
    """

    def __init__(
        self,
        internal_reqs: tuple[str, ...],
        client_reqs: dict[str, tuple[str, Callable[[str], Any]]],
    ) -> None:
        """
        Initializes the dependency contract without resolving anything.

        No values are validated or transformed at this stage. Configure at
        this point is a pure declaration — a structured description of what
        the implementation will need once the Assembler begins assembly.
        """
        self._internal_reqs: tuple[str, ...] = internal_reqs
        self._client_reqs: dict[str, tuple[str, Callable[[str], Any]]] = client_reqs
        self._provided: dict[str, str] = {}
        self.resolved: dict[str, dict[str, Any]] = {"internal": {}, "client": {}}

    def internal_reqs(self) -> tuple[str, ...]:
        """
        Returns the sequence of internal requirement names declared by this
        implementation.

        Used by the Assembler to determine which resources it must provision
        from its own environment before calling resolve().
        """
        return self._internal_reqs

    def client_reqs(self) -> dict[str, tuple[str, str]]:
        """
        Returns a client-facing view of all client requirements alongside
        their current provision state.

        For each declared client requirement, returns a tuple of:
            (currently_provided_raw_value_or_"Empty", human_readable_description)

        The first element reflects whatever raw string the client has already
        supplied via resolve() — or "Empty" if the requirement has not yet
        been provided. Used by the Assembler to present the full requirement
        status to the client and to identify which parameters still need a value.
        Never exposes Callables.
        """
        return {
            param: (self._provided.get(param, "Empty"), desc)
            for param, (desc, _) in self._client_reqs.items()
        }

    def resolve(
        self,
        internal: dict[str, Any],
        client: dict[str, tuple[str, str]],
    ) -> None:
        """
        Validates and resolves all requirements, populating self.resolved.

        Called by the Assembler after both internal and client values have been
        collected. client must carry the same structure that client_reqs() returns —
        dict[str, tuple[str, str]] — where the first element of each tuple is the
        raw value supplied by the client and the second element is the description.
        This mirrors the output of client_reqs() exactly so the Assembler never
        has to restructure the dict between the two calls — it receives the template,
        fills in the values, and passes it straight through.

        Internal values are stored directly into resolved["internal"]. For each
        client requirement, the raw string is extracted from the tuple, recorded
        in _provided so that client_reqs() can surface it, then passed through
        its registered Callable — validated or transformed — and the result is
        stored in resolved["client"].

        The resolved dict is populated only when all client requirements pass
        without error. A single missing or invalid argument raises immediately —
        no partial result is ever produced.

        Raises:
            KeyError:   if a client requirement is absent from provided.
            ValueError: if the Callable raises for any supplied value.
        """
        provided = {param: value for param, (value, _) in client.items()}
        self._provided.update(provided)

        for key in self._internal_reqs:
            self.resolved["internal"][key] = internal[key]

        for param, (description, func) in self._client_reqs.items():
            if param not in provided:
                raise KeyError(
                    f"Requirement {param!r} was not supplied. "
                    f"Description: {description}."
                )
            try:
                self.resolved["client"][param] = func(provided[param])
            except Exception as exc:
                raise ValueError(
                    f"Requirement {param!r} validation failed. "
                    f"Problem: {exc}. "
                    f"Description: {description}."
                ) from exc
