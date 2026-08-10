"""The frame: the only thing that travels through the graph.

Two rules make everything else work, both taken from MLT (docs/ENGINE.md §2):

**The position is written by the producer, and by nobody else.** A filter
receiving a frame has no idea where it sits on the timeline, who asked for it,
or what came before. That is what makes a filter a pure function: testable on
its own, and identical in preview and in export.

**Image and audio are two independent lazy stacks.** Asking for the picture
never decodes the sound, and asking for the sound never decodes the picture.
That is what makes waveform extraction, audio scrubbing and video-only export
cheap instead of special cases.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Callable

import numpy as np

log = logging.getLogger(__name__)

__all__ = ["Frame", "Timebase", "AudioFormat"]


@dataclass(frozen=True)
class Timebase:
    """The rate a sequence runs at. Everything inside the engine is frames."""

    fps: Fraction = Fraction(25, 1)

    def frames_to_seconds(self, frames: int) -> float:
        return float(frames / self.fps)

    def seconds_to_frames(self, seconds: float) -> int:
        return int(round(seconds * float(self.fps)))

    def frame_duration(self) -> float:
        return float(1 / self.fps)

    def __str__(self) -> str:
        return f"{float(self.fps):.3f} fps"


@dataclass(frozen=True)
class AudioFormat:
    """One internal audio format for the whole engine.

    Converting once at the edges means no module downstream has to think about
    sample rates or channel counts, and a mismatch cannot cause a subtle,
    intermittent bug in the middle of a mix.
    """

    sample_rate: int = 48000
    channels: int = 2

    def samples_for(self, frames: int, timebase: Timebase) -> int:
        return int(round(frames * self.sample_rate / float(timebase.fps)))

    def sample_bounds(self, position: int, timebase: Timebase) -> tuple[int, int]:
        """``(first_sample, count)`` of frame ``position``. Exact, cumulative.

        At a fractional rate no whole number of samples fits one frame:
        48000 / 29.97 is 1601.6. A constant ``round()`` count therefore gains
        0.4 samples on every frame - about 0.9 seconds of drift per hour,
        enough to lose lip sync inside one long take. Deriving each frame's
        block from the CUMULATIVE integer boundaries instead (frame N owns
        samples ``floor(N*rate/fps)`` up to ``floor((N+1)*rate/fps)``) makes
        the counts alternate 1601/1602 so the running total is always within
        one sample of true time, forever. Integer math throughout: float
        boundaries would disagree between two calls at large positions.
        """
        fps = timebase.fps
        start = position * self.sample_rate * fps.denominator // fps.numerator
        end = (position + 1) * self.sample_rate * fps.denominator // fps.numerator
        return start, end - start


class Frame:
    """One instant of the sequence, with lazily evaluated content."""

    __slots__ = ("position", "timebase", "audio_format", "_image_fn",
                 "_audio_fn", "_image", "_audio", "properties")

    def __init__(
        self,
        position: int,
        timebase: Timebase,
        audio_format: AudioFormat | None = None,
        image_fn: Callable[[], np.ndarray] | None = None,
        audio_fn: Callable[[], np.ndarray] | None = None,
    ) -> None:
        self.position = position
        self.timebase = timebase
        self.audio_format = audio_format or AudioFormat()
        self._image_fn = image_fn
        self._audio_fn = audio_fn
        self._image: np.ndarray | None = None
        self._audio: np.ndarray | None = None
        #: Free-form annotations a producer can leave for a filter downstream.
        self.properties: dict[str, Any] = {}

    # ── image ─────────────────────────────────────────────────────────

    @property
    def has_image(self) -> bool:
        return self._image is not None or self._image_fn is not None

    def image(self) -> np.ndarray | None:
        """RGB888 array, ``(height, width, 3)``. Evaluated on first request."""
        if self._image is None and self._image_fn is not None:
            try:
                self._image = self._image_fn()
            except Exception:
                log.exception("Image evaluation failed at frame %d", self.position)
                self._image = None
            self._image_fn = None      # evaluate once, whatever the outcome
        return self._image

    def set_image(self, image: np.ndarray | None) -> None:
        self._image = image
        self._image_fn = None

    # ── audio ─────────────────────────────────────────────────────────

    @property
    def has_audio(self) -> bool:
        return self._audio is not None or self._audio_fn is not None

    def audio(self) -> np.ndarray | None:
        """float32 array, ``(samples, channels)``, in [-1, 1]."""
        if self._audio is None and self._audio_fn is not None:
            try:
                self._audio = self._audio_fn()
            except Exception:
                log.exception("Audio evaluation failed at frame %d", self.position)
                self._audio = None
            self._audio_fn = None
        return self._audio

    def set_audio(self, audio: np.ndarray | None) -> None:
        self._audio = audio
        self._audio_fn = None

    def silence(self) -> np.ndarray:
        """A block of silence the right length for this frame.

        Sized from the frame's POSITION, not a constant: at fractional rates
        the per-frame count alternates (see AudioFormat.sample_bounds), and a
        silent gap must occupy exactly as many samples as the sound it
        replaces or everything after it lands early.
        """
        _, count = self.audio_format.sample_bounds(self.position, self.timebase)
        return np.zeros((count, self.audio_format.channels), dtype=np.float32)

    # ── helpers ───────────────────────────────────────────────────────

    def derive(self, *, image=None, audio=None) -> "Frame":
        """A copy carrying the same position, with content replaced.

        Filters use this rather than mutating in place, so a frame handed to
        two branches of the graph cannot be changed under the other's feet.
        """
        new = Frame(self.position, self.timebase, self.audio_format)
        new.properties = dict(self.properties)
        if image is not None:
            new.set_image(image)
        elif self._image is not None:
            new.set_image(self._image)
        else:
            new._image_fn = self._image_fn
        if audio is not None:
            new.set_audio(audio)
        elif self._audio is not None:
            new.set_audio(self._audio)
        else:
            new._audio_fn = self._audio_fn
        return new

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"Frame(pos={self.position}, image={'y' if self.has_image else 'n'}, "
                f"audio={'y' if self.has_audio else 'n'})")
