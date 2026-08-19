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
        #: Index maps for letterboxing, keyed by source size.
        self._fit_cache: dict[tuple[int, int], tuple] = {}
        #: Filters over the finished composite - grades, watermarks.
        self.filters: list = []
        self.length = 0

    # ── building ──────────────────────────────────────────────────────

    def resize(self, width: int, height: int) -> None:
        """Change the canvas size; the scaling plans no longer apply."""
        self.width, self.height = int(width), int(height)
        self._fit_cache.clear()

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
        mixed: np.ndarray | None = None
        contributed = False

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
                    image = self._fit(image)
                    if composite is None:
                        composite = image.copy()
                    elif track.transition is not None:
                        # A timed blend (engine/transitions.TimedBlend)
                        # needs the position: transitions live in windows.
                        # The legacy contract stays for whole-track blends.
                        if hasattr(track.transition, "blend_at"):
                            composite = track.transition.blend_at(
                                position, composite, image)
                        else:
                            composite = track.transition.blend(
                                composite, image, track.opacity)
                    else:
                        composite = _over(composite, image, track.opacity)
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
        """Letterbox a track's picture into the sequence frame.

        Never crops and never stretches: an editor that quietly reframes the
        footage is lying about what will be exported.

        The index maps are cached per source size. Rebuilding them each frame
        was measured at 250 ms for a 4K canvas - enough on its own to make a
        proxy slower than the original it was meant to replace.
        """
        height, width = image.shape[:2]
        if (width, height) == (self.width, self.height):
            return image

        key = (width, height)
        plan = self._fit_cache.get(key)
        if plan is None:
            scale = min(self.width / width, self.height / height)
            new_w = max(1, int(round(width * scale)))
            new_h = max(1, int(round(height * scale)))
            ys = (np.arange(new_h) * height // new_h).clip(0, height - 1)
            xs = (np.arange(new_w) * width // new_w).clip(0, width - 1)
            top = (self.height - new_h) // 2
            left = (self.width - new_w) // 2
            plan = (ys, xs, top, left, new_h, new_w)
            self._fit_cache[key] = plan

        ys, xs, top, left, new_h, new_w = plan
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

    def close(self) -> None:
        for track in self.tracks:
            track.producer.close()


def _over(base: np.ndarray, top: np.ndarray, opacity: float) -> np.ndarray:
    """Standard "over": ``top`` on ``base`` at ``opacity``."""
    if opacity >= 1.0:
        return top
    if opacity <= 0.0:
        return base
    return (base.astype(np.float32) * (1.0 - opacity)
            + top.astype(np.float32) * opacity).astype(np.uint8)
