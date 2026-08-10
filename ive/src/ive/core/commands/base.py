"""Reversible commands.

Rule: no code writes to the project model except through a Command. That is
what makes undo complete instead of best-effort, and what lets the assistant
undo a whole natural-language request in one step.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Sequence

log = logging.getLogger(__name__)

__all__ = ["Command", "CompositeCommand", "CallbackCommand"]


class Command(ABC):
    """One reversible mutation."""

    #: Human-facing label, used by the undo menu. A translation key.
    label: str = "command.generic"

    @abstractmethod
    def do(self) -> None:
        """Apply the change. Must be safe to call again after :meth:`undo`."""

    @abstractmethod
    def undo(self) -> None:
        """Revert the change, restoring the exact previous state."""

    def merge_with(self, other: "Command") -> bool:
        """Absorb ``other`` into this command; return True when merged.

        Used to coalesce continuous interaction - dragging a clip or a slider
        must produce one undo step at release, not one per mouse move.
        """
        return False


class CompositeCommand(Command):
    """Several commands treated as one undo step."""

    def __init__(self, label: str, commands: Sequence[Command]) -> None:
        self.label = label
        self._commands = list(commands)

    def do(self) -> None:
        applied: list[Command] = []
        try:
            for command in self._commands:
                command.do()
                applied.append(command)
        except Exception:
            log.exception("Composite %r failed; rolling back %d commands",
                          self.label, len(applied))
            for command in reversed(applied):
                try:
                    command.undo()
                except Exception:
                    log.exception("Rollback failed for %s", command.label)
            raise

    def undo(self) -> None:
        for command in reversed(self._commands):
            command.undo()

    def __len__(self) -> int:
        return len(self._commands)


class CallbackCommand(Command):
    """Simple command built from two callables.

    Convenient for settings-like changes that have no dedicated command class.
    """

    def __init__(self, label: str, apply, revert) -> None:
        self.label = label
        self._apply = apply
        self._revert = revert

    def do(self) -> None:
        self._apply()

    def undo(self) -> None:
        self._revert()
