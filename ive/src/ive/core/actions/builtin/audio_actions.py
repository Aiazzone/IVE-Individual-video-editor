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


@action(
    id="timeline.place_music",
    title_key="music.place",
    desc_key="Lay a track from the music library (or any audio file by "
             "path) on the Music lane at a point in time; with cover=true "
             "it repeats until the cut ends.",
    category="timeline",
    params={
        "track_id": Param(str, required=False,
                          doc="An id from the music library..."),
        "path": Param(str, required=False, doc="...or an audio file."),
        "at": Param(float, required=False, doc="Timeline seconds; the UI "
                                               "passes the playhead."),
        "cover": Param(bool, required=False),
    },
)
def place_music(ctx, track_id: str = "", path: str = "", at: float = 0.0,
                cover: bool = False):
    if track_id:
        from ive.music.library import track_by_id

        track = track_by_id(track_id)
        if track is None:
            raise RuntimeError(f"Unknown track {track_id!r}")
        path = track["path"]
    if not path:
        raise RuntimeError("place_music needs a track_id or a path")
    if not ctx.require("project").place_music(path, at, cover):
        raise RuntimeError(f"Could not place {path}")


@action(
    id="music.toggle_favorite",
    title_key="music.favorite",
    desc_key="Star a music track, or unstar it.",
    category="audio",
    params={"track_id": Param(str, required=True)},
)
def toggle_music_favorite(ctx, track_id: str):
    settings = ctx.require("settings")
    favorites = [str(v) for v in (settings.get("music.favorites") or [])]
    if track_id in favorites:
        favorites.remove(track_id)
    else:
        favorites.append(track_id)
    settings.set("music.favorites", favorites)


@action(
    id="timeline.set_clip_ducking",
    title_key="audio.duck",
    desc_key="Make a music clip dip under the cut's speech (ducking): on "
             "or off, and by how many dB. How speech is detected is the "
             "global audio.ducking_mode preference.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "enabled": Param(bool, required=True),
        "depth_db": Param(float, required=False,
                          doc="How far the bed dips, 0-30 dB (default 12)."),
    },
)
def set_clip_ducking(ctx, clip_id: str, enabled: bool, depth_db: float = 12.0):
    if not ctx.require("project").set_clip_ducking(clip_id, enabled, depth_db):
        raise RuntimeError(f"Unknown clip {clip_id}")


@action(
    id="audio.set_ducking_mode",
    title_key="settings.ducking_mode",
    desc_key="How ducking detects speech: 'simple' (sound level) or "
             "'smart' (voice recognition model, falls back to simple "
             "while no model is installed).",
    category="settings",
    params={"mode": Param(str, required=True, doc="simple | smart")},
)
def set_ducking_mode(ctx, mode: str):
    ctx.require("settings").set("audio.ducking_mode", mode)
