"""Tractor: pulls every track at the same position and returns one frame.

The name comes from MLT and describes what it does: it drags all the tracks
along together. It composites video bottom-up and sums audio, and - being a
producer itself - a whole sequence can be dropped into another timeline with
no new concepts.
"""

from __future__ import annotations

import logging

import numpy as np

from ive.engine.frame import AudioFormat, Frame, Timebase
from ive.engine.producer import Producer

log = logging.getLogger(__name__)

__all__ = ["Track", "Tractor"]


class Track:
    """One track in the stack: a producer plus how it takes part."""

    def __init__(self, producer: Producer, *, video: bool = True,
                 audio: bool = True, hidden: bool = False, muted: bool = False,
                 opacity: float = 1.0, gain: float = 1.0,
                 transition=None, name: str = "") -> None:
        self.producer = producer
        self.video = video
        self.audio = audio
        self.hidden = hidden
        self.muted = muted
        self.opacity = opacity
        self.gain = gain
        #: How this track combines with everything below it. None = over.
        self.transition = transition
        self.name = name or getattr(producer, "name", "")


class Tractor(Producer):
    """The root of a sequence."""

    def __init__(self, timebase: Timebase | None = None,
                 audio_format: AudioFormat | None = None,
                 width: int = 1920, height: int = 1080,
                 name: str = "sequence") -> None:
        self.timebase = timebase or Timebase()
        self.audio_format = audio_format or AudioFormat()
        self.width = width
        self.height = height
        self.name = name
        self.tracks: list[Track] = []
        #: How a picture with a different ratio meets the canvas:
        #: "fit" letterboxes (never crops, never stretches), "fill"
        #: crops the overflow, "blur" letterboxes over a blurred fill
        #: of the same picture instead of black bars.
        self.fit_mode = "fit"
        #: Index maps for letterboxing, keyed by source size.
        self._fit_cache: dict[tuple[int, int], dict] = {}
        #: Filters over the finished composite - grades, watermarks.
        self.filters: list = []
        self.length = 0
        #: An alpha export: compose the coverage alongside the picture.
        #: Off for the preview, which never looks at it.
        self.with_alpha = False

    # ── building ──────────────────────────────────────────────────────

    def resize(self, width: int, height: int) -> None:
        """Change the canvas size; the scaling plans no longer apply."""
        self.width, self.height = int(width), int(height)
        self._fit_cache.clear()

    def set_fit_mode(self, mode: str) -> None:
        """Choose fit / fill / blur; an unknown name stays at "fit"."""
        self.fit_mode = mode if mode in ("fit", "fill", "blur") else "fit"

    def add_track(self, track: Track) -> Track:
        """Add a track. The first added is the bottom of the stack."""
        self.tracks.append(track)
        self.length = max((t.producer.length for t in self.tracks), default=0)
        return track

    def clear(self) -> None:
        self.tracks.clear()
        self.length = 0

    # ── producing ─────────────────────────────────────────────────────

    def frame_at(self, position: int) -> Frame | None:
        if self.length and not (0 <= position < self.length):
            return None

        result = Frame(position, self.timebase, self.audio_format)
        composite: np.ndarray | None = None
        coverage: np.ndarray | None = None
        mixed: np.ndarray | None = None
        contributed = False
        with_alpha = self.with_alpha

        for track in self.tracks:
            if track.hidden and track.muted:
                continue
            source = track.producer.frame_at(position)
            if source is None:
                continue

            # ── video, bottom-up ──────────────────────────────────────
            if track.video and not track.hidden:
                image = source.image()
                if image is not None:
                    alpha = None
                    if with_alpha:
                        alpha = self._fit_alpha(image, source.alpha())
                    image = self._fit(image)
                    if composite is None:
                        composite = image.copy()
                        coverage = alpha
                    elif track.transition is not None:
                        # A timed blend (engine/transitions.TimedBlend)
                        # needs the position: transitions live in windows.
                        # The legacy contract stays for whole-track blends.
                        if hasattr(track.transition, "blend_at"):
                            composite_in = composite
                            composite = track.transition.blend_at(
                                position, composite, image)
                            if with_alpha:
                                coverage = _blend_alpha(
                                    lambda a, b: track.transition.blend_at(
                                        position, a, b),
                                    coverage, alpha, composite_in.shape)
                        else:
                            composite = track.transition.blend(
                                composite, image, track.opacity)
                            if with_alpha:
                                coverage = _blend_alpha(
                                    lambda a, b: track.transition.blend(
                                        a, b, track.opacity),
                                    coverage, alpha, image.shape)
                    else:
                        composite = _over(composite, image, track.opacity)
                        if with_alpha:
                            coverage = _blend_alpha(
                                lambda a, b: _over(a, b, track.opacity),
                                coverage, alpha, image.shape)
                    contributed = True

            # ── audio, summed ─────────────────────────────────────────
            if track.audio and not track.muted:
                audio = source.audio()
                if audio is not None and len(audio):
                    scaled = audio * track.gain if track.gain != 1.0 else audio
                    if mixed is None:
                        mixed = scaled.astype(np.float32, copy=True)
                    else:
                        length = min(len(mixed), len(scaled))
                        mixed[:length] += scaled[:length]

        if composite is not None:
            result.set_image(composite)
            if with_alpha:
                result.set_alpha(coverage)
        elif contributed:
            result.set_image(None)

        if mixed is not None:
            # Summing tracks can exceed full scale. Clipping here is the honest
            # cheap answer; a limiter belongs in the audio filters, not in the
            # mixer, where it would be impossible to switch off.
            np.clip(mixed, -1.0, 1.0, out=mixed)
            result.set_audio(mixed)
        else:
            result.set_audio(result.silence())

        for filt in self.filters:
            result = filt.process(result)
        return result

    # ── helpers ───────────────────────────────────────────────────────

    def _fit(self, image: np.ndarray) -> np.ndarray:
        """Bring a track's picture onto the sequence frame.

        "fit" letterboxes and never crops or stretches - the honest
        default. "fill" crops the overflow (the user chose it, so the
        reframe is not silent). "blur" letterboxes the sharp picture
        over a blurred fill of ITSELF, the way vertical phone clips are
        published on 16:9 - no black bars, nothing invented.

        The index maps are cached per source size (and rebuilt when the
        mode changes). Rebuilding them each frame was measured at 250 ms
        for a 4K canvas - enough on its own to make a proxy slower than
        the original it was meant to replace.
        """
        height, width = image.shape[:2]
        if (width, height) == (self.width, self.height):
            return image

        key = (width, height)
        plans = self._fit_cache.get(key)
        if plans is None:
            plans = {}
            self._fit_cache[key] = plans
        mode = self.fit_mode
        need_fill = mode in ("fill", "blur")
        if "fit" not in plans:
            scale = min(self.width / width, self.height / height)
            new_w = max(1, int(round(width * scale)))
            new_h = max(1, int(round(height * scale)))
            ys = (np.arange(new_h) * height // new_h).clip(0, height - 1)
            xs = (np.arange(new_w) * width // new_w).clip(0, width - 1)
            top = (self.height - new_h) // 2
            left = (self.width - new_w) // 2
            plans["fit"] = (ys, xs, top, left, new_h, new_w)
        if need_fill and "fill" not in plans:
            # Output pixel -> source pixel, crop centred: the whole
            # canvas is covered, the overflow never leaves the source.
            scale = max(self.width / width, self.height / height)
            span_w = max(1, int(round(width * scale)))
            span_h = max(1, int(round(height * scale)))
            xs = (((np.arange(self.width) + (span_w - self.width) // 2)
                   * width) // span_w).clip(0, width - 1)
            ys = (((np.arange(self.height) + (span_h - self.height) // 2)
                   * height) // span_h).clip(0, height - 1)
            plans["fill"] = (ys, xs)

        if mode == "fill":
            ys, xs = plans["fill"]
            return np.ascontiguousarray(image[ys][:, xs])

        ys, xs, top, left, new_h, new_w = plans["fit"]
        if mode == "blur":
            fill_ys, fill_xs = plans["fill"]
            canvas = self._blurred(image[fill_ys][:, fill_xs])
        else:
            canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        if (height, width) == (new_h, new_w):
            # Already the right size, because the producer asked its decoder
            # for it and FFmpeg did the scaling. Only the letterbox placement
            # is left - a copy, not a gather. Falling through to the index maps
            # below would rebuild the picture pixel by pixel for nothing.
            canvas[top:top + new_h, left:left + new_w] = image
            return canvas
        canvas[top:top + new_h, left:left + new_w] = image[ys][:, xs]
        return canvas

    def _fit_alpha(self, image: np.ndarray,
                   alpha: np.ndarray | None) -> np.ndarray | None:
        """The coverage of ``image`` once ``_fit`` has placed it: the
        same index maps; letterbox bars are see-through under "fit",
        picture under "blur" (the blurred fill), absent under "fill"."""
        height, width = image.shape[:2]
        if (width, height) == (self.width, self.height):
            return alpha
        if alpha is None and self.fit_mode in ("fill", "blur"):
            return None
        source = (alpha if alpha is not None
                  else np.full((height, width), 255, np.uint8))
        # Reuse _fit's cached plans: run it on the coverage as a picture.
        rgb = np.repeat(source[..., None], 3, axis=2)
        mode = self.fit_mode
        if mode == "blur":
            self.fit_mode = "fit"
            try:
                fitted = self._fit(rgb)[..., 0]
            finally:
                self.fit_mode = mode
            ys, xs, top, left, new_h, new_w = self._fit_cache[
                (width, height)]["fit"]
            out = np.full((self.height, self.width), 255, np.uint8)
            out[top:top + new_h, left:left + new_w] = \
                fitted[top:top + new_h, left:left + new_w]
            return out
        return np.ascontiguousarray(self._fit(rgb)[..., 0])

    def _blurred(self, filled: np.ndarray) -> np.ndarray:
        """A heavy, cheap blur: shrink hard, then stretch back.

        Two linear resizes cost a fraction of a Gaussian at canvas size
        and the result is indistinguishable behind the sharp foreground.
        A little darkening keeps the letterboxed picture readable on a
        bright background.
        """
        import cv2

        small = cv2.resize(filled, (max(2, self.width // 24),
                                    max(2, self.height // 24)),
                           interpolation=cv2.INTER_AREA)
        background = cv2.resize(small, (self.width, self.height),
                                interpolation=cv2.INTER_LINEAR)
        return (background.astype(np.uint16) * 3 // 4).astype(np.uint8)

    def close(self) -> None:
        for track in self.tracks:
            track.producer.close()


def _blend_alpha(blend, base: np.ndarray | None, top: np.ndarray | None,
                 shape) -> np.ndarray | None:
    """Run a picture blend on the two coverages (as grey pictures), so a
    wipe or a dissolve reveals the alpha exactly as it reveals the
    image. None (opaque) on both sides stays None."""
    if base is None and top is None:
        return None
    h, w = shape[:2]
    full = np.full((h, w), 255, np.uint8)
    a = np.repeat((full if base is None else base)[..., None], 3, axis=2)
    b = np.repeat((full if top is None else top)[..., None], 3, axis=2)
    return np.ascontiguousarray(blend(a, b)[..., 0])


def _over(base: np.ndarray, top: np.ndarray, opacity: float) -> np.ndarray:
    """Standard "over": ``top`` on ``base`` at ``opacity``."""
    if opacity >= 1.0:
        return top
    if opacity <= 0.0:
        return base
    return (base.astype(np.float32) * (1.0 - opacity)
            + top.astype(np.float32) * opacity).astype(np.uint8)
