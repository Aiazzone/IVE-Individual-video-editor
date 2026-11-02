"""Background removal on one A/V clip: the subject over a new backdrop.

The clip's own picture is cut along the subject mask (the same injected
provider the masked colour ops use - see ``filters.set_mask_provider``)
and laid over a solid colour or a still image. It runs on the CLIP, in
the entry's filter chain BEFORE the Placement filter, so the new
backdrop moves, scales and fades with the clip like the picture it
replaces did.

``span`` is the clip dict itself, read at process time (the Placement
contract): ``span["cutout"]`` holds

    mode      "color" | "image" | "transparent"
                                     ("" / absent = the filter is idle)
    color     "#RRGGBB"              the backdrop for "color"
    image     absolute path          the backdrop for "image" (cover-fit)
                                     "transparent": NO backdrop - the frame
                                     carries the subject's coverage as its
                                     alpha (an alpha export keeps it; the
                                     preview shows black behind, like any
                                     hole in the sequence)
    feather   0..1                   how soft the edge is
    shrink    0..1                   how far the edge is pulled IN -
                                     U2-Net's mask tends to bleed a rim
                                     of the old scene around hair

**Flicker.** A per-frame mask jitters: the edge breathes from one frame
to the next even on a still subject. Consecutive frames therefore blend
the new mask with the previous one (``STABILITY``): a cheap temporal
low-pass that calms the edge and costs a frame of lag on fast motion,
reset on any jump (a seek, a pull out of order).

Without a mask (model not installed, no provider) the clip plays
UNTOUCHED - the same degrade-to-pass-through contract every masked op
has - rather than over an empty backdrop.
"""

from __future__ import annotations

import logging
import os
import threading

import numpy as np

from ive.engine.filters import Filter, _hex_rgb, _subject_mask
from ive.engine.frame import Frame

log = logging.getLogger(__name__)

__all__ = ["Cutout", "MODES", "STABILITY"]

MODES = ("color", "image", "transparent")

#: Weight of the PREVIOUS frame's mask in the temporal blend.
STABILITY = 0.4


class Cutout(Filter):
    """Replace the clip's background with a colour or an image."""

    def __init__(self, span: dict) -> None:
        self._span = span
        self._lock = threading.Lock()
        #: (position, float mask) of the last frame cut, for the blend.
        self._last: tuple[int, np.ndarray] | None = None
        #: (path, mtime, w, h) -> the cover-fitted backdrop.
        self._images: dict[tuple, np.ndarray] = {}

    def process(self, frame: Frame) -> Frame:
        settings = self._span.get("cutout") or {}
        if settings.get("mode") not in MODES:
            return frame
        position = frame.position

        if settings.get("mode") == "transparent":
            def both():
                image = frame.image()
                if image is None:
                    return None, None
                return self.apply_alpha(image, position)

            image_fn, alpha_fn = self._joint(both)
            return self._wrap(frame, image_fn=image_fn, alpha_fn=alpha_fn)

        def cut():
            image = frame.image()
            if image is None:
                return None
            return self.apply(image, position)

        return self._wrap(frame, image_fn=cut)

    # ── the work ──────────────────────────────────────────────────────

    def apply(self, image: np.ndarray, position: int = -1) -> np.ndarray:
        """The cut-out picture at ``position`` (-1 = no temporal blend)."""
        settings = dict(self._span.get("cutout") or {})
        if image.ndim != 3 or image.shape[2] < 3:
            return image
        rgb = image[..., :3]
        mask = _subject_mask(np.ascontiguousarray(rgb))
        if mask is None:
            return image
        h, w = rgb.shape[:2]
        alpha = self._alpha(mask, settings, position, w, h)
        backdrop = self._backdrop(settings, w, h)
        out = (rgb.astype(np.float32) * alpha
               + backdrop.astype(np.float32) * (1.0 - alpha))
        return np.clip(out + 0.5, 0, 255).astype(np.uint8)

    def apply_alpha(self, image: np.ndarray, position: int = -1
                    ) -> tuple[np.ndarray, np.ndarray | None]:
        """(subject over black, its coverage) - the "transparent" mode.

        The picture is premultiplied, the engine's convention: what a
        viewer sees over black. Without a mask: the clip untouched and
        opaque (None).
        """
        settings = dict(self._span.get("cutout") or {})
        if image.ndim != 3 or image.shape[2] < 3:
            return image, None
        rgb = image[..., :3]
        mask = _subject_mask(np.ascontiguousarray(rgb))
        if mask is None:
            return image, None
        h, w = rgb.shape[:2]
        alpha = self._alpha(mask, settings, position, w, h)
        out = np.clip(rgb.astype(np.float32) * alpha + 0.5, 0, 255
                      ).astype(np.uint8)
        return out, np.clip(alpha[..., 0] * 255.0 + 0.5, 0, 255
                            ).astype(np.uint8)

    def _alpha(self, mask: np.ndarray, settings: dict, position: int,
               w: int, h: int) -> np.ndarray:
        """The refined soft mask, float32 0..1, shape (h, w, 1)."""
        try:
            import cv2
        except ImportError:
            cv2 = None
        if mask.shape[:2] != (h, w):
            if cv2 is None:
                ys = (np.arange(h) * mask.shape[0] // h)
                xs = (np.arange(w) * mask.shape[1] // w)
                mask = mask[ys][:, xs]
            else:
                mask = cv2.resize(mask, (w, h),
                                  interpolation=cv2.INTER_LINEAR)
        current = mask.astype(np.float32) / 255.0

        with self._lock:
            last = self._last
            if (position >= 0 and last is not None
                    and last[0] == position - 1
                    and last[1].shape == current.shape):
                current = (current * (1.0 - STABILITY)
                           + last[1] * STABILITY)
            if position >= 0:
                self._last = (position, current)

        shrink = _unit(settings.get("shrink"), 0.1)
        feather = _unit(settings.get("feather"), 0.3)
        if cv2 is not None:
            radius = int(round(shrink * 0.02 * h))
            if radius > 0:
                kernel = cv2.getStructuringElement(
                    cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1))
                current = cv2.erode(current, kernel)
            sigma = 0.4 + feather * 0.008 * h
            current = cv2.GaussianBlur(current, (0, 0), sigma)
        return np.clip(current, 0.0, 1.0)[..., None]

    def _backdrop(self, settings: dict, w: int, h: int) -> np.ndarray:
        if settings.get("mode") == "image":
            picture = self._image(str(settings.get("image") or ""), w, h)
            if picture is not None:
                return picture
        colour = _hex_rgb(settings.get("color"), fallback=(0, 177, 64))
        return np.broadcast_to(colour.astype(np.uint8), (h, w, 3))

    def _image(self, path: str, w: int, h: int) -> np.ndarray | None:
        """The still, cover-fitted to ``w`` x ``h`` and cached."""
        if not path:
            return None
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            log.warning("Background image missing: %s", path)
            return None
        key = (path, mtime, w, h)
        cached = self._images.get(key)
        if cached is not None:
            return cached
        try:
            import cv2

            # imdecode, not imread: imread cannot open a non-ASCII path
            # on Windows.
            raw = np.fromfile(path, dtype=np.uint8)
            picture = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if picture is None:
                raise ValueError("unreadable image")
            picture = cv2.cvtColor(picture, cv2.COLOR_BGR2RGB)
            ih, iw = picture.shape[:2]
            scale = max(w / iw, h / ih)
            sw = max(w, int(round(iw * scale)))
            sh = max(h, int(round(ih * scale)))
            picture = cv2.resize(picture, (sw, sh),
                                 interpolation=cv2.INTER_AREA
                                 if scale < 1 else cv2.INTER_LINEAR)
            x0, y0 = (sw - w) // 2, (sh - h) // 2
            picture = np.ascontiguousarray(picture[y0:y0 + h, x0:x0 + w])
        except Exception:
            log.exception("Could not load the background image %s", path)
            return None
        if len(self._images) > 4:
            self._images.clear()
        self._images[key] = picture
        return picture


def _unit(value, default: float) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return default
