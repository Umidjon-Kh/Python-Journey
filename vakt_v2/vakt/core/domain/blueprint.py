from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class MethodSpec:
    """
    MethodSpec defines exactly which arguments and what they must be to invoke
    a single public method of a registry implementation that inherits from and
    conforms to RegistryProtocol. It acts as a per-method dependency declaration
    contract between the registry implementation and the client.

    MethodSpec is simultaneously responsible for two things:
        1. Describing the callable method of the implementation — its purpose,
            every required argument, what each argument represents, and what it
            accepts. This description drives the client interaction layer inside
            RegistryManager, giving the client the full picture of what a method
            does and what it needs before a single value is supplied.
        2. Validating and delivering a fully resolved argument mapping ready for
            direct invocation. resolve() receives the complete set of client-
            supplied strings, runs each value through its registered Callable —
            which may validate, convert, or transform it — and returns a new dict
            where every argument has been processed into its final form. No partial
            state is produced or retained at any point. The result is either a
            complete, safe-to-use argument mapping ready to be unpacked directly
            into the underlying method call, or an immediate error that tells
            RegistryManager exactly which argument failed and why.

    Why MethodSpec does not store client-supplied data:
        Retaining provided data on the instance would be meaningless from the
        perspective of MethodSpec's lifecycle. MethodSpec exists to solve a
        specific problem — keeping RegistryManager's orchestration logic clean
        while providing a rich, uniform surface for interacting with any
        implementation that conforms to RegistryProtocol. That was its original
        and sole design goal. Features such as persisting the last supplied
        requirements across calls are deliberately deferred — the project does
        not require them yet and adding them now would introduce overhead with
        no immediate benefit.

        MethodSpec is an internal object owned exclusively by BluePrint. Only
        BluePrint has the right to construct MethodSpec instances — from the raw
        dict passed to its own __init__, not from MethodSpec instances supplied
        from outside. MethodSpec describes only the methods of the implementation
        that the client is permitted to invoke through RegistryManager — not every
        method the implementation exposes. This distinction is intentional: it
        prevents developers from accidentally exposing implementation internals by
        indiscriminately registering all public methods without filtering.

        For full details on ownership, construction, and usage examples
        see the BluePrint class documentation.

    Why MethodSpec is immutable (frozen):
        MethodSpec is a descriptor, not a state container. Its sole purpose is
        to carry a stable, authoritative definition of a method contract — the
        description of the callable and the full requirements it demands from
        the client. Once BluePrint constructs a MethodSpec instance, neither
        the description nor the requirements should ever change for the lifetime
        of that BluePrint. Freezing the dataclass makes this guarantee explicit
        and enforceable at the language level: no component can accidentally
        overwrite the contract mid-session, corrupt the requirements dict, or
        inject transient state through attribute assignment. This is also
        consistent with MethodSpec's role — it describes, it does not accumulate.

    Requirements Dictionary structure:
        _requirements is dict[str, tuple[str, Callable[[str], Any]]]:
            - The str in the tuple is a human-readable description of the
                parameter — its purpose and expected value, presented to the
                client by RegistryManager before they supply a value.
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
        only the human-readable descriptions — exactly what RegistryManager needs
        to present each parameter to the client before they supply a value.

    Notes:
        - MethodSpec does not know which registry method it describes. The name
            lives in BluePrint._methods as the dict key and is used by
            RegistryManager to invoke the method via getattr after resolve()
            has passed.
        - resolve() accepts only a fully supplied arguments dict — partial input
            is not permitted. It follows the same error protocol as Configure:
            KeyError if a required key is absent from provided, ValueError if
            the Callable raises.
        - All Callables must return the object itself after validation, even when
            they perform no transformation. A pure validator that silently returns
            None would corrupt the resolved output.
        - MethodSpec and BluePrint are intended exclusively for RegistryManager.
            No other object — not handlers, not the Assembler, not any helper
            consumer — has the right to call blueprint() or interact with
            MethodSpec directly.
        - All requirements declared in a MethodSpec must accept raw string input
            supplied directly by the client. RegistryManager has no knowledge of
            what any specific MethodSpec requires and performs no pre-processing
            of its own — client-supplied strings are passed to resolve() as-is.
            Implementations must therefore never declare a requirement whose value
            the client cannot supply as a plain string.
    """

    description: str
    _requirements: dict[str, tuple[str, Callable[[str], Any]]]

    def requirements(self) -> dict[str, str]:
        """
        Returns a client-facing view of the requirements dictionary.

        Strips the Callable from each entry, exposing only the human-readable
        description of each parameter. Used by RegistryManager to present
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
        no partial result is ever produced or retained.

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
                value = func(provided[param])
                resolved[param] = value
            except Exception as exc:
                raise ValueError(
                    f"Requirement {param!r} value validation failed. "
                    f"Problem: {exc}. "
                    f"Description: {description}."
                ) from exc

        return resolved


@dataclass(frozen=True)
class BluePrint:
    """
    BluePrint is the complete public manifest of all methods the client is
    permitted to invoke through RegistryManager. It describes every callable
    the client may operate on a registry implementation that conforms to
    RegistryProtocol, and acts as the API the implementation delivers to
    RegistryManager so it can present those methods to the client via
    IPCommunicator. Put plainly — BluePrint is a protocol between the implementation
    and the RegistryManager that lets you know what capabilities are granted to
    the client, independent of any implementation-specific details.

    Every implementation inheriting from RegistryProtocol must deliver a fully
    constructed BluePrint through its blueprint() method. BluePrint constructs
    and owns one MethodSpec per declared method, keyed by the method's exact
    public name — the same name RegistryManager hands to getattr() after
    arguments are resolved. RegistryManager is the only object permitted to
    call blueprint() or interact with BluePrint and its owned MethodSpec
    instances. No other object — not even the Assembler — may touch either.
    For the full protocol see RegistryProtocol documentation.

    Why BluePrint and not a plain dict[str, MethodSpec]:
        A plain dict offloads work onto RegistryManager that is NYR (Not In
        Your Responsibilities) — constructing properly formatted client error
        messages, locating callables for each method, raising errors on invalid
        selections. BluePrint and MethodSpec take on all of that so RegistryManager
        can operate purely as a consultant — presenting options, collecting choices,
        routing calls — without getting its hands dirty on what is fundamentally
        the implementation's paperwork.

    Why BluePrint is immutable (frozen):
        By the time blueprint() returns, BluePrint is a resolved object — every
        MethodSpec constructed, every Callable fixed, every requirement declared.
        There is nothing left to change, and a manifest that shifts mid-session
        is a manifest that lies. Worth clarifying — frozen means no attribute
        slot may be rebound after __post_init__ completes, not that the objects
        those attributes point to are themselves immutable. Because of this
        guarantee, RegistryManager receives the original instance directly rather
        than a copy — a copy would be an empty gesture when the original is
        already incapable of changing in any way that matters. Also, thats why
        it returns original MethodSpec instances instead of copy, cause thay
        are immutabel too.

    Why show() returns only descriptions and not full MethodSpec objects:
        When a client first surveys available methods, it cares about what each
        method does — not what it requires. Returning full MethodSpec objects
        before any selection is made floods the client with requirement trees
        it does not yet need, turning a clean menu into a bazaar. The full
        specification is surfaced only after the client commits to a specific
        method via get(name).

    Usage example:
        def blueprint(self) -> BluePrint:
            return BluePrint(
                raw_methods={
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
            cached between sessions. RegistryManager holds it for the duration
            of a single management session only.
        - BluePrint has no knowledge of the registry instance it was created from.
            Method invocation is the sole responsibility of RegistryManager, which
            calls getattr(registry_instance, name) after all requirements are
            resolved by MethodSpec.
        - BluePrint is intended exclusively for RegistryManager. All other objects
            must depend on the concrete port conforming to RegistryProtocol or the
            concrete class directly — never through BluePrint.
    """

    raw_methods: dict[str, tuple[str, dict[str, tuple[str, Callable[[str], Any]]]]]
    _methods: dict[str, MethodSpec] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        """
        Constructs all MethodSpec instances from raw_methods and populates
        _methods. Called automatically by the dataclass machinery immediately
        after __init__ completes.
        """
        for name, meta in self.raw_methods.items():
            self._methods[name] = MethodSpec(meta[0], meta[1])

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

        RegistryManager uses the returned spec to present requirements to the
        client, collect their input, and call resolve() before invoking the
        underlying method via getattr.

        Raises:
            KeyError: if no method with the given name exists in this BluePrint.
                      Forwarded by RegistryManager to the client as a
                      "method not found" response.
        """
        if name not in self._methods:
            raise KeyError(
                f"Method {name!r} not found in this BluePrint. "
                f"Available: {list(self._methods)}."
            )
        return self._methods[name]
