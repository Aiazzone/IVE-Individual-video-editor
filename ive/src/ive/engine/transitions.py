"""Transition blenders: how two pictures become one while a cut plays.

Pure numpy (cv2 used when present, never required), no Qt, no files:
the LUMA MAPS arrive as arrays, loaded elsewhere (ive/transitions/
loader.py) - the same division of labour the stickers use.

One primitive carries most of the catalogue: the **luma map**, a
greyscale image where each pixel's value says WHEN that pixel switches
from the outgoing clip to the incoming one (0 = first, 1 = last), with
a softness band around the moving edge. A left wipe is a horizontal
gradient, a circle is a radial one, and a hand-drawn PNG is a brand-new
transition nobody had to program. Parametric wipes are just gradients
generated here, so they share the exact same code path.

Performance notes (measured in tests/test_transitions.py):

* the luma weight for a frame depends ONLY on the map value, so it is
  a 256-entry LUT built per frame and gathered per pixel - no per-pixel
  arithmetic on floats;
* blends run in uint16 integer math with 0..256 weights (255*256 fits
  uint16), like the vignette in filters.py;
* maps are resized to the canvas ONCE and cached per size;
* pushes and slides are pure array slicing - memcpy, no resampling;
* outside a transition window the cost is zero (the tractor never
  calls a blender).
"""

from __future__ import annotations

import logging
from bisect import bisect_right

import numpy as np

try:
    import cv2
except ImportError:                                   # pragma: no cover
    cv2 = None

log = logging.getLogger(__name__)

__all__ = ["Blender", "Mix", "Luma", "Push", "Zoom", "ThroughColor",
           "TimedBlend", "make_blender", "ease", "gradient_map"]


def ease(t: float, curve: str) -> float:
    """Progress curves. ``smooth`` is the default of the catalogue."""
    t = min(1.0, max(0.0, float(t)))
    if curve == "smooth":
        return t * t * (3.0 - 2.0 * t)
    if curve == "ease_in":
        return t * t
    if curve == "ease_out":
        return 1.0 - (1.0 - t) * (1.0 - t)
    return t


def _blend_scalar(base: np.ndarray, top: np.ndarray, w: float) -> np.ndarray:
    """base*(1-w) + top*w with a scalar weight, integer math."""
    if w <= 0.0:
        return base
    if w >= 1.0:
        return top
    if cv2 is not None:
        return cv2.addWeighted(base, 1.0 - w, top, w, 0.0)
    iw = int(round(w * 256.0))
    return ((base.astype(np.uint16) * (256 - iw)
             + top.astype(np.uint16) * iw) >> 8).astype(np.uint8)


class Blender:
    """Combines two same-shaped uint8 pictures at progress ``t`` [0, 1]."""

    def blend(self, base: np.ndarray, top: np.ndarray,
              t: float) -> np.ndarray:
        raise NotImplementedError


class Mix(Blender):
    """Plain crossfade."""

    def blend(self, base, top, t):
        return _blend_scalar(base, top, t)


class Luma(Blender):
    """The workhorse: a greyscale map decides when each pixel switches.

    ``softness`` widens the moving edge (0 = hard cut per pixel). The
    map can be any size; it is resized to each canvas once and cached.
    """

    def __init__(self, map_u8: np.ndarray, softness: float = 0.1) -> None:
        map_u8 = np.asarray(map_u8)
        if map_u8.ndim == 3:
            map_u8 = map_u8[..., 0]
        self._map = map_u8.astype(np.uint8, copy=False)
        self.softness = max(0.005, min(1.0, float(softness)))
        self._sized: dict[tuple[int, int], np.ndarray] = {}

    def _map_for(self, height: int, width: int) -> np.ndarray:
        key = (height, width)
        sized = self._sized.get(key)
        if sized is None:
            mh, mw = self._map.shape[:2]
            if (mh, mw) == key:
                sized = self._map
            elif cv2 is not None:
                sized = cv2.resize(self._map, (width, height),
                                   interpolation=cv2.INTER_LINEAR)
            else:
                ys = (np.arange(height) * mh // height).clip(0, mh - 1)
                xs = (np.arange(width) * mw // width).clip(0, mw - 1)
                sized = self._map[ys][:, xs]
            self._sized[key] = sized
        return sized

    def blend(self, base, top, t):
        if t <= 0.0:
            return base
        if t >= 1.0:
            return top
        height, width = base.shape[:2]
        gate = self._map_for(height, width)
        s = self.softness
        # Weight depends ONLY on the map value: one 256-entry LUT per
        # frame, one gather per pixel. t*(1+s) sweeps past 1 so even the
        # brightest pixel finishes fully inside the window.
        values = np.arange(256, dtype=np.float32) / 255.0
        lut = np.clip((t * (1.0 + s) - values) / s, 0.0, 1.0)
        if cv2 is not None:
            # SIMD gather + SIMD blend: measured 104 -> ~3 ms per 720p
            # frame against the pure-numpy expression this replaces
            # (whose uint16 broadcast temporaries were the whole cost).
            weights = cv2.LUT(gate, lut.astype(np.float32))
            return cv2.blendLinear(base, top, 1.0 - weights, weights)
        # Fallback: gather uint8 weights, blend via the delta trick -
        # one widening multiply instead of two, no HxWx3 uint16 pair.
        w = (lut * 255.0).astype(np.uint8)[gate][..., None].astype(np.int32)
        delta = top.astype(np.int32) - base.astype(np.int32)
        return (base + (delta * w) // 255).astype(np.uint8)


def gradient_map(direction: str, size: tuple[int, int] = (288, 512)
                 ) -> np.ndarray:
    """Parametric wipes as generated luma maps - one code path for all."""
    height, width = size
    xs = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    ys = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    if direction == "left":            # the new picture enters from the left
        field = np.broadcast_to(xs, (height, width))
    elif direction == "right":
        field = np.broadcast_to(1.0 - xs, (height, width))
    elif direction == "up":
        field = np.broadcast_to(1.0 - ys, (height, width))
    elif direction == "down":
        field = np.broadcast_to(ys, (height, width))
    elif direction == "circle_in":     # a growing disc reveals the new clip
        field = np.hypot((xs - 0.5) * 2.0, (ys - 0.5) * 2.0) / 1.4142
    elif direction == "circle_out":    # a shrinking disc hides the old one
        field = 1.0 - np.hypot((xs - 0.5) * 2.0, (ys - 0.5) * 2.0) / 1.4142
    else:
        log.warning("Unknown wipe direction %r; using left", direction)
        field = np.broadcast_to(xs, (height, width))
    return (np.clip(field, 0.0, 1.0) * 255.0).astype(np.uint8)


class Push(Blender):
    """The incoming picture pushes the old one out, or slides over it.

    Pure slicing: two block copies per frame, no resampling at all.
    """

    def __init__(self, direction: str = "left", slide: bool = False) -> None:
        self.direction = direction
        self.slide = bool(slide)

    def blend(self, base, top, t):
        height, width = base.shape[:2]
        out = np.empty_like(base) if not self.slide else base.copy()
        if self.direction in ("left", "right"):
            o = int(round(t * width))
            if o <= 0:
                return base
            if o >= width:
                return top
            if self.direction == "left":     # new enters from the right edge
                if not self.slide:
                    out[:, :width - o] = base[:, o:]
                out[:, width - o:] = top[:, :o]
            else:                            # new enters from the left edge
                if not self.slide:
                    out[:, o:] = base[:, :width - o]
                out[:, :o] = top[:, width - o:]
            return out
        o = int(round(t * height))
        if o <= 0:
            return base
        if o >= height:
            return top
        if self.direction == "up":           # new enters from the bottom
            if not self.slide:
                out[:height - o] = base[o:]
            out[height - o:] = top[:o]
        else:                                # new enters from the top
            if not self.slide:
                out[o:] = base[:height - o]
            out[:o] = top[height - o:]
        return out


class Zoom(Blender):
    """The old picture zooms in while the new one fades through it."""

    #: How far the outgoing picture has zoomed by the end of the window.
    FACTOR = 1.6

    def blend(self, base, top, t):
        if t <= 0.0:
            return base
        if t >= 1.0:
            return top
        height, width = base.shape[:2]
        zoom = 1.0 + (self.FACTOR - 1.0) * t
        crop_h = max(2, int(round(height / zoom)))
        crop_w = max(2, int(round(width / zoom)))
        y0 = (height - crop_h) // 2
        x0 = (width - crop_w) // 2
        crop = base[y0:y0 + crop_h, x0:x0 + crop_w]
        if cv2 is not None:
            zoomed = cv2.resize(crop, (width, height),
                                interpolation=cv2.INTER_LINEAR)
        else:
            ys = (np.arange(height) * crop_h // height).clip(0, crop_h - 1)
            xs = (np.arange(width) * crop_w // width).clip(0, crop_w - 1)
            zoomed = crop[ys][:, xs]
        return _blend_scalar(zoomed, top, t)


class ThroughColor(Blender):
    """Out through a solid colour, in from it - the classic dip."""

    def __init__(self, rgb: tuple[int, int, int] = (0, 0, 0)) -> None:
        self._rgb = tuple(int(v) for v in rgb[:3])
        self._plate: np.ndarray | None = None

    def _plate_for(self, shape) -> np.ndarray:
        if self._plate is None or self._plate.shape != shape:
            self._plate = np.empty(shape, dtype=np.uint8)
            self._plate[...] = np.array(self._rgb, dtype=np.uint8)
        return self._plate

    def blend(self, base, top, t):
        plate = self._plate_for(base.shape)
        if t < 0.5:
            return _blend_scalar(base, plate, t * 2.0)
        return _blend_scalar(plate, top, t * 2.0 - 1.0)


def make_blender(payload: dict) -> Blender | None:
    """A blender from a recipe's ``op`` payload. Unknown kinds -> None.

    ``luma`` expects the map ALREADY LOADED as an array under "map"
    (ive/transitions/loader.py does that - the engine reads no files).
    """
    kind = str(payload.get("kind") or "")
    if kind == "mix":
        return Mix()
    if kind == "luma":
        map_u8 = payload.get("map")
        if map_u8 is None:
            log.warning("Luma transition without a loaded map skipped")
            return None
        return Luma(map_u8, float(payload.get("softness", 0.1)))
    if kind == "wipe":
        return Luma(gradient_map(str(payload.get("direction") or "left")),
                    float(payload.get("softness", 0.1)))
    if kind in ("push", "slide"):
        return Push(str(payload.get("direction") or "left"),
                    slide=(kind == "slide"))
    if kind == "zoom":
        return Zoom()
    if kind == "through_color":
        value = str(payload.get("color") or "#000000").lstrip("#")
        try:
            rgb = tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            rgb = (0, 0, 0)
        return ThroughColor(rgb)
    log.warning("Unknown transition kind %r skipped", kind)
    return None


class TimedBlend:
    """What sits on the B-roll track: windows in SEQUENCE frames.

    Inside a window the two tracks blend at the window's progress;
    outside, the top track simply covers (its clip is alone there).
    ``windows`` is ``[(start_f, end_f, blender, easing, flipped), ...]``
    sorted. ``flipped`` marks the windows where the OUTGOING clip sits
    on the UPPER track (the A/B alternation flips roles at every other
    junction): the pictures swap before the blend, because a push is
    not symmetric - reversing arguments is not the same as 1-t.
    """

    def __init__(self, windows: list[tuple]) -> None:
        self._windows = sorted(windows, key=lambda w: w[0])
        self._starts = [w[0] for w in self._windows]

    def blend_at(self, position: int, base: np.ndarray,
                 top: np.ndarray) -> np.ndarray:
        index = bisect_right(self._starts, position) - 1
        if index >= 0:
            start, end, blender, easing, flipped = self._windows[index]
            if start <= position < end:
                # First frame 0, last frame 1: the window ends ON the
                # incoming picture, never one frame short of it.
                span = max(1, end - start - 1)
                t = ease((position - start) / span, easing)
                if flipped:
                    base, top = top, base
                return blender.blend(base, top, t)
        return top
