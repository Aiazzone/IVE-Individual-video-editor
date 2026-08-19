"""Actions for the transitions between clips."""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


@action(
    id="timeline.set_transition",
    title_key="transition.set",
    desc_key="Dress the cut AFTER a video clip with a transition (or clear "
             "it with an empty transition_id). The next clip is pulled back "
             "by the transition's duration, so the sequence shortens by "
             "that much and no extra source material is needed.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True,
                         doc="The OUTGOING clip: the transition follows it."),
        "transition_id": Param(str, required=True,
                               doc='"" removes the transition.'),
        "duration": Param(float, required=False, doc="Seconds; 0.1 to 5."),
    },
)
def set_transition(ctx, clip_id: str, transition_id: str,
                   duration: float = 0.5):
    if not ctx.require("project").set_clip_transition(clip_id, transition_id,
                                                      duration):
        raise RuntimeError(
            f"Cannot set transition {transition_id!r} on {clip_id}")
