"""The one command every project mutation uses: a memento.

Why snapshots instead of a hand-written inverse per operation: a timeline
edit rarely changes one thing. Removing a clip reflows every later clip;
a trim moves all its neighbours; removing a pool item deletes its clips
too. An inverse that replays those side effects backwards has to be kept
correct against every future change of the model - the exact class of bug
undo exists to prevent. A snapshot of the lists is a few kilobytes on a
model this size, and it is right by construction.

The command never touches Qt and never emits signals itself: after a
restore it calls back into the service, which owns the signals and the
autosave. Note the deep copy on RESTORE as well as on capture - installing
a stored list as the live one would let the next in-place edit corrupt the
history it came from.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Callable

from ive.core.commands.base import Command

log = logging.getLogger(__name__)

__all__ = ["ProjectEdit"]


class ProjectEdit(Command):
    """One reversible edit of the open project's timeline and/or pool."""

    def __init__(self, service, label: str, *, timeline: bool = True,
                 media: bool = False) -> None:
        self._service = service
        self.label = label
        self._timeline = timeline
        self._media = media
        self._before: dict[str, Any] | None = None
        self._after: dict[str, Any] | None = None
        #: push() executes do() on a command whose mutation already ran in
        #: capture(); the first do() must therefore be a no-op.
        self._fresh = True

    # ── recording ─────────────────────────────────────────────────────

    def capture(self, mutate: Callable[[], Any]) -> Any:
        """Snapshot, run ``mutate``, snapshot again.

        Returns whatever ``mutate`` returned; falsy means the model refused
        the edit (unknown id, misclick split) and NOTHING was changed - the
        caller must then drop this command instead of pushing it.
        """
        project = self._service._project
        before = self._snapshot(project)
        result = mutate()
        if not result:
            return result
        self._before = before
        self._after = self._snapshot(project)
        return result

    # ── Command ───────────────────────────────────────────────────────

    def do(self) -> None:
        if self._fresh:
            self._fresh = False
            return
        self._restore(self._after)

    def undo(self) -> None:
        self._restore(self._before)

    # ── internals ─────────────────────────────────────────────────────

    def _snapshot(self, project) -> dict[str, Any]:
        state: dict[str, Any] = {}
        if self._timeline:
            state["timeline"] = copy.deepcopy(project.timeline)
        if self._media:
            state["media"] = copy.deepcopy(project.media)
        return state

    def _restore(self, state: dict[str, Any] | None) -> None:
        project = self._service._project
        if project is None or state is None:
            # The stack is cleared on open/close, so this is a programming
            # error, not a user-reachable state - but undo must never crash.
            log.error("No project to restore %r into", self.label)
            return
        if self._timeline:
            project.timeline = copy.deepcopy(state["timeline"])
        if self._media:
            project.media = copy.deepcopy(state["media"])
        self._service._history_restored(media_changed=self._media,
                                        timeline_changed=self._timeline)
