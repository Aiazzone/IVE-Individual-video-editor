"""Actions for placing and arranging stickers."""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


@action(
    id="timeline.place_sticker",
    title_key="sticker.place",
    desc_key="Put a sticker on the Sticker lane, covering a stretch of the "
             "timeline. It appears centred; move it with "
             "timeline.set_clip_transform.",
    category="timeline",
    params={
        "sticker_id": Param(str, required=True),
        "at": Param(float, required=True, doc="Timeline seconds."),
        "duration": Param(float, required=True),
    },
)
def place_sticker(ctx, sticker_id: str, at: float, duration: float):
    if not ctx.require("project").place_sticker(sticker_id, at, duration):
        raise RuntimeError(f"Unknown sticker {sticker_id!r}")


@action(
    id="sticker.toggle_favorite",
    title_key="sticker.favorite",
    desc_key="Star a sticker, or unstar it. Starred stickers gather in the "
             "Favorites tab of the Stickers panel.",
    category="stickers",
    params={"sticker_id": Param(str, required=True)},
)
def toggle_favorite(ctx, sticker_id: str):
    settings = ctx.require("settings")
    favorites = [str(v) for v in (settings.get("sticker.favorites") or [])]
    if sticker_id in favorites:
        favorites.remove(sticker_id)
    else:
        favorites.append(sticker_id)
    settings.set("sticker.favorites", favorites)
    log.info("Sticker favourites now: %s", favorites)


@action(
    id="timeline.set_clip_transform",
    title_key="sticker.transform",
    desc_key="Reposition a sticker on the canvas: centre (x, y) in canvas "
             "fractions, scale as a fraction of the canvas height, rotation "
             "in degrees.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "x": Param(float, required=True),
        "y": Param(float, required=True),
        "scale": Param(float, required=True),
        "rotation": Param(float, required=False),
    },
)
def set_clip_transform(ctx, clip_id: str, x: float, y: float, scale: float,
                       rotation: float = 0.0):
    if not ctx.require("project").set_clip_transform(clip_id, x, y, scale,
                                                     rotation):
        raise RuntimeError(f"Unknown sticker clip {clip_id}")
