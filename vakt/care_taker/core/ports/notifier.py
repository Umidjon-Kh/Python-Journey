from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..event import Event
from ..instruction import Instruction
from ..user_choice import UserChoice


class BaseNotifier(ABC):
    """
    Abstract base class for all file system change notifiers.

    A Notifier is responsible for two things:
        1. Delivering a file system change notification to the user.
        2. Collecting the user's response as a sequence of UserChoice values.

    Notifier is the only component that interacts with the user directly.
    It does not make decisions - it only presents information and collects intent.
    All action logic belongs to the handlers themselves.

    Implementations:
        - DesktopNotifier - notify-send with action buttons (Linux desktop).
        - TerminalNotifier - prints to stdout, reads input() for response.
        - ServerNotifier - sends via webhook or messaging service.

    Notes:
        - If the user does not respond within a timeout, Notifier must
            return [UserChoice.IGNORE] as a safe default.
        - If some user responsibility choices is provided in instruction
            Notifier dont asks it for user again it silently uses it instead of
            user answer.
        - Notifier runs inside Dispatcher Thread - must not block indefinitely.
        - Notifier must never call handlers direclty, cause it handlers too.
    """

    @abstractmethod
    def notify(self, event: Event, instruction: Instruction) -> Sequence[UserChoice]:
        """
        Shows a notification and waits for user responds to
        collect user's response as a sequence nad return it to upper layer
        objects (dispatcher) as a sequence of UserChoice values.
        """
        ...
