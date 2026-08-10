"""Actions for opening media and driving playback.

The transport buttons, the keyboard shortcuts and the assistant all go through
these, so "play" means the same thing however it is asked for.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ive.core.actions.registry import Param, action
from ive.utils.paths import local_path_from_url

log = logging.getLogger(__name__)


@action(
    id="media.open",
    title_key="media.open",
    desc_key="Open a video file in the preview.",
    category="media",
    params={"path": Param(str, required=True, doc="Absolute path to a media file.")},
    shortcut="Ctrl+O",
)
def open_media(ctx, path: str):
    playback = ctx.require("playback")
    resolved = Path(local_path_from_url(path))
    if not playback.open(resolved):
        raise RuntimeError(f"Could not open {resolved.name}")


@action(
    id="media.close",
    title_key="media.close",
    desc_key="Close the media currently loaded in the preview.",
    category="media",
)
def close_media(ctx):
    ctx.require("playback").close()


@action(
    id="playback.toggle",
    title_key="transport.play",
    desc_key="Start or stop playback.",
    category="playback",
    shortcut="Space",
)
def toggle_playback(ctx):
    ctx.require("playback").toggle()


@action(
    id="playback.seek",
    title_key="transport.start",
    desc_key="Move the playhead to a frame number.",
    category="playback",
    params={"frame": Param(int, required=True)},
)
def seek(ctx, frame: int):
    ctx.require("playback").seek(frame)


@action(
    id="playback.seek_seconds",
    title_key="transport.start",
    desc_key="Move the playhead to a position in seconds.",
    category="playback",
    params={"seconds": Param(float, required=True)},
)
def seek_seconds(ctx, seconds: float):
    ctx.require("playback").seek_seconds(seconds)


@action(
    id="playback.step",
    title_key="transport.next_frame",
    desc_key="Move by a number of frames; negative goes backwards.",
    category="playback",
    params={"frames": Param(int, required=False, default=1)},
)
def step(ctx, frames: int = 1):
    ctx.require("playback").step(frames)


@action(
    id="playback.go_to_start",
    title_key="transport.start",
    desc_key="Move the playhead to the beginning.",
    category="playback",
    shortcut="Home",
)
def go_to_start(ctx):
    ctx.require("playback").go_to_start()


@action(
    id="playback.go_to_end",
    title_key="transport.end",
    desc_key="Move the playhead to the end.",
    category="playback",
    shortcut="End",
)
def go_to_end(ctx):
    ctx.require("playback").go_to_end()
