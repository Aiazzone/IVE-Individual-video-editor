"""Actions for the colour-effect catalogue."""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


@action(
    id="color.toggle_favorite",
    title_key="color.favorite",
    desc_key="Star a colour effect, or unstar it. Starred effects gather "
             "in the Favorites tab of the Color panel.",
    category="color",
    params={"effect_id": Param(str, required=True)},
)
def toggle_favorite(ctx, effect_id: str):
    settings = ctx.require("settings")
    favorites = [str(v) for v in (settings.get("color.favorites") or [])]
    if effect_id in favorites:
        favorites.remove(effect_id)
    else:
        favorites.append(effect_id)
    settings.set("color.favorites", favorites)
    log.info("Colour favourites now: %s", favorites)


@action(
    id="timeline.place_grade",
    title_key="color.adjust",
    desc_key="Put an Adjust clip on the Color lane: manual colour dials "
             "(brightness, contrast, saturation, gamma, temperature, "
             "tint, shadows, highlights, vignette) with no recipe "
             "underneath. Over a video clip it adopts that clip's span.",
    category="color",
    params={
        "at": Param(float, required=False,
                    doc="Timeline seconds; the UI passes the playhead."),
    },
)
def place_grade(ctx, at: float = 0.0):
    if not ctx.require("project").place_grade(at):
        raise RuntimeError("Could not place the Adjust clip")


@action(
    id="timeline.set_clip_grade",
    title_key="color.grade",
    desc_key="Turn one dial of a Color-lane clip's manual grade. Keys: "
             "brightness (-0.5..0.5), contrast (0.2..2, 1 = untouched), "
             "saturation (0..2), gamma (0.3..2.5), temperature (-1..1), "
             "tint (-1..1), shadows (-1..1), highlights (-1..1), "
             "vignette (0..1). The default value removes the dial.",
    category="color",
    params={
        "clip_id": Param(str, required=True),
        "key": Param(str, required=True),
        "value": Param(float, required=True),
    },
)
def set_clip_grade(ctx, clip_id: str, key: str, value: float):
    if not ctx.require("project").set_clip_grade(clip_id, key, value):
        raise RuntimeError(
            f"Clip {clip_id} is not on the Color lane, or {key!r} is not "
            f"a dial")
