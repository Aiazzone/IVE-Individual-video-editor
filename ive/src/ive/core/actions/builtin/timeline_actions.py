"""Actions for arranging clips on the timeline."""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


@action(
    id="timeline.place_media",
    title_key="timeline.place_media",
    desc_key="Put a media pool item on the timeline. Without 'at' it goes to "
             "the end; with it, at that point in seconds.",
    category="timeline",
    params={
        "media_id": Param(str, required=True),
        "at": Param(float, required=False, doc="Seconds. Omit to append."),
    },
)
def place_media(ctx, media_id: str, at: float = -1.0):
    if not ctx.require("project").place_media(media_id, at):
        raise RuntimeError(f"Could not place media {media_id}")


@action(
    id="timeline.move_clip",
    title_key="timeline.move_clip",
    desc_key="Move a clip to another point in time; the others close up around it.",
    category="timeline",
    params={"clip_id": Param(str, required=True), "to": Param(float, required=True)},
)
def move_clip(ctx, clip_id: str, to: float):
    ctx.require("project").move_clip(clip_id, to)


@action(
    id="timeline.remove_clip",
    title_key="timeline.remove_clip",
    desc_key="Take a clip off the timeline. The media stays in the pool.",
    category="timeline",
    params={"clip_id": Param(str, required=True)},
)
def remove_clip(ctx, clip_id: str):
    ctx.require("project").remove_clip(clip_id)


@action(
    id="timeline.split_clip",
    title_key="timeline.split",
    desc_key="Cut a clip in two at a point on the timeline; both halves keep "
             "playing the same material.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "at": Param(float, required=True, doc="Timeline seconds; the UI "
                                              "passes the playhead."),
    },
)
def split_clip(ctx, clip_id: str, at: float):
    if not ctx.require("project").split_clip(clip_id, at):
        raise RuntimeError(
            f"Cannot split {clip_id} at {at:.2f}s: the point is not inside it")


@action(
    id="timeline.set_clip_volume",
    title_key="timeline.volume",
    desc_key="Audio gain of one clip: 0 is silent, 1 as recorded, up to 2.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "volume": Param(float, required=True),
    },
)
def set_clip_volume(ctx, clip_id: str, volume: float):
    if not ctx.require("project").set_clip_volume(clip_id, volume):
        raise RuntimeError(f"Unknown clip {clip_id}")


@action(
    id="timeline.place_effect",
    title_key="timeline.place_effect",
    desc_key="Put a colour effect on the Color lane, covering a stretch of "
             "the timeline.",
    category="timeline",
    params={
        "effect_id": Param(str, required=True),
        "at": Param(float, required=True, doc="Timeline seconds."),
        "duration": Param(float, required=True),
    },
)
def place_effect(ctx, effect_id: str, at: float, duration: float):
    if not ctx.require("project").place_effect(effect_id, at, duration):
        raise RuntimeError(f"Unknown colour effect {effect_id!r}")


@action(
    id="timeline.trim_clip",
    title_key="timeline.trim",
    desc_key="Resize a clip: new offset into its source and new duration, "
             "clamped to the material the file actually has.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "source_in": Param(float, required=True),
        "duration": Param(float, required=True),
    },
)
def trim_clip(ctx, clip_id: str, source_in: float, duration: float):
    if not ctx.require("project").trim_clip(clip_id, source_in, duration):
        raise RuntimeError(f"Unknown clip {clip_id}")


@action(
    id="timeline.set_clip_muted",
    title_key="timeline.mute_clip",
    desc_key="Silence one clip, or unsilence it. Muted is a state, not a "
             "volume: unmuting restores the loudness the user had set.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "muted": Param(bool, required=True),
    },
)
def set_clip_muted(ctx, clip_id: str, muted: bool):
    if not ctx.require("project").set_clip_muted(clip_id, muted):
        raise RuntimeError(f"Unknown clip {clip_id}")


@action(
    id="timeline.set_clip_audio",
    title_key="timeline.remove_audio",
    desc_key="Remove one clip's sound from the sequence, or bring it back. "
             "The clip's volume is remembered across the round trip.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "enabled": Param(bool, required=True),
    },
)
def set_clip_audio(ctx, clip_id: str, enabled: bool):
    if not ctx.require("project").set_clip_audio(clip_id, enabled):
        raise RuntimeError(f"Unknown clip {clip_id}")


@action(
    id="timeline.preview_clip",
    title_key="timeline.preview_clip",
    desc_key="Load the media behind a timeline clip into the preview.",
    category="timeline",
    params={"clip_id": Param(str, required=True)},
)
def preview_clip(ctx, clip_id: str):
    path = ctx.require("project").clip_media_path(clip_id)
    if not path:
        raise RuntimeError(f"Unknown clip {clip_id}")
    ctx.require("playback").open(path)
