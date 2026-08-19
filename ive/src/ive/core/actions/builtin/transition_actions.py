"""Actions for the transitions between clips."""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


@action(
    id="transition.toggle_favorite",
    title_key="transition.favorite",
    desc_key="Star a transition, or unstar it. Starred transitions gather "
             "in the Favorites tab of the Transitions panel.",
    category="transitions",
    params={"transition_id": Param(str, required=True)},
)
def toggle_favorite(ctx, transition_id: str):
    settings = ctx.require("settings")
    favorites = [str(v) for v in (settings.get("transition.favorites") or [])]
    if transition_id in favorites:
        favorites.remove(transition_id)
    else:
        favorites.append(transition_id)
    settings.set("transition.favorites", favorites)
    log.info("Transition favourites now: %s", favorites)


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
