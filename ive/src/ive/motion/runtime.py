"""From a motion recipe to the per-frame evaluator the engine calls.

Pure Python, no Qt, no files: the engine's Overlays filter asks the
evaluator ``motion(local_seconds, clip_seconds)`` and gets back the
frame's ``{dx, dy, scale, rotation, opacity}`` - offsets and
multipliers RELATIVE to the clip's own transform, so a preset composes
with wherever the user put the sticker.

Anchoring is decided by the recipe's kind:

* ``loop``  - the recipe repeats with its duration as the period, for
  the whole clip;
* ``in``    - it plays ONCE over the clip's first `duration` seconds,
  then holds its final frame (identity, by convention of the recipes);
* ``out``   - it holds identity until the clip's last `duration`
  seconds, then plays once, ending ON the clip's end.

Easing is a closed, documented set; an unknown name falls back to
linear with a warning, an unknown parameter is skipped - a recipe
written by a newer version must degrade, never break.
"""

from __future__ import annotations

import logging
import math

log = logging.getLogger(__name__)

__all__ = ["make_motion", "attach_motion", "IDENTITY"]

IDENTITY = {"dx": 0.0, "dy": 0.0, "scale": 1.0, "rotation": 0.0,
            "opacity": 1.0}

#: What each parameter modulates, and its resting value.
_PARAMETERS = {"x": ("dx", 0.0), "y": ("dy", 0.0), "scale": ("scale", 1.0),
               "rotation": ("rotation", 0.0), "opacity": ("opacity", 1.0)}


def _ease(name: str, t: float) -> float:
    if name == "linear" or not name:
        return t
    if name == "in_quad":
        return t * t
    if name == "out_quad":
        return 1.0 - (1.0 - t) * (1.0 - t)
    if name == "in_out_quad":
        return 2 * t * t if t < 0.5 else 1.0 - 2 * (1.0 - t) * (1.0 - t)
    if name == "in_cubic":
        return t ** 3
    if name == "out_cubic":
        return 1.0 - (1.0 - t) ** 3
    if name == "in_out_cubic":
        return 4 * t ** 3 if t < 0.5 else 1.0 - 4 * (1.0 - t) ** 3
    if name == "out_back":
        c1, c3 = 1.70158, 2.70158
        u = t - 1.0
        return 1.0 + c3 * u ** 3 + c1 * u * u
    if name == "out_bounce":
        n1, d1 = 7.5625, 2.75
        if t < 1 / d1:
            return n1 * t * t
        if t < 2 / d1:
            u = t - 1.5 / d1
            return n1 * u * u + 0.75
        if t < 2.5 / d1:
            u = t - 2.25 / d1
            return n1 * u * u + 0.9375
        u = t - 2.625 / d1
        return n1 * u * u + 0.984375
    if name == "out_elastic":
        if t <= 0.0 or t >= 1.0:
            return max(0.0, min(1.0, t))
        return (math.pow(2.0, -10.0 * t)
                * math.sin((t * 10.0 - 0.75) * (2.0 * math.pi / 3.0)) + 1.0)
    log.warning("Unknown easing %r; using linear", name)
    return t


def _track_value(keyframes: list[dict], t: float, resting: float) -> float:
    """The track's value at normalised time ``t``.

    The easing declared ON a keyframe shapes the segment LEAVING it.
    Before the first keyframe the first value holds; after the last,
    the last one does.
    """
    frames = sorted(
        ({"t": max(0.0, min(1.0, float(k.get("t", 0.0)))),
          "value": float(k.get("value", resting)),
          "easing": str(k.get("easing") or "linear")}
         for k in keyframes if isinstance(k, dict)),
        key=lambda k: k["t"])
    if not frames:
        return resting
    if t <= frames[0]["t"]:
        return frames[0]["value"]
    for left, right in zip(frames, frames[1:]):
        if t <= right["t"]:
            span = right["t"] - left["t"]
            local = 0.0 if span <= 0 else (t - left["t"]) / span
            shaped = _ease(left["easing"], local)
            return left["value"] + (right["value"] - left["value"]) * shaped
    return frames[-1]["value"]


def make_motion(recipe: dict):
    """``motion(local_seconds, clip_seconds) -> {dx, dy, scale, rotation,
    opacity}`` from a recipe, or None when the recipe is unusable."""
    if not isinstance(recipe, dict):
        return None
    kind = str(recipe.get("kind") or "loop")
    duration = min(10.0, max(0.1, float(recipe.get("duration") or 0.8)))
    tracks = []
    for track in recipe.get("tracks") or []:
        parameter = str(track.get("parameter") or "")
        if parameter not in _PARAMETERS:
            log.warning("Unknown motion parameter %r skipped", parameter)
            continue
        key, resting = _PARAMETERS[parameter]
        keyframes = track.get("keyframes")
        if isinstance(keyframes, list) and keyframes:
            tracks.append((key, resting, keyframes))
    if not tracks:
        return None

    def motion(local_seconds: float, clip_seconds: float) -> dict:
        if kind == "loop":
            t = (local_seconds % duration) / duration
        elif kind == "in":
            if local_seconds >= duration:
                return IDENTITY
            t = local_seconds / duration
        else:                                            # "out"
            start = max(0.0, clip_seconds - duration)
            if local_seconds < start:
                return IDENTITY
            span = max(1e-6, min(duration, clip_seconds))
            t = min(1.0, (local_seconds - start) / span)
        values = dict(IDENTITY)
        for key, resting, keyframes in tracks:
            values[key] = _track_value(keyframes, t, resting)
        return values

    return motion


def attach_motion(spans: list[dict]) -> None:
    """Give each span with a ``motion_recipe`` its ``motion`` callable,
    IN PLACE - same division of labour as the sprites: recipes are pure
    data across thread boundaries, evaluators attach on either side."""
    for span in spans or []:
        recipe = span.get("motion_recipe")
        if recipe:
            motion = make_motion(recipe)
            if motion is not None:
                span["motion"] = motion
