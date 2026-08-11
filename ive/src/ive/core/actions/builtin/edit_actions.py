"""Undo and redo.

Thin on purpose: the UndoStack owns the semantics, these actions only make
them reachable from the UI, a script or the assistant like everything else.
Undoing with an empty stack is a no-op, not an error - Ctrl+Z held down
must never end in a dialog.
"""

from __future__ import annotations

import logging

from ive.core.actions.registry import action

log = logging.getLogger(__name__)


@action(
    id="edit.undo",
    title_key="timeline.undo",
    desc_key="Revert the last edit of the project.",
    category="edit",
    shortcut="Ctrl+Z",
)
def undo(ctx):
    ctx.require("history").undo()


@action(
    id="edit.redo",
    title_key="timeline.redo",
    desc_key="Apply again the edit that was just undone.",
    category="edit",
    shortcut="Ctrl+Y",
)
def redo(ctx):
    ctx.require("history").redo()
