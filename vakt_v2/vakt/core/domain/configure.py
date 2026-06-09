from __future__ import annotations

from typing import Any, Callable


class Configure:
    """
    Configure defines precisely what is needed to instantiate a port implementation.
    It acts as a dependency declaration contract between the implementation and its
    two suppliers: the internal provider (via Assembler) and the client. Each
    implementation specifies its won Configure through a class method, describing
    exactly what it requires and from whom.

    Why two seperate arguments:
        internal_reqs and client_reqs strictly partition all requirements. During
        assembly, Assembler resolves these using a lazy incremental dependency graph.
        When populating and instance's requirements, it consults the client_reqs
        dictionary and prompts the user requirements as needed. (For the rationale
        and full details, see the documentation inside the Assembler class).

    Cleint Requirements Dictionary structure:
        client_reqs is dict[str, tuple[str, Callable]]:
            - The str in tuple is a human-readable description of the parameter - its
                purpose and role.
            - Tha callable in tuple lets the imeplementation supply a custom validation
                or conversion function. It processes (validate/transforms) the client
                supplied value before it is accepted by imp.__init__(configure: Configure).

        In contrast, internal_reqs is simply a tuple of requirement names that the
        implementation excepts Assembler to provide (e.g., shutdown_event, occupied_paths).

    DECLARATION PROTOCOL:
        Implementation must never request from the internal provider (Assembler) any
        resources that requires client decision or response. Any resources thet explicitly
        or implicitly depends on client input must be declared in client_reqs. This is hard
        requirement for correct instance creation. The Assembler cannot arbitrarily
        choose such values - doing so would violate the NYR (Not in Your Responbility)
        principle, custom law that I declared.

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

        Never delete a path directly without decrementing — multiple
        components may hold concurrent claims on the same path, and
        a direct delete would silently invalidate all of them.


    Why Configure.__init__ avoids setattr:
        Deliberetely, no dynamic attribute setting occurs during Configure initialization.
        This allows Configure.check_out to reliably detect what has been supplied and what
        is missing (even though missing data is unlikely given the Assembler mechanism).
        During checkout, every client-supplied parameter's presence is verified, and every
        parameter's value is validated/converted using its associated Callable. If any check
        fails, the problem is immediately reported to Assembler, which forwards it to the
        Overseer, the Overseer in turn uses IPCommunicator to inform the client about the
        incorrectly provided parameter. This early validation prevents malformed instances
        and avoids runtime crashes during creation.

        The protocol forbids placing client-depended values directly into internal_reqs,
        but it explicity allows placing a concrete implementation (which may itself declare
        client_reqs). This gives implementations the power to hard-wire which dependency
        implementation is used, while the Assembler takes full responsibility for resolving
        that implementation and requesting the necessary client parameters on its behalf -
        without involving the outer client in the implementation choice.

    Usage Example:
        @classmethod
        def requirements(self) -> Configure:
            return Configure(
                internal_reqs=("shutdown_event", "occupied_paths", "ActionsLogger"),
                client_reqs={
                    "registry_path": (
                        "Path of persistent registry JSON file",
                        os.path.exists,
                    ),
                    "rotation": (
                        "delay of rotation registry",
                        lambda x: if x <= 0: raise ValueError(...) else x,
                    ),
                    "path_locker::BasePathLocker": (
                        "Locker that locks path object while reading from writing"
                        has_shared_lock,
                    )
                },
            )

    Notes:
        - All implementations must respect DECLARATION PROTOCOL.
        - Configure.client_reqs returns a dictionary that does
            not contain a Callable for the associated parameter.
    """

    def __init__(
        self,
        internal_reqs: tuple[str],
        client_reqs: dict[str, tuple[str, Callable[[Any], Any]]],
    ) -> None:
        """
        Initializes all seperated requirements for implementation
        without setting attributes for params in both reqs.
        """
        self._internal_reqs: tuple[str] = internal_reqs
        self._client_reqs: dict[str, tuple[str, Callable[[Any], Any]]] = client_reqs

    def internal_reqs(self) -> tuple[str]:
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
