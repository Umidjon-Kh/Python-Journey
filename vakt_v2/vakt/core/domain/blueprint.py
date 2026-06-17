from __future__ import annotations

from typing import Any, Callable


class MethodSpec:
    """
    The per-method dependency declaration contract between a BluePrintProtocol
    implementation and any management-layer object authorised to invoke its
    methods on behalf of the client.

    MethodSpec is simultaneously responsible for two things:
        1. Describing the callable method of the implementation — its purpose,
            every required argument, what each argument represents, and what it
            accepts. This description drives the client interaction layer,
            giving the client the full picture of what a method does and what
            it needs before a single value is supplied.
        2. Validating and delivering a fully resolved argument mapping ready for
            direct invocation. resolve() receives the complete set of client-
            supplied strings, runs each value through its registered Callable —
            which may validate, convert, or transform it — and returns a new dict
            where every argument has been processed into its final form. No partial
            state is produced or retained at any point. The result is either a
            complete, safe-to-use argument mapping ready to be unpacked directly
            into the underlying method call, or an immediate error that tells the
            caller exactly which argument failed and why.

    Why MethodSpec does not retain client-supplied data:
        MethodSpec is a descriptor, not a session container. Persisting provided
        data on the instance would be meaningful only if the same MethodSpec were
        reused across multiple client interactions with a need to recall what was
        last supplied — a feature this project does not require. Adding it now
        would be overhead for an object of this scale. Shooting a bird with a tank.
        resolve() receives values, processes them, and returns the result —
        nothing is kept.

    Why MethodSpec is not a dataclass:
        MethodSpec instances are owned exclusively by the BluePrint that constructs
        them. Nothing outside BluePrint ever creates a MethodSpec directly, and no
        external object ever reassigns its attributes — making frozen enforcement
        redundant. Slots are equally unnecessary: there will never be enough
        MethodSpec instances alive simultaneously to justify the overhead. A plain
        class is precise enough.

    Who MethodSpec is for:
        MethodSpec is exclusively consumed by management-layer objects — the layer
        responsible for presenting implementation capabilities to the client and
        orchestrating method invocation on their behalf. It is not designed for
        the Assembler, the Observer, watchers, handlers, or any other
        infrastructure or environment object. RegistryManager is the current
        representative of this layer, but any future object that manages client
        interaction with a BluePrintProtocol implementation occupies the same role
        and consumes MethodSpec in exactly the same way.

    Requirements Dictionary structure:
        _requirements is dict[str, tuple[str, Callable[[str], Any]]]:
            - The str in the tuple is a human-readable description of the
                parameter — its purpose and expected value, presented to the
                client before they supply a value.
            - The Callable receives the client-supplied string, validates or
                transforms it, and must always return the result — even if it
                is a pure validator that applies no transformation. The return
                value is what ends up in the resolved dict returned by resolve().
                A Callable that returns None on success would silently replace
                the client value with None in the output — always return the
                object itself.

    Why _requirements is kept private:
        The raw Callables inside _requirements are internal validation logic
        and must not be exposed directly. requirements() strips them and returns
        only the human-readable descriptions — precisely what the management
        layer needs to present each parameter to the client before they supply
        a value.

    Notes:
        - MethodSpec does not know which BluePrintProtocol method it describes. The name
            lives in BluePrint._methods as the dict key and is used by the
            management layer to invoke the method via getattr after resolve()
            has passed.
        - resolve() accepts only a fully supplied arguments dict — partial input
            is not permitted. KeyError if a required key is absent from provided,
            ValueError if the Callable raises. No partial result is ever produced.
        - All Callables must return the object itself after validation, even when
            they perform no transformation. A pure validator that silently returns
            None would corrupt the resolved output.
        - All requirements declared in a MethodSpec must accept raw string input
            supplied directly by the client. The management layer performs no
            pre-processing of its own — client-supplied strings are passed to
            resolve() as-is. Implementations must therefore never declare a
            requirement whose value the client cannot supply as a plain string.
    """

    def __init__(
        self,
        description: str,
        requirements: dict[str, tuple[str, Callable[[str], Any]]],
    ) -> None:
        """
        Initializes the method contract with its description and requirements.

        No values are validated or transformed at this stage. MethodSpec at
        this point is a pure declaration — a structured description of what
        the method does and what it needs from the client.
        """
        self.description: str = description
        self._requirements: dict[str, tuple[str, Callable[[str], Any]]] = requirements

    def requirements(self) -> dict[str, str]:
        """
        Returns a client-facing view of the requirements dictionary.

        Strips the Callable from each entry, exposing only the human-readable
        description of each parameter. Used by the management layer to present
        what the method requires to the client before any values are supplied.
        """
        return {param: desc for param, (desc, _) in self._requirements.items()}

    def resolve(self, provided: dict[str, str]) -> dict[str, Any]:
        """
        Validates and transforms a fully supplied set of client arguments,
        returning a resolved mapping ready for direct method invocation.

        Partial input is not accepted — every key declared in _requirements
        must be present in provided. For each requirement:
            1. Checks the key is present in provided (KeyError if missing).
            2. Passes the client-supplied string through the registered Callable.
            3. Stores the Callable's return value in the resolved dict.

        The resolved dict is returned only when all requirements pass without
        error. A single missing or invalid argument raises immediately —
        no partial result is ever produced.

        Raises:
            KeyError:   if a required key is absent from provided.
            ValueError: if the Callable raises for any supplied value.
        """
        resolved: dict[str, Any] = {}

        for param, (description, func) in self._requirements.items():
            if param not in provided:
                raise KeyError(
                    f"Requirement {param!r} was not supplied. "
                    f"Description: {description}."
                )
            try:
                resolved[param] = func(provided[param])
            except Exception as exc:
                raise ValueError(
                    f"Requirement {param!r} value validation failed. "
                    f"Problem: {exc}. "
                    f"Description: {description}."
                ) from exc

        return resolved


class BluePrint:
    """
    The complete public manifest of all methods the client is permitted to invoke
    through any management-layer object authorised to operate on a BluePrintProtocol
    implementation.

    BluePrint is to BluePrintProtocol what Configure is to AssemblyProtocol —
    the declaration object the protocol mandates every implementation produce.
    Just as AssemblyProtocol implementations must return a Configure from
    requirements(), BluePrintProtocol implementations must return a BluePrint
    from blueprint(). It constructs and owns one MethodSpec per declared method,
    keyed by the method's exact public name — the same name the management layer
    hands to getattr() after arguments are resolved. BluePrint places no
    restriction on which management-layer object may consume it: RegistryManager
    is the current occupant of that role, but any future object that manages
    client interaction with a BluePrintProtocol implementation may consume
    BluePrint directly. For the full protocol contract and implementation
    requirements, see BluePrintProtocol.

    Why BluePrint is not a dataclass:
        BluePrint is created fresh on every blueprint() call — a new instance
        per management session, never cached or shared across them. A frozen
        dataclass would add machinery whose only benefit is preventing attribute
        rebinding that never happens anyway: nothing outside the implementation's
        own blueprint() method constructs or modifies a BluePrint instance.
        The enforcement would be purely theatrical. A plain class is precise enough.

    Why the methods argument is not stored as an attribute:
        The methods dict is input data — a construction-time argument that exists
        only to be consumed by __init__ and converted into MethodSpec instances.
        Storing it as an attribute after construction would mean carrying raw,
        unprocessed Callables and string tuples on the instance indefinitely,
        exposing them to any caller and giving the impression that the raw
        representation is part of BluePrint's public surface. It is not.
        __init__ consumes it, builds _methods, and discards it. The only surface
        BluePrint exposes is show() and get().

    Why show() and get() are separate:
        When a client first surveys available methods, it cares about what each
        method does — not what it requires. Returning full MethodSpec objects
        before any selection is made floods the client with requirement trees it
        does not yet need, turning a clean menu into a bazaar. The full
        specification is surfaced only after the client commits to a specific
        method via get(name).

    Who BluePrint is for:
        BluePrint is exclusively consumed by management-layer objects — objects
        that present implementation capabilities to the client and orchestrate
        method invocation on their behalf. It is not designed for the Assembler,
        the Observer, watchers, handlers, or any other infrastructure or environment
        object. The Assembler has no business calling blueprint() or interacting
        with BluePrint in any form. BluePrint lives and dies within a single
        management session.

    Usage Example:
        def blueprint(self) -> BluePrint:
            return BluePrint(
                methods={
                    "restore": (
                        "Restores a tracked path to the state of its last saved snapshot.",
                        {
                            "path": (
                                "Absolute path of the root to restore.",
                                Path,
                            ),
                        },
                    ),
                    "register": (
                        "Registers a new path for snapshot tracking and captures "
                        "its initial state.",
                        {
                            "path": (
                                "Absolute path to register. Must exist on the filesystem.",
                                Path,
                            ),
                            "recursive": (
                                "Whether to track the entire directory tree. "
                                "Accepted values: 'true', 'false'.",
                                lambda s: s.lower() == "true",
                            ),
                            "level": (
                                "Sensitivity level for change detection. "
                                "Accepted values: 'low', 'medium', 'high'.",
                                lambda s: LevelType[s.upper()],
                            ),
                        },
                    ),
                    "unregister": (
                        "Removes a path from snapshot tracking and discards "
                        "all its stored state.",
                        {
                            "path": (
                                "Absolute path to unregister. Must be currently tracked.",
                                Path,
                            ),
                        },
                    ),
                }
            )

    Notes:
        - BluePrint must be created once per blueprint() call and must never be
            cached between sessions. The management layer holds it for the duration
            of a single management session only.
        - BluePrint has no knowledge of the implementation instance it was created from.
            Method invocation is the sole responsibility of the management layer,
            which calls getattr(registry_instance, name) after all requirements
            are resolved by MethodSpec.resolve().
        - Management-layer objects are the only callers of blueprint() and the
            only consumers of the BluePrint it returns. No other component — not
            even the Assembler — has any business constructing or interacting
            with BluePrint directly.
    """

    def __init__(
        self,
        methods: dict[str, tuple[str, dict[str, tuple[str, Callable[[str], Any]]]]],
    ) -> None:
        """
        Constructs all MethodSpec instances from methods and populates _methods.

        methods is a construction-time argument only — it is consumed here and
        not retained as an attribute. After __init__ completes, the only
        accessible surface is _methods, exposed through show() and get().
        """
        self._methods: dict[str, MethodSpec] = {
            name: MethodSpec(description, reqs)
            for name, (description, reqs) in methods.items()
        }

    def show(self) -> dict[str, str]:
        """
        Returns a name-to-description summary of all available methods.

        Intended as the first step in a management session — the client calls
        show() to survey what the implementation offers before selecting a
        specific method. Does not expose requirements or Callables.
        """
        return {name: spec.description for name, spec in self._methods.items()}

    def get(self, name: str) -> MethodSpec:
        """
        Returns the MethodSpec for the method identified by name.

        The management layer uses the returned spec to present requirements to
        the client, collect their input, and call resolve() before invoking the
        underlying method via getattr.

        Raises:
            KeyError: if no method with the given name exists in this BluePrint.
                      Forwarded by the management layer to the client as a
                      "method not found" response.
        """
        if name not in self._methods:
            raise KeyError(
                f"Method {name!r} not found in this BluePrint. "
                f"Available: {list(self._methods)}."
            )
        return self._methods[name]
