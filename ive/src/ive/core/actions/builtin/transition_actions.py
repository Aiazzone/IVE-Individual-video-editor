"""Actions for the transitions between clips."""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


@action(
    id="timeline.set_transition",
    title_key="transition.set",
    desc_key="Dress one edge of a video clip with a transition (or clear "
             "it with an empty transition_id). edge='out' is the cut "
             "towards what follows - the next clip is pulled back by the "
             "duration (the sequence shortens by that much), or black when "
             "this is the last clip. edge='in' is the intro from black, "
             "meaningful on the first clip.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True,
                         doc="The clip whose edge is dressed."),
        "transition_id": Param(str, required=True,
                               doc='"" removes the transition.'),
        "duration": Param(float, required=False, doc="Seconds; 0.1 to 5."),
        "edge": Param(str, required=False, doc='"out" (default) or "in".'),
    },
)
def set_transition(ctx, clip_id: str, transition_id: str,
                   duration: float = 0.5, edge: str = "out"):
    if not ctx.require("project").set_clip_transition(clip_id, transition_id,
                                                      duration, edge):
        raise RuntimeError(
            f"Cannot set transition {transition_id!r} on {clip_id}")
