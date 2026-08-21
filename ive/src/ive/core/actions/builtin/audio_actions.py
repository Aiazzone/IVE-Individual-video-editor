"""Actions for the audio of a clip: effect recipes, fades, favourites."""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


@action(
    id="timeline.set_clip_audio_effect",
    title_key="audio.set_effect",
    desc_key="Apply an audio effect recipe (EQ, compression, normalisation, "
             "a telephone voice...) to one clip's sound. Empty effect_id "
             "removes it.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "effect_id": Param(str, required=False,
                           doc="An id from the audio catalogue; '' = none."),
    },
)
def set_clip_audio_effect(ctx, clip_id: str, effect_id: str = ""):
    if not ctx.require("project").set_clip_audio_effect(clip_id, effect_id):
        raise RuntimeError(f"Unknown clip {clip_id} or effect {effect_id!r}")


@action(
    id="timeline.set_clip_fades",
    title_key="audio.fades",
    desc_key="Audio fade in at the clip's head and fade out at its tail, "
             "in seconds (0 = none).",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "fade_in": Param(float, required=False),
        "fade_out": Param(float, required=False),
    },
)
def set_clip_fades(ctx, clip_id: str, fade_in: float = 0.0,
                   fade_out: float = 0.0):
    if not ctx.require("project").set_clip_fades(clip_id, fade_in, fade_out):
        raise RuntimeError(f"Unknown clip {clip_id}")


@action(
    id="audio.toggle_favorite",
    title_key="audio.favorite",
    desc_key="Star an audio effect, or unstar it. Starred effects gather "
             "at the top of the Audio panel.",
    category="audio",
    params={"effect_id": Param(str, required=True)},
)
def toggle_favorite(ctx, effect_id: str):
    settings = ctx.require("settings")
    favorites = [str(v) for v in (settings.get("audio.favorites") or [])]
    if effect_id in favorites:
        favorites.remove(effect_id)
    else:
        favorites.append(effect_id)
    settings.set("audio.favorites", favorites)
    log.info("Audio favourites now: %s", favorites)
