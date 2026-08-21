"""Typed settings schema - the single source of truth for every stored key.

A key that is not declared here does not exist. Reading or writing an unknown
key raises, which turns a silent typo into an immediate, locatable error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Setting", "SETTINGS", "get_setting", "coerce"]


@dataclass(frozen=True)
class Setting:
    """Declaration of one persisted preference."""

    key: str
    default: Any
    kind: type
    choices: tuple[Any, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    doc: str = ""

    def validate(self, value: Any) -> Any:
        """Return a valid value, falling back to the default when unusable."""
        try:
            value = coerce(value, self.kind)
        except (TypeError, ValueError):
            return self.default
        if self.choices and value not in self.choices:
            return self.default
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if self.minimum is not None:
                value = max(self.minimum, value)
            if self.maximum is not None:
                value = min(self.maximum, value)
            value = self.kind(value)
        return value


def coerce(value: Any, kind: type) -> Any:
    """Convert a JSON-decoded value to the declared type."""
    if kind is bool:
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    if kind is int:
        return int(value)
    if kind is float:
        return float(value)
    if kind is str:
        return str(value)
    if kind is list:
        # A string reaches here from the generic settings.set action, whose
        # value param is str. list("10,20,800,600") would "succeed" as a
        # list of characters and get persisted; parse it as JSON instead,
        # and let a failure fall back to the default via validate().
        if isinstance(value, str):
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise ValueError(f"not a list: {value!r}")
            return parsed
        return list(value)
    if kind is dict:
        if isinstance(value, str):
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise ValueError(f"not an object: {value!r}")
            return parsed
        return dict(value)
    return value


def _s(*args: Any, **kwargs: Any) -> Setting:
    return Setting(*args, **kwargs)


#: Every persisted preference, grouped by area. Keys use ``area.name``.
SETTINGS: dict[str, Setting] = {
    s.key: s
    for s in (
        # ── application ────────────────────────────────────────────────
        _s("app.language", "system", str,
           doc="Locale code, or 'system' to follow the operating system."),
        _s("app.theme", "dark", str,
           doc="Theme id; must match a theme file in config/defaults/themes "
               "or user_data/themes."),
        _s("app.first_run", True, bool),

        # ── window ─────────────────────────────────────────────────────
        _s("window.fullscreen", True, bool,
           doc="Start in fullscreen. This is the intended default."),
        _s("window.screen", "", str, doc="Name of the screen used last."),
        _s("window.geometry", [], list, doc="[x, y, w, h] in windowed mode."),

        # ── shell layout (docs/UI_SHELL.md 8-ter) ──────────────────────
        _s("shell.rail_side", "left", str, choices=("left", "right"),
           doc="Tool rail side; the floating panel always takes the other."),
        _s("shell.transport_position", "bottom", str, choices=("center", "bottom"),
           doc="Playback controls: centre of the video, or above the timeline."),
        _s("shell.readout_corner", "top_left", str,
           choices=("top_left", "top_right", "bottom_left"),
           doc="Where the timecode and volume readout sits."),
        # 312 = video + audio + colour + sticker + text lanes, ruler and
        # toolbar: every lane on screen without scrolling.
        _s("shell.timeline_height", 312, int, minimum=140, maximum=520),
        _s("shell.panel_autohide", True, bool),
        _s("shell.panel_hide_delay_ms", 600, int, minimum=0, maximum=3000),
        _s("shell.panel_pinned", False, bool),
        _s("shell.ambient_backdrop", True, bool),

        # ── colour effects ─────────────────────────────────────────────
        _s("color.favorites", [], list,
           doc="Ids of the colour effects starred by the user, in the order "
               "they were starred."),
        _s("audio.favorites", [], list,
           doc="Ids of the audio effects starred by the user, in the order "
               "they were starred."),

        # ── stickers and transitions ────────────────────────────────────
        _s("sticker.favorites", [], list,
           doc="Ids of the stickers starred by the user, in the order they "
               "were starred."),
        _s("transition.favorites", [], list,
           doc="Ids of the transitions starred by the user, in the order "
               "they were starred."),

        # ── appearance / accessibility ─────────────────────────────────
        _s("appearance.glass", "auto", str, choices=("auto", "always", "never"),
           doc="Glass surfaces; 'auto' degrades on its own when unsupported "
               "or too slow."),
        _s("appearance.glass_opacity", 0.62, float, minimum=0.15, maximum=1.0,
           doc="Scrim strength of glass surfaces. Lower is more see-through. "
               "Below SAFE_SCRIM_TEXT the app warns: white text stops being "
               "guaranteed legible on a bright frame."),
        _s("appearance.glass_blur", 45, int, minimum=0, maximum=100,
           doc="Blur INTENSITY of glass surfaces, 0-100. A percentage, not a "
               "pixel radius: the radius is an implementation detail nobody "
               "should have to reason about, and a large one used to make the "
               "effect spill outside the panel."),
        _s("appearance.idle_background", True, bool,
           doc="Play the looping clip behind the empty state. Purely "
               "decorative; it stops as soon as a project is open."),
        _s("appearance.reduce_transparency", False, bool),
        _s("appearance.reduce_motion", False, bool),
        _s("appearance.ui_scale", 1.0, float, minimum=0.75, maximum=2.0),

        # ── proxies (docs/MEDIA_FORMATS.md 9) ──────────────────────────
        _s("media.proxy_enabled", True, bool,
           doc="Edit against small stand-in copies. The export always reads "
               "the originals, whatever this says."),
        _s("media.proxy_threshold", 1440, int, minimum=480, maximum=4320,
           doc="Above this height a proxy is built. 1080p decodes in ~6 ms "
               "here, 2160p in ~35 ms; the line sits between them."),
        _s("media.proxy_height", 540, int, minimum=270, maximum=1080,
           doc="Height of the proxy."),
        _s("project.canvas", "auto", str,
           choices=("auto", "16:9", "9:16", "4:3", "1:1", "21:9"),
           doc="Aspect ratio of the SEQUENCE. Every clip is letterboxed into "
               "it, so a clip shaped differently gets bars - which is correct: "
               "the canvas belongs to the project, not to whichever clip "
               "happens to be first. 'auto' takes the first clip's ratio, "
               "which is convenient but means the canvas changes under you "
               "when you reorder the timeline."),
        _s("media.preview_height", 720, int, minimum=360, maximum=2160,
           doc="Height the PREVIEW composites at. Proxies alone achieve "
               "nothing if every frame is then scaled back up to the sequence "
               "size: measured at 250 ms per frame to reach 2160p. The export "
               "always composites at full size."),

        # ── playback ───────────────────────────────────────────────────
        _s("playback.volume", 0.8, float, minimum=0.0, maximum=1.0),
        _s("playback.muted", False, bool),

        # ── logging ────────────────────────────────────────────────────
        _s("log.level", "INFO", str,
           choices=("DEBUG", "INFO", "WARNING", "ERROR")),
    )
}


def get_setting(key: str) -> Setting:
    """Look up a declared setting, raising a helpful error when missing."""
    try:
        return SETTINGS[key]
    except KeyError:
        raise KeyError(
            f"Unknown setting {key!r}. Declare it in ive/settings/schema.py "
            f"before using it."
        ) from None
