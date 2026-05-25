from __future__ import annotations

from ...core import BaseHandler, EventContext, InstructionType, ToolKit


class BackupInvoker(BaseHandler):
    """
    BackupInvoker is an aggregator handler responsible for calling the create
    method on a helper object that implements BaseSnapshotsRegistryStore.
    That imeplementation, in turn, creates a backup (reserve copy) of the
    current state at the path taken from the incoming Event.

    Why it is an Ivoker:
        BackupInvoker itself contains no logic or knowledge of how or where
        to create backup. It acts only as a mediater (aggregator) that initiates
        the call for a backup event, and it does so only in sepcific cases.

    Why the Invoker MUST wait a certain number of encounters with the same Event:
        This is done to give other handler implementations - specifically those
        belonging to the category of ResponseCollector, Commander, and similar - an
        opportunity to add instructions or request that certain actions be performed.

        Bacause the Dispatcher loop is not an ordered loop but still provides waiting
        mechanism, we allow other handlers to act until at least one of them can make
        progress with the current Event.

    Purpose of the _met toggle:
        _met is a flag (toggle) that answers the question: "Hase we already seen
        the current Event?". It is needed so that in the first cycle, we give other
        handlers a chance to issue a backup command. If no one issues such a command,
        it is interpreted as meaning that this Event will never trigger a backup for
        for the current state of file system object in the path.

        This is a standard approach that provides exactly one opportunity for other
        handlers to give a backup instruction. If you need to configure the number of
        iterations, imeplement you own logic, this is the basic minimum.

    Why "BackupInvoker is done" is stored in ctx.metadata:
        This is done to remember and mark whether we have finished working with
        the current Event. This flag does not answer the question "Was a backup created?".
        Instead, it answers: "Will we still interact with this event?".

        This design choice is intentional: we do not rely on the safety guard of the
        Dispatcher's Handlers Loop mechanism. Instead, we rely on our own markers for
        this Event, independent of external conditions. This allows the processing
        to finish correctly, avoiding infinite loops, regardless of the state of
        external components.

    Why the Snapshot is stored in metadta only when backup is created successfully:
        This allows other handlers to interact with the resulting snapshot
        as they see fit. For example, it enables a SnapshotsRotator handler that
        keeps only limited number of snapshots for a single file system object.
        This is only one example - feel free to extend with your own use cases.

    Why the BACKUP flag is added only only when backup is created successfully,
    while processed_handlers is always incremented:
        Because:
            - performed tracks only what was successfully completed (the actual action).
            - processed_handlers answers a different question: "How many handlers have
                processed this Event (regardless of whether each individual action succeeded)."

    Notes:
        - BackupInvoker uses ToolKit because it necessarily needs
            a helper object that implements BaseSnapshotsRegistryStore.
        - Even if backup is not successfully created, the processed_handlers
            value will always increase.
    """

    _INTERACTION_DONE_MARK = "BackupInvoker is done"

    def __init__(self, toolkit: ToolKit) -> None:
        """
        Initializes the handler, saves a reference to the ToolKit,
        and sets an internal event detection flag.
        """
        self._toolkit: ToolKit = toolkit
        self._met: bool = False

    def can_handle(self, ctx: EventContext) -> bool:
        """
        Returns False on first contact to five other handlers a chance
        to issue a backup instruction. Returns False again on second contact
        if no backup instruction was issued, marking itself as done.
        Returns True only if InstructionType.BACKUP is present in instruction.types.
        """
        if (
            ctx.instruction.types
            and InstructionType.BACKUP not in ctx.instruction.types
        ):
            if self._met:
                self._met = False
                ctx.metadata[self._INTERACTION_DONE_MARK] = True
                ctx.handlers_count -= 1
                return False

            self._met = True
            return False

        return True

    def handle(self, ctx: EventContext) -> None:
        """
        Calls snapshots_registry.create() and stores the result in ctx.metadata.
        Appends InstructionType.BACKUP to ctx.performed only if backup succeeded.
        Always increments ctx.processed_handlers regardless of backup result.
        """
        snapshot = self._toolkit.snapshots_registry.create(ctx.event)

        if snapshot.backup_path:
            ctx.performed.append(InstructionType.BACKUP)  # type: ignore[assignment]
            self._met = False

        ctx.metadata[self.__class__.__name__] = snapshot
        ctx.processed_handlers += 1

    def is_done(self, ctx: EventContext) -> bool:
        """
        Returns True if the interaction done mark is set in ctx.metadata,
        indicating this handler will no longer interact with the current event.
        """
        return ctx.metadata.get(self._INTERACTION_DONE_MARK, False)
