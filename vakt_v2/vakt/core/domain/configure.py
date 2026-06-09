from __future__ import annotations

from typing import Any, Callable


class Configure:
    """
    Configure defines precisely what is needed to instantiate a port implementation.
    It acts as a dependency declaration contract between the implementation and its
    two suppliers: the internal provider (via Assembler) and the client. Each
    implementation specifies its own Configure through a class method, describing
    exactly what it requires and from whom.

    Why two separate arguments:
        internal_reqs and client_reqs strictly partition all requirements. During
        assembly, the Assembler resolves these using a lazy incremental dependency
        graph. When populating an instance's requirements, it consults the client_reqs
        dictionary and prompts the client for input as needed. For the full rationale
        and details, see the Assembler class documentation.

    Client Requirements Dictionary structure:
        client_reqs is dict[str, tuple[str, Callable]]:
            - The str in the tuple is a human-readable description of the parameter —
                its purpose and expected value.
            - The Callable lets the implementation supply a custom validation or
                conversion function. It processes (validates or transforms) the
                client-supplied value before it is accepted by
                imp.__init__(configure: Configure).

        In contrast, internal_reqs is simply a tuple of requirement names that the
        implementation expects the Assembler to provide (e.g., shutdown_event,
        occupied_paths).

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

        occupied_paths is a shared dict[str, int] mapping each path to the
        number of server components currently holding an active occupancy
        claim on it. A path remains occupied as long as its count is above
        zero — it is removed only when the last component releases its claim.

        Before starting any self-generated file system operation:
            occupied_paths[path] = occupied_paths.get(path, 0) + 1

        After all operations on that path are complete:
            occupied_paths[path] -= 1
            if occupied_paths[path] == 0:
                del occupied_paths[path]

        Never delete a path directly without decrementing — multiple components
        may hold concurrent claims on the same path, and a direct delete would
        silently invalidate all of them.

    Why Configure.__init__ avoids setattr:
        Deliberately, no dynamic attribute setting occurs during Configure
        initialization. This allows Configure.check_out() to reliably detect
        what has been supplied and what is missing. During checkout, every
        client-supplied parameter's presence is verified and its value is
        validated or converted using its associated Callable. If any check
        fails, the problem is immediately reported to the Assembler, which
        forwards it to the Overseer. The Overseer in turn uses IPCommunicator
        to inform the client about the incorrectly provided parameter. This
        early validation prevents malformed instances and avoids runtime
        crashes during creation.

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
                        os.path.exists,
                    ),
                    "rotation": (
                        "Snapshot rotation delay in seconds. Must be greater than zero.",
                        lambda x: x if x > 0 else (_ for _ in ()).throw(ValueError(...)),
                    ),
                },
            )

    Notes:
        - All implementations must respect the DECLARATION PROTOCOL.
        - Configure.client_reqs() returns a dictionary that strips the
            Callable from each entry, exposing only the human-readable
            description to the client.
    """

    def __init__(
        self,
        internal_reqs: tuple[str, ...],
        client_reqs: dict[str, tuple[str, Callable[[Any], Any]]],
    ) -> None:
        """
        Initializes all seperated requirements for implementation
        without setting attributes for params in both reqs.
        """
        self._internal_reqs: tuple[str, ...] = internal_reqs
        self._client_reqs: dict[str, tuple[str, Callable[[Any], Any]]] = client_reqs

    def internal_reqs(self) -> tuple[str, ...]:
        return self._internal_reqs

    def client_reqs(self) -> dict[str, str]:
        return {p: v for p, (v, _) in self._client_reqs.items()}

    def check_out(self) -> None:
        """
        Validate and transform all client‑supplied requirements.
        Internal dependencies are not checked because their provision by
        the Assembler is architecturally guaranteed (NYR principle).

        For each client parameter:
        1. Verifies the attribute was set (KeyError if missing).
        2. Applies the registered validation/conversion callable.
        3. Overwrites the attribute with the transformed value on success.

        Raises:
            KeyError: if a client requirement was not supplied.
            ValueError: if the validation/conversion callable raises an exception.
        """
        for param, (description, func) in self._client_reqs.items():
            if not hasattr(self, param):
                raise KeyError(
                    f"Requirement {param!r} was not supplied."
                    f"Description: {description}."
                )
            try:
                value = getattr(self, param)
                setattr(self, param, func(value))
            except Exception as exc:
                raise ValueError(
                    f"Requirement {param!r} value validation is failed."
                    f"Problem: {exc}."
                    f"Description: {description}"
                ) from exc
