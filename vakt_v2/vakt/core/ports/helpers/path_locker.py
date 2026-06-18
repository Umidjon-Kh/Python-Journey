from __future__ import annotations

from abc import abstractmethod

from ..protocols import AssemblyProtocol


class BasePathLocker(AssemblyProtocol):
    """
    Abstract base class for all file system path locker implementations.

    PathLocker is simultaneously responsible for three things:
        1. Blocking access to physical file system objects at the given path.
        2. Releasing those objects when requested.
        3. Thread-safety — implementations may be used by multiple objects
            concurrently and must avoid race conditions.

    This gives other components the ability to safely interact with a file system
    object during critical operations without the risk of external modification or
    reading. PathLocker is a helper infrastructure component — it is not a core
    pipeline element and does not participate in event processing directly.

    Marking Protocol:
        All implementations must rename locked objects by appending the .vakt.lock
        suffix, regardless of their internal locking mechanism. This creates a
        unified visible contract across all implementations — other objects do not
        need to guess or check implementation details. A .vakt.lock suffix always
        and reliably means the object is currently locked. This also allows
        implementations that cannot lock at the OS kernel level (e.g., chmod-based)
        to use renaming as an additional safety layer on top of their own mechanism.
        External users and tools can also identify and manually recover any locked
        objects by looking for this suffix.

    Marking and Guarantee Protocol:
        Beyond marking, all implementations must guarantee that every object they
        lock will eventually be released — even if the server crashes. To enforce
        this guarantee, every implementation must maintain an internal persistent
        lock store that records all currently locked object paths. On
        re-initialization the implementation must load this store and release
        (recover) all previously locked objects before resuming normal operation.
        This is mandatory — locked objects may be critically important and must
        never be left in an unrecoverable state.

        The lock store must be kept in a location protected from untrusted or
        suspicious external processes. The recommended location is the directory
        pointed to by the Vakt Sanctum server environment variable — a designated
        safe directory guaranteed not to be accessed or tampered with by unknown
        processes. All modifications to the lock store must be persisted immediately.
        Atomic operations are strongly recommended to avoid corruption on crash.

    occupied_paths Protocol:
        When PathLocker renames a file system object to apply the .vakt.lock
        suffix, the Watcher detects this rename as a file system event. Whether
        the Watcher can identify it as self-generated depends entirely on the
        implementation — deep-integration Watchers can detect the initiating
        process directly, surface-level ones cannot. PathLocker has no visibility
        into which Watcher is deployed and must never depend on that. All
        implementations must declare occupied_paths in Configure.internal_reqs
        and register their path claims unconditionally — this guarantees correct
        filtering regardless of which Watcher implementation is in use

        PathLocker registers and releases exact claims only. Before starting any
        file system operation — renaming to apply or remove the .vakt.lock suffix —
        the implementation registers an exact claim:
            occupied_paths[path] = occupied_paths.get(path, 0) + 1
        Once all operations on that path are complete, it releases it:
            occupied_paths[path] -= 1
            if occupied_paths[path] == 0:
                del occupied_paths[path]

        PathLocker never registers recursive claims. Whether the surrounding
        operation covers a full directory tree is not something PathLocker knows
        or decides — NYR. Callers that need recursive coverage register it
        themselves in occupied_paths["recursive"] after PathLocker has registered
        the exact claim on their behalf.

        Path Registration Rule:
            Always register the original clean path — the one that existed before
            any .vakt.** rename. When file.txt is renamed to file.txt.vakt.lock,
            the claim goes under "file.txt", not "file.txt.vakt.lock". Registering
            the suffixed path would break the Watcher's lookup — it strips the
            .vakt. suffix to recover the original path and expects to find exactly
            that in occupied_paths. For the full suffix-stripping algorithm see
            BaseWatcher and Configure documentation.

    PathLocker Categories:
        Like handlers, PathLocker implementations are not formally categorized in
        the codebase but can be classified by their locking scope:

        MultiPathLocker:
            Can lock multiple file system objects simultaneously. Because it manages
            many locked objects at once, a registry is the natural internal structure
            for tracking all currently locked paths and their metadata. The release()
            method accepts path explicitly so that a specific object can be released
            independently without affecting others. Suited for environments where
            concurrent critical operations on different paths are expected.

        SinglePathLocker:
            Can lock only one file system object at a time. Objects that need access
            to the same locked path must wait, forming a natural queue of pending
            operations. While this may seem limited compared to MultiPathLocker, it
            is a deliberate choice for specific Observer deployment environments
            where ordered exclusive access is preferable. SinglePathLockers also
            require a persistent store for crash recovery — simpler than a full
            registry, but subject to the same crash guarantee.

    Example implementations:
        - FcntlPathLocker: Linux/macOS, uses fcntl.flock().
        - WindowsPathLocker: Windows, uses msvcrt.locking().
        - ChmodPathLocker: Linux, uses chmod to restrict permissions.

    Notes:
        - PathLocker operates at the OS level, not the thread level. It blocks
            access from external processes, not just threads within the same process.
        - All objects that use PathLocker must call release() after finishing their
            work. The persistent store guarantee exists only for crash scenarios —
            normal operation requires explicit release.
        - All implementations must persist their lock store after every modification.
        - The base abstract class does not require __enter__ and __exit__. Implementations
            that want context manager support may add it themselves. However, this is
            worth considering carefully — objects that declare a non-concrete
            BasePathLocker in their requirements have no guarantee the implementation
            supports the context manager protocol, which can lead to silent failures.
        - Must never propagate exceptions to the caller. All errors must be caught
            and handled internally.
    """

    @abstractmethod
    def acquire(self, path: str) -> None:
        """
        Locks the file system object at path by renaming it with the .vakt.lock
        suffix and recording it in the persistent lock store.

        Registers an exact claim in occupied_paths under the original clean path
        before any file system operation, so the Watcher silently drops all
        self-generated rename events. Releases the claim once all acquire
        operations are complete. Must never propagate exceptions.
        """
        ...

    @abstractmethod
    def release(self, path: str) -> None:
        """
        Releases the lock on the file system object at path by restoring its
        original name and removing it from the persistent lock store.

        Registers an exact claim in occupied_paths under the original clean path
        before any file system operation, so the Watcher silently drops all
        self-generated rename events. Releases the claim once all release
        operations are complete. Removes path from occupied_paths entirely when
        the count reaches zero. path is always the original path before locking —
        never the .vakt.lock path. Silently ignores if path is not currently locked.
        Must never propagate exceptions.
        """
        ...
