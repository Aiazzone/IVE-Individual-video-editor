"""Undo stack with transactions and coalescing.

Every mutation of the project model goes through a :class:`Command`. The UI
never writes to the model directly, which is what makes undo complete rather
than best-effort.

Transactions matter for the assistant: a natural-language request that runs
five actions must be undone by a single Ctrl+Z.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from PySide6.QtCore import QObject, Signal

from ive.core.commands.base import Command, CompositeCommand

log = logging.getLogger(__name__)

__all__ = ["UndoStack"]

DEFAULT_LIMIT = 200


class UndoStack(QObject):
    """Holds executed commands and replays them backwards on demand."""

    changed = Signal()

    def __init__(self, limit: int = DEFAULT_LIMIT, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._limit = limit
        self._done: list[Command] = []
        self._undone: list[Command] = []
        self._transaction: list[Command] | None = None
        self._transaction_label = ""

    # ── state ─────────────────────────────────────────────────────────

    @property
    def can_undo(self) -> bool:
        return bool(self._done)

    @property
    def can_redo(self) -> bool:
        return bool(self._undone)

    @property
    def undo_label(self) -> str:
        return self._done[-1].label if self._done else ""

    @property
    def redo_label(self) -> str:
        return self._undone[-1].label if self._undone else ""

    def depth(self) -> int:
        return len(self._done)

    # ── mutation ──────────────────────────────────────────────────────

    def push(self, command: Command) -> None:
        """Execute ``command`` and record it.

        Inside a transaction the command is collected instead, so the whole
        group becomes one undo step.
        """
        command.do()

        if self._transaction is not None:
            self._transaction.append(command)
            return

        if self._done and self._done[-1].merge_with(command):
            # Coalesced into the previous step (drag, slider, typing).
            self._undone.clear()
            self.changed.emit()
            return

        self._done.append(command)
        self._undone.clear()
        if len(self._done) > self._limit:
            dropped = self._done.pop(0)
            log.debug("Undo limit reached, dropping %s", dropped.label)
        self.changed.emit()

    def undo(self) -> bool:
        if not self._done:
            return False
        command = self._done.pop()
        try:
            command.undo()
        except Exception:
            log.exception("Undo failed for %s; stack cleared to stay consistent", command.label)
            self._done.clear()
            self._undone.clear()
            self.changed.emit()
            return False
        self._undone.append(command)
        log.info("Undo: %s", command.label)
        self.changed.emit()
        return True

    def redo(self) -> bool:
        if not self._undone:
            return False
        command = self._undone.pop()
        try:
            command.do()
        except Exception:
            log.exception("Redo failed for %s; stack cleared to stay consistent", command.label)
            self._done.clear()
            self._undone.clear()
            self.changed.emit()
            return False
        self._done.append(command)
        log.info("Redo: %s", command.label)
        self.changed.emit()
        return True

    def clear(self) -> None:
        self._done.clear()
        self._undone.clear()
        self.changed.emit()

    # ── transactions ──────────────────────────────────────────────────

    @contextmanager
    def transaction(self, label: str) -> Iterator[None]:
        """Group every command pushed inside the block into one undo step."""
        if self._transaction is not None:
            # Nested transactions simply join the outer one.
            yield
            return

        self._transaction = []
        self._transaction_label = label
        try:
            yield
        except Exception:
            collected = self._transaction
            self._transaction = None
            log.exception("Transaction %r failed; rolling back %d commands",
                          label, len(collected))
            for command in reversed(collected):
                try:
                    command.undo()
                except Exception:
                    log.exception("Rollback failed for %s", command.label)
            self.changed.emit()
            raise
        else:
            collected = self._transaction
            self._transaction = None
            if not collected:
                return
            if len(collected) == 1:
                self._done.append(collected[0])
            else:
                self._done.append(CompositeCommand(label, collected))
            self._undone.clear()
            if len(self._done) > self._limit:
                self._done.pop(0)
            self.changed.emit()
