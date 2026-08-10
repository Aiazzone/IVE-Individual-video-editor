"""Frame-accurate video decoding.

The hard part of a video editor is not decoding, it is landing on the *exact*
frame the user asked for. Containers only allow seeking to a keyframe, so:

    seek to the keyframe at or before the target, then decode forward until
    the frame whose timestamp reaches the target.

Anything simpler lands on the wrong frame, and every cut made afterwards is
off by up to a whole GOP.

This class is **not thread-safe** and must be used from one thread only:
FFmpeg decoder contexts are not shareable. :mod:`ive.media.reader` owns one of
these on a worker thread.
"""

from __future__ import annotations

import logging
from fractions import Fraction
from pathlib import Path

import numpy as np

from ive.media.probe import MediaInfo, MediaProbeError, VideoStreamInfo, probe

log = logging.getLogger(__name__)

__all__ = ["VideoDecoder", "DecodedFrame", "MediaDecodeError"]

#: Forward jumps up to this many frames decode-and-discard rather than seek.
#: A discard costs one decode (~10 ms); a seek costs a keyframe seek plus a
#: GOP decode (up to ~250 frames), so the window must stay well below a GOP.
_STEP_WINDOW = 32


class MediaDecodeError(RuntimeError):
    """Decoding failed in a way the caller has to know about."""


class DecodedFrame:
    """One decoded frame, in RGB888, already rotated for display."""

    __slots__ = ("index", "time", "array")

    def __init__(self, index: int, time: float, array: np.ndarray) -> None:
        self.index = index
        self.time = time
        self.array = array

    @property
    def size(self) -> tuple[int, int]:
        return self.array.shape[1], self.array.shape[0]


class VideoDecoder:
    """Sequential and random access to the video frames of one file."""

    def __init__(self, path: str | Path, info: MediaInfo | None = None) -> None:
        import av

        self._av = av
        self.path = Path(path)
        self.info: MediaInfo = info or probe(self.path)

        video = self.info.primary_video
        if video is None:
            raise MediaProbeError(f"{self.path.name} has no video stream")
        self.video: VideoStreamInfo = video

        self._container = av.open(str(self.path))
        self._stream = self._container.streams.video[0]
        # Let FFmpeg use several cores; the worker thread stays responsive.
        self._stream.thread_type = "AUTO"

        self._time_base: Fraction = Fraction(self._stream.time_base or Fraction(1, 1000))
        self._start_time: int = int(self._stream.start_time or 0)
        self._fps: float = float(self.video.fps) or 25.0
        #: Index of the last frame handed out, for cheap sequential reads.
        self._cursor: int = -1
        #: The frame at `_cursor`, kept so a repeated index is free. Rate
        #: conversion asks for the same source frame more than once (a 25 fps
        #: clip on a 30 fps timeline repeats every few frames), and without
        #: this each repeat misses the cursor+1 fast path and pays a keyframe
        #: seek plus a GOP decode. Consumers must not mutate the array
        #: (the Filter contract already forbids it).
        self._last: DecodedFrame | None = None
        #: Size to hand frames out at, or None for the source size.
        self._output_size: tuple[int, int] | None = None
        self._iter = None
        self._closed = False

    # ── geometry and timing ───────────────────────────────────────────

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def frame_count(self) -> int:
        """Number of frames, from the stream when known, else from duration."""
        if self.video.frames:
            return self.video.frames
        return max(1, int(round(self.video.duration * self._fps)))

    def frame_to_time(self, index: int) -> float:
        return index / self._fps

    def time_to_frame(self, seconds: float) -> int:
        return max(0, int(round(seconds * self._fps)))

    # ── decoding ──────────────────────────────────────────────────────

    def frame_at(self, index: int) -> DecodedFrame | None:
        """Return the frame at ``index``, seeking only when necessary.

        Reading forward one frame at a time - playback and scrubbing right -
        never seeks, which is what keeps it smooth.
        """
        if self._closed:
            raise MediaDecodeError("Decoder is closed")

        index = max(0, min(index, self.frame_count - 1))

        if index == self._cursor and self._last is not None:
            return self._last

        # Small forward steps decode-and-discard instead of seeking: rate
        # conversion on a mixed-fps timeline asks for source indices that
        # jump by 2 or 3 (a 60 fps clip on a 30 fps sequence), and a seek
        # costs a whole GOP where a discard costs one decode.
        if (self._iter is not None
                and self._cursor < index <= self._cursor + _STEP_WINDOW):
            frame = None
            for _ in range(index - self._cursor):
                frame = self._next_raw()
                if frame is None:
                    break
            if frame is not None:
                self._cursor = index
                self._last = self._convert(frame, index)
                return self._last
            # Ran past the end: fall through and seek.

        return self._seek_and_decode(index)

    def _seek_and_decode(self, index: int) -> DecodedFrame | None:
        target_time = self.frame_to_time(index)
        # Aim slightly before the target: seeking lands on the keyframe at or
        # before this timestamp, and we then decode forward to the exact frame.
        target_pts = int(target_time / self._time_base) + self._start_time

        try:
            self._container.seek(target_pts, stream=self._stream, backward=True, any_frame=False)
        except Exception as exc:
            raise MediaDecodeError(f"Seek failed at frame {index}: {exc}") from exc

        self._iter = self._container.decode(self._stream)
        # Half a frame of tolerance absorbs the rounding of pts arithmetic.
        tolerance = 0.5 / self._fps
        last = None

        for _ in range(4096):  # a GOP is far shorter; this is a runaway guard
            frame = self._next_raw()
            if frame is None:
                break
            frame_time = self._time_of(frame)
            last = frame
            if frame_time >= target_time - tolerance:
                self._cursor = index
                self._last = self._convert(frame, index)
                return self._last

        if last is not None:
            log.debug("Frame %d not reached exactly; using the last decoded one", index)
            self._cursor = index
            self._last = self._convert(last, index)
            return self._last

        log.warning("No frame decoded at index %d of %s", index, self.path.name)
        self._last = None
        return None

    def _next_raw(self):
        if self._iter is None:
            self._iter = self._container.decode(self._stream)
        try:
            return next(self._iter)
        except StopIteration:
            return None
        except Exception as exc:
            # A damaged packet must not kill the reader thread.
            log.warning("Decode error in %s: %s", self.path.name, exc)
            return None

    def _time_of(self, frame) -> float:
        pts = frame.pts
        if pts is None:
            return 0.0
        return float((pts - self._start_time) * self._time_base)

    def set_output_size(self, width: int | None, height: int | None) -> None:
        """Hand frames out at this size, scaled by FFmpeg rather than numpy.

        Scaling here is not an optimisation detail, it is where the resize
        belongs: swscale is SIMD C, and it runs on the YUV frame before the
        RGB conversion. Doing the same work afterwards with numpy fancy
        indexing measured 32 ms a frame against 10.5 for the decode itself -
        on a 33 ms budget, the resize alone was the reason preview stuttered.

        Ignored for rotated video: rotation swaps the axes after conversion,
        so the requested size would apply to the wrong pair. Rare enough to be
        worth the simplicity.
        """
        if not width or not height or self.video.rotation:
            self._output_size = None
            self._last = None
            return
        self._output_size = (max(2, int(width)), max(2, int(height)))
        # The cached frame is at the old size; a repeat must not serve it.
        self._last = None

    def _convert(self, frame, index: int) -> DecodedFrame:
        """FFmpeg frame -> contiguous RGB888 array, rotated for display."""
        if self._output_size is not None:
            width, height = self._output_size
            array = frame.to_ndarray(format="rgb24", width=width, height=height)
        else:
            array = frame.to_ndarray(format="rgb24")

        rotation = self.video.rotation
        if rotation == 90:
            array = np.rot90(array, k=-1)
        elif rotation == 180:
            array = np.rot90(array, k=2)
        elif rotation == 270:
            array = np.rot90(array, k=1)

        # np.rot90 returns a view with a negative stride; QImage needs a real
        # contiguous buffer or it renders garbage.
        if not array.flags["C_CONTIGUOUS"]:
            array = np.ascontiguousarray(array)

        return DecodedFrame(index, self._time_of(frame), array)

    # ── lifecycle ─────────────────────────────────────────────────────

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._iter = None
        try:
            self._container.close()
        except Exception:
            log.exception("Error closing %s", self.path.name)

    def __enter__(self) -> "VideoDecoder":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - best effort
        try:
            self.close()
        except Exception:
            pass
