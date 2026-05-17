from __future__ import annotations

from collections.abc import Sequence
from os import path as pth
from os import walk
from pathlib import Path
from queue import Queue
from threading import Thread
from time import monotonic

from inotify_simple import INotify
from inotify_simple import flags as _FLAGS

from ...core import BaseWatcher, Event
from ..semantic_types import InotifyEventType

# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

_PENDING_MAX_ITERATIONS: int = 2
"""
Number of read() iterations a MOVED_FROM event is kept in pending
before being emitted as DELETED. Iterations count is used instead of
one iteration to reduce false deletions in case MOVED_TO arrives in the next
batch due to timing between kernel delivery and read() batching.
"""

_READ_TIMEOUT: int = 500
"""
Maximum milliseconds inotify.read() blocks waiting for events.
Controls how often the main loop checks the shutdown event and
flushes expired pending moves.
"""

_MASK: int = (
    _FLAGS.CREATE
    | _FLAGS.DELETE
    | _FLAGS.ATTRIB
    | _FLAGS.ACCESS
    | _FLAGS.OPEN
    | _FLAGS.CLOSE_WRITE
    | _FLAGS.CLOSE_NOWRITE
    | _FLAGS.MOVED_FROM
    | _FLAGS.MOVED_TO
    | _FLAGS.EXCL_UNLINK
    | _FLAGS.DONT_FOLLOW
)
"""
Combined inotify mask applied to every watch descriptor.
System event IN_IGNORED, IN_UNMOUNT and IN_Q_OVERFLOW are delivered
by the kernel regardless of the mask and are handled internally.
Two specific flags IN_EXCL_UNLINK and IN_DONT_FOLLOW serves for:
    - IN_EXCL_UNLINK:
        suppresses events for files deleted from the directory,
        but still open by another process, reducing noise.
    - IN_DONT_FOLLOW:
        prevents following symlinks when adding watches,
        keeping observation within the expected directory tree.
"""

_FILE_MASK_TO_EVENT: dict[int, InotifyEventType] = {
    _FLAGS.ACCESS: InotifyEventType.FILE_ACCESSED,
    _FLAGS.ATTRIB: InotifyEventType.FILE_METADATA_CHANGED,
}
