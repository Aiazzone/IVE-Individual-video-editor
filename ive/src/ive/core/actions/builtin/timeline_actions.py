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
    id="timeline.set_clip_speed",
    title_key="timeline.speed",
    desc_key="Playback pace of one A/V clip: 0.5 is slow motion, 2 twice "
             "as fast. The clip keeps showing the same footage, so its "
             "timeline length changes and the track reflows. The pitch "
             "follows the pace.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "speed": Param(float, required=True, doc="0.1 to 8."),
    },
)
def set_clip_speed(ctx, clip_id: str, speed: float):
    if not ctx.require("project").set_clip_speed(clip_id, speed):
        raise RuntimeError(f"Clip {clip_id} cannot change pace")


@action(
    id="timeline.set_clip_crop",
    title_key="video.crop",
    desc_key="Crop an A/V clip's picture by edge insets, each a fraction "
             "of the source (0 to 0.45): left, top, right, bottom. All "
             "zeros removes the crop.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "left": Param(float, required=False),
        "top": Param(float, required=False),
        "right": Param(float, required=False),
        "bottom": Param(float, required=False),
    },
)
def set_clip_crop(ctx, clip_id: str, left: float = 0.0, top: float = 0.0,
                  right: float = 0.0, bottom: float = 0.0):
    if not ctx.require("project").set_clip_crop(clip_id, left, top,
                                                right, bottom):
        raise RuntimeError(f"Clip {clip_id} cannot be cropped")


@action(
    id="timeline.set_clip_opacity",
    title_key="video.opacity",
    desc_key="Fade an A/V clip: 1 is opaque, towards 0 the picture "
             "dissolves into what sits underneath it.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "opacity": Param(float, required=True),
    },
)
def set_clip_opacity(ctx, clip_id: str, opacity: float):
    if not ctx.require("project").set_clip_opacity(clip_id, opacity):
        raise RuntimeError(f"Clip {clip_id} has no opacity to set")


@action(
    id="timeline.set_clip_keyframe",
    title_key="video.keyframe",
    desc_key="Pin an A/V clip's transform/opacity at a clip-local time "
             "(seconds): any of x, y, scale, rotation, opacity. Between "
             "pins the values run linearly; a pin already at that time "
             "is replaced. Pinning a transform floats the clip.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "t": Param(float, required=True, doc="Clip-local seconds."),
        "x": Param(float, required=False),
        "y": Param(float, required=False),
        "scale": Param(float, required=False),
        "rotation": Param(float, required=False),
        "opacity": Param(float, required=False),
    },
)
def set_clip_keyframe(ctx, clip_id: str, t: float, x=None, y=None,
                      scale=None, rotation=None, opacity=None):
    values = {key: value for key, value in
              (("x", x), ("y", y), ("scale", scale),
               ("rotation", rotation), ("opacity", opacity))
              if value is not None}
    if not ctx.require("project").set_clip_keyframe(clip_id, t, values):
        raise RuntimeError(
            f"No keyframe landed on {clip_id} (no values, or not an A/V "
            f"clip, or t outside it)")


@action(
    id="timeline.remove_clip_keyframe",
    title_key="video.keyframe_remove",
    desc_key="Remove the keyframe standing at a clip-local time.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "t": Param(float, required=True, doc="Clip-local seconds."),
    },
)
def remove_clip_keyframe(ctx, clip_id: str, t: float):
    if not ctx.require("project").remove_clip_keyframe(clip_id, t):
        raise RuntimeError(f"No keyframe at {t:.2f}s on {clip_id}")


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
    id="timeline.remove_clips",
    title_key="timeline.remove_clip",
    desc_key="Remove several clips at once - a whole selection, one "
             "undo step.",
    category="timeline",
    params={"clip_ids": Param(list, required=True)},
)
def remove_clips(ctx, clip_ids: list):
    if not ctx.require("project").remove_clips(list(clip_ids or [])):
        raise RuntimeError("Nothing to remove")


@action(
    id="timeline.split_at_playhead",
    title_key="timeline.split",
    desc_key="Split the A/V clip under the playhead in two, right where "
             "the playhead stands.",
    category="timeline",
    shortcut="Ctrl+B",
)
def split_at_playhead(ctx):
    playback = ctx.require("playback")
    project = ctx.require("project")
    at = float(getattr(playback, "positionSeconds", 0.0) or 0.0)
    target = next((c for c in project.timelineClips
                   if c["track"] == 0 and c["start"] + 0.05 < at
                   < c["end"] - 0.05), None)
    if target is None:
        raise RuntimeError("No clip under the playhead to split")
    if not project.split_clip(target["id"], at):
        raise RuntimeError("The split failed")


@action(
    id="timeline.copy_selection",
    title_key="timeline.copy",
    desc_key="Copy the selected clips (the whole multi-selection) for a "
             "later paste.",
    category="timeline",
    shortcut="Ctrl+C",
)
def copy_selection(ctx):
    shell = ctx.require("shell")
    ids = shell.selected_ids()
    if not ids or ctx.require("project").copy_clips(ids) == 0:
        raise RuntimeError("Nothing selected to copy")


@action(
    id="timeline.paste",
    title_key="timeline.paste",
    desc_key="Paste the copied clips at the playhead (or at the end when "
             "nothing plays), keeping their spacing. One undo step.",
    category="timeline",
    shortcut="Ctrl+V",
)
def paste_clips(ctx):
    playback = ctx.require("playback")
    at = (float(playback.positionSeconds)
          if getattr(playback, "hasMedia", False) else -1.0)
    if ctx.require("project").paste_clips(at) == 0:
        raise RuntimeError("Nothing to paste")


@action(
    id="timeline.drop_media",
    title_key="timeline.place_media",
    desc_key="Import files or folders and lay them on the A/V track back "
             "to back from a point in time - the dropped-on-the-timeline "
             "gesture, one undo step for the whole landing.",
    category="timeline",
    params={
        "paths": Param(list, required=True,
                       doc="Files or folders (paths or file:// URLs)."),
        "at": Param(float, required=True,
                    doc="Seconds on the timeline where the first clip lands."),
    },
)
def drop_media(ctx, paths: list, at: float):
    # Asynchronous: the files are probed on a worker and the clips land
    # where the pointer said once the probing is done.
    if ctx.require("project").import_and_place_async(list(paths or []),
                                                     at) == 0:
        raise RuntimeError("Nothing usable was dropped")


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
        "start": Param(float, required=False,
                       doc="New start on a free lane, so a head trim moves "
                           "the LEFT edge. Omit (or negative) to stay put; "
                           "track 0 reflows regardless."),
    },
)
def trim_clip(ctx, clip_id: str, source_in: float, duration: float,
              start: float = -1.0):
    if not ctx.require("project").trim_clip(clip_id, source_in, duration,
                                            start):
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
