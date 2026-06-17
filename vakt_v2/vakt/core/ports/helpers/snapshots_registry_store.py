from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence

from ..protocols import AssemblyProtocol, BluePrintProtocol


class BaseSnapshotsRegistryStore(AssemblyProtocol, BluePrintProtocol):
    """
    Abstract base class for all snapshot registry and storage implementations.

    SnapshotsRegistryStore is a helper infrastructure component that gives
    pipeline components the ability to create, restore, and delete backups of
    file system objects. It is not a core pipeline element and does not
    participate in event processing directly.

    Its existence decouples components like BackupInvoker and RestoreInvoker
    from implementation details that are critical in real-world backup
    operations — where the backup is stored, under what name, whether it was
    encrypted, whether it was created correctly or is corrupted, or whether a
    backup even exists despite BackupInvoker having appended its flag to
    ctx.performed. SnapshotsRegistryStore owns these concerns entirely, giving
    its callers a single clean contract regardless of the storage strategy
    behind it.

    SnapshotsRegistryStore is simultaneously responsible for three things:
        1. Registering and managing Snapshot metadata objects, stored in groups
            per concrete file system object.
        2. Storing and managing the physical backup files themselves, and owning
            their full lifecycle — including creation, restoration, and deletion.
        3. Thread-safety — both internal pipeline components and external
            management objects operating under client commands must be able to
            work concurrently without race conditions.

    Who BaseSnapshotsRegistryStore is for:
        Any pipeline component that needs backup capabilities — whether a
        handler, a helper, another registry, or any other component in the
        observer environment — may declare this port in its Configure
        requirements. Components that need to know exactly what kwargs a
        specific implementation accepts declare it as a concrete dependency
        via "concrete:BaseSnapshotsRegistryStore::..." in their Configure
        requirements. That is their direct contract with the implementation
        — blueprint() plays no role there. blueprint() is strictly a
        management-layer concern.

        Management-layer objects reach show() through the BluePrint flow as a
        guaranteed entry point and interact with everything else through
        blueprint().

    Pipeline Methods Protocol:
        create(), restore(), and delete() share the same contract: each accepts
        only **kwargs and returns bool. kwargs are whatever the implementation
        requires — it decides what fields are mandatory, what is optional, and
        what it fills in itself. No two implementations are required to accept
        the same kwargs. bool is the only signal the caller needs: the operation
        succeeded, or it did not.

        The Snapshot object produced internally by create() is a private concern
        of the implementation. No external object holds one, inspects one, or
        stores one.

    Storage Protocol:
        All implementations must store snapshots in groups keyed by the original
        file system object. This is mandatory so that restore() and delete() can
        locate the correct group from the kwargs the caller provides. Whether the
        implementation stores groups under the literal original path, a hash, or
        something else is an internal detail.

        Implementations that want to surface snapshot history for a specific
        object do so through show() with implementation-specific kwargs or
        presentation modes. show() is flexible enough to accommodate any
        variation — full registry view, filtered by path, ordered by date —
        without a dedicated history method.

    Integrity and Safety Protocol:
        All implementations MUST persist the registry after every modification
        to avoid metadata loss on crash. This is not optional — it is a
        critical requirement for data integrity. If the server crashes during
        backup creation and registry persistence, the backup file may exist on
        disk while the registry no longer tracks it, leading to orphaned backup
        objects that cannot be managed or restored.

        Furthermore, all implementations must verify that a backup was
        successfully created or restored by comparing checksums to detect
        corruption. Yes, it is expensive — but it is safe, mfks.

        When working with physical file system objects, implementations must mark
        all intermediate objects with the appropriate suffix — .vakt.bckp,
        .vakt.tmp, or .vakt.old — depending on the task and the semantics of
        the object. This gives users and other components the ability to manually
        recover or remove leftover and failed objects.

        Recommended approach:
            - Verify backup integrity at every move via checksum comparison.
            - Prefer atomic operations (rename or move) wherever possible.
            - Register in the registry before modifying or moving the physical
                backup, so that snapshot.checksum can be compared against the
                post-move checksum.
            - Use atomic writes with .vakt.tmp in the registry store itself.
            - Validate group integrity on every method call that contacts a
                group — check for existence and remove from the registry if
                the backup is gone.

    show() as a Registry Agreement:
        show() upholds the Registry Agreement shared across all registry-like
        ports in this codebase — any port that carries show() is declaring
        itself as belonging to the registry role. Declaring it here as an
        abstract method serves as a cushion: it ensures no implementation
        silently omits it. See BaseInstructionRegistry for the full description
        of this agreement.

    Current State — Temporary Pragmatic Contract:
        The current management contract is temporary and pragmatic. The full
        picture of what is coming is documented in BluePrintProtocol.
        That is where the promise lives.

    Example implementations:
        - LocalSnapshotsRegistryStore: stores backups on disk, registry in JSON.
        - S3SnapshotsRegistryStore: stores backups in S3, registry in a remote store.

    Notes:
        - create(), restore(), delete() return bool — success or failure. That
            is the only signal pipeline components need. The Snapshot produced
            internally by create() is private — no external object holds it.
        - Pipeline components that declare a concrete implementation in Configure
            know exactly what kwargs to pass — that is their direct contract with
            the implementation. blueprint() is strictly for the management layer.
        - show(**kwargs) is invoked exclusively through the BluePrint flow —
            never called directly by pipeline components. kwargs are the resolved
            output of the implementation's MethodSpec for show(), provided by
            the client during the management session.
        - Must never propagate exceptions to the caller. All errors must be
            caught and handled internally.
        - Implementations that require exclusive access to a file system object
            during backup creation or restoration should declare BasePathLocker
            in their Configure internal_reqs.
    """

    @abstractmethod
    def create(self, **kwargs) -> bool:
        """
        Creates a backup of a file system object and registers its metadata.

        kwargs are whatever the implementation requires — it decides what
        fields are mandatory, what is optional, and what it fills in itself.
        Persists the registry after creation. Returns True if the backup was
        created and registered successfully, False otherwise. The Snapshot
        built internally is a private concern of the implementation — the
        caller receives only the bool. Must never raise.
        """
        ...

    @abstractmethod
    def restore(self, **kwargs) -> bool:
        """
        Restores a file system object to a previously captured state.

        kwargs are whatever the implementation requires to identify the target
        group and snapshot. Verifies integrity via checksum before and after
        restoration. Marks intermediate objects with .vakt.tmp or .vakt.old
        suffixes. Returns True if restoration completed successfully,
        False otherwise. Must never raise.
        """
        ...

    @abstractmethod
    def delete(self, **kwargs) -> bool:
        """
        Removes a snapshot and its physical backup file.

        kwargs are whatever the implementation requires to identify the target
        group and snapshot. Removes the physical backup file and persists the
        registry after deletion. Returns True if removal completed successfully,
        False otherwise. Must never raise.
        """
        ...

    @abstractmethod
    def show(self, **kwargs) -> Sequence[dict]:
        """
        Returns snapshot metadata across all groups as raw dictionaries.

        Invoked through the BluePrint flow — kwargs are the resolved output
        of the implementation's MethodSpec for this method, provided by the
        client during the management session. Each dict reflects the full
        internal representation of one Snapshot as the implementation stores
        it — the same structure used to reconstruct it. Returns an empty
        sequence if the registry contains no snapshots. Must never raise.
        """
        ...
