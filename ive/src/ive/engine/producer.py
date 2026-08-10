"""Producers: the only things in the graph that know what time it is.

A producer answers one question - *give me frame N* - and is free to answer it
however it likes: by decoding a file, by generating a colour, or by pulling
from other producers. Everything downstream sees the same interface, which is
why a playlist and a tractor can themselves be producers (docs/ENGINE.md §2.4).

``ClipProducer`` is the leaf that reads a file. Its audio is decoded
**sequentially into a buffer**, not seeked per frame: a seek per frame would
cost more than decoding the whole track.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from fractions import Fraction
from pathlib import Path

import numpy as np

from ive.engine.frame import AudioFormat, Frame, Timebase

log = logging.getLogger(__name__)

__all__ = ["Producer", "ColourProducer", "ClipProducer"]


class Producer(ABC):
    """Something that can be asked for a frame."""

    #: Length in frames at the producer's own timebase.
    length: int = 0
    timebase: Timebase = Timebase()
    audio_format: AudioFormat = AudioFormat()
    name: str = ""

    @abstractmethod
    def frame_at(self, position: int) -> Frame | None:
        """Frame at ``position``, or None when out of range."""

    def close(self) -> None:
        """Release whatever the producer holds. Safe to call repeatedly."""

    # Convenience shared by every producer.
    def clamp(self, position: int) -> int:
        return max(0, min(int(position), max(0, self.length - 1)))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}({self.name!r}, {self.length} frames)"


class ColourProducer(Producer):
    """A flat colour of arbitrary length.

    This is the black track at the bottom of the stack, exactly as Kdenlive
    does it: with something always underneath, compositing never has to
    special-case "there is nothing here".
    """

    def __init__(self, width: int, height: int, length: int,
                 timebase: Timebase | None = None,
                 colour: tuple[int, int, int] = (0, 0, 0),
                 audio_format: AudioFormat | None = None,
                 name: str = "colour") -> None:
        self.width = width
        self.height = height
        self.length = max(0, int(length))
        self.timebase = timebase or Timebase()
        self.audio_format = audio_format or AudioFormat()
        self.colour = colour
        self.name = name
        self._cached: np.ndarray | None = None

    def _image(self) -> np.ndarray:
        # One buffer reused for every frame: it never changes, and allocating
        # a fresh 4K array 25 times a second for a black track is pure waste.
        if self._cached is None:
            self._cached = np.empty((self.height, self.width, 3), dtype=np.uint8)
            self._cached[:, :] = self.colour
        return self._cached

    def frame_at(self, position: int) -> Frame | None:
        if self.length and not (0 <= position < self.length):
            return None
        frame = Frame(position, self.timebase, self.audio_format,
                      image_fn=self._image)
        # A colour track is silent, but it still carries an audio block: the
        # mixer must never have to ask whether a track has audio at all.
        frame.set_audio(frame.silence())
        return frame


def _fit_size(source: tuple[int, int],
              canvas: tuple[int, int]) -> tuple[int, int]:
    """Largest size that fits ``source`` inside ``canvas``, keeping the ratio.

    Never crops and never stretches: an editor that quietly reframes the
    footage is lying about what will be exported.
    """
    width, height = int(source[0]), int(source[1])
    max_w, max_h = int(canvas[0]), int(canvas[1])
    if width <= 0 or height <= 0:
        return max_w, max_h
    scale = min(max_w / width, max_h / height)
    return max(2, int(round(width * scale))), max(2, int(round(height * scale)))


class ClipProducer(Producer):
    """A media file. The leaf of the graph.

    Video comes from :class:`~ive.media.decoder.VideoDecoder`, which already
    seeks frame-accurately. Audio is decoded sequentially into a buffer and
    resampled once to the engine format.
    """

    def __init__(self, path: str | Path, timebase: Timebase | None = None,
                 audio_format: AudioFormat | None = None,
                 proxy_path: str | Path | None = None,
                 canvas: tuple[int, int] | None = None) -> None:
        """``proxy_path`` supplies the PICTURE only.

        Timing, duration and audio always come from the original, so a proxy
        can never shift a cut or change what is heard - it only makes the
        picture cheap enough to scrub. See ive/media/proxy.py.
        """
        from ive.media.decoder import VideoDecoder
        from ive.media.probe import probe

        self.path = str(path)
        self.name = Path(self.path).name
        self.info = probe(self.path)
        self.audio_format = audio_format or AudioFormat()

        video = self.info.primary_video
        native = Timebase(Fraction(video.fps)) if video else Timebase()
        # The sequence rate wins. A clip at another rate is resampled in time
        # by asking its decoder for the nearest source frame - the only place
        # in the engine where rate conversion happens.
        self.timebase = timebase or native
        self._native = native

        # The decoder may read a proxy; everything else stays on the original.
        self.proxy_path = str(proxy_path) if proxy_path else ""
        self.using_proxy = bool(self.proxy_path) and self.proxy_path != self.path
        decode_path = self.proxy_path if self.using_proxy else self.path
        if video:
            self._decoder = (VideoDecoder(decode_path) if self.using_proxy
                             else VideoDecoder(self.path, self.info))
            if self.using_proxy:
                log.info("Reading pictures from a proxy for %s", self.name)
        else:
            self._decoder = None
        if self._decoder is not None and canvas:
            self._decoder.set_output_size(*_fit_size(video.display_size, canvas))
        self.source_length = (self._decoder.frame_count if self._decoder
                              else self.timebase.seconds_to_frames(self.info.duration))
        self.length = int(round(self.info.duration * float(self.timebase.fps))) or 1

        self._audio = _AudioTrack(self.path, self.audio_format) if self.info.has_audio else None

    # ── frames ────────────────────────────────────────────────────────

    def frame_at(self, position: int) -> Frame | None:
        if not (0 <= position < self.length):
            return None

        seconds = self.timebase.frames_to_seconds(position)

        def image():
            if self._decoder is None:
                return None
            # Map sequence position to source frame through TIME, so a 30 fps
            # clip on a 25 fps timeline lands on the right picture.
            source_index = int(round(seconds * self._native.fps))
            if source_index >= self.source_length:
                # `length` comes from the container duration, which the audio
                # stream usually outlives by a fraction of a second: those
                # tail positions have no picture. They are holes, not frames -
                # asking the decoder would clamp to the last frame and pay a
                # keyframe seek plus a GOP decode for every single one, which
                # is what froze playback at every clip boundary.
                return None
            decoded = self._decoder.frame_at(source_index)
            return decoded.array if decoded else None

        def audio():
            if self._audio is None:
                return None
            # Cumulative boundaries, not a constant count: at 29.97 fps a
            # rounded per-frame count drifts ~0.9 s/hour. Consecutive frames
            # share a boundary, so the blocks are gapless by construction.
            start, count = self.audio_format.sample_bounds(position, self.timebase)
            return self._audio.read(start, count)

        frame = Frame(position, self.timebase, self.audio_format,
                      image_fn=image, audio_fn=audio if self._audio else None)
        frame.properties["source"] = self.path
        return frame

    def close(self) -> None:
        if self._decoder is not None:
            self._decoder.close()
            self._decoder = None
        if self._audio is not None:
            self._audio.close()
            self._audio = None


class _AudioTrack:
    """Sequential audio decoding with a rewindable buffer.

    Audio is read forward and kept in a buffer; a request that lands behind
    the buffer rewinds the container. Decoding per frame with a seek each time
    would be an order of magnitude slower for no benefit, since playback and
    export both move forward.
    """

    def __init__(self, path: str, audio_format: AudioFormat) -> None:
        import av

        self._av = av
        self.path = path
        self.format = audio_format
        self._container = av.open(path)
        self._stream = self._container.streams.audio[0]
        self._stream.thread_type = "AUTO"
        self._resampler = self._make_resampler()
        self._buffer = np.zeros((0, audio_format.channels), dtype=np.float32)
        #: Sample index of buffer[0]. None until the first decode after a seek
        #: ANCHORS it to the pts the seek actually landed on. Anchoring to the
        #: requested time instead assumed the seek was exact; a keyframe seek
        #: is not, and the whole buffer was then labelled a fraction of a
        #: second away from where it really sat.
        self._buffer_start: int | None = None
        #: Where the last rewind aimed - the anchor of last resort when the
        #: first decoded frame carries no pts.
        self._target = 0
        self._iter = None
        self._exhausted = False

    def _make_resampler(self):
        # Recreated on every seek: a resampler keeps unflushed samples from
        # the old position, and they would come out at the head of the new one.
        return self._av.audio.resampler.AudioResampler(
            format="fltp",
            layout="stereo" if self.format.channels == 2 else "mono",
            rate=self.format.sample_rate,
        )

    def read(self, start: int, count: int) -> np.ndarray:
        """``count`` samples starting at absolute sample ``start``."""
        if self._buffer_start is None:
            if self._iter is None and not self._exhausted:
                # First use: land near the request instead of decoding the
                # whole file from zero to reach a playhead ten minutes in.
                self._rewind(start)
        elif (start < self._buffer_start
              or start > (self._buffer_start + len(self._buffer)
                          + self.format.sample_rate)):
            # Behind the buffer, or more than a second past its end: decoding
            # forward would be slower than the seek it avoids.
            self._rewind(start)
        while self._buffer_start is None and self._decode_more():
            pass
        if self._buffer_start is None:
            return np.zeros((count, self.format.channels), dtype=np.float32)
        while (self._buffer_start + len(self._buffer)) < (start + count):
            if not self._decode_more():
                break
        # The seek can land AFTER the request (the stream's first packet past
        # the target). The missing head is silence in its own place - sliding
        # later data earlier would be exactly the desync the anchor prevents.
        lead = min(count, max(0, self._buffer_start - start))
        offset = max(0, start - self._buffer_start)
        chunk = self._buffer[offset:offset + count - lead]
        if lead or len(chunk) < count - lead:
            out = np.zeros((count, self.format.channels), dtype=np.float32)
            if len(chunk):
                out[lead:lead + len(chunk)] = chunk
            return out
        return chunk

    def _rewind(self, start: int) -> None:
        seconds = max(0.0, start / self.format.sample_rate - 0.5)
        try:
            self._container.seek(int(seconds / float(self._stream.time_base)),
                                 stream=self._stream, backward=True)
        except Exception:
            log.exception("Audio seek failed in %s", Path(self.path).name)
        self._iter = None
        self._exhausted = False
        self._resampler = self._make_resampler()
        self._buffer = np.zeros((0, self.format.channels), dtype=np.float32)
        self._buffer_start = None        # the next decode anchors it
        self._target = int(seconds * self.format.sample_rate)

    def _decode_more(self) -> bool:
        if self._exhausted:
            return False
        if self._iter is None:
            self._iter = self._container.decode(self._stream)
        try:
            packet_frame = next(self._iter)
        except StopIteration:
            self._exhausted = True
            return False
        except Exception:
            log.exception("Audio decode error in %s", Path(self.path).name)
            self._exhausted = True
            return False

        if self._buffer_start is None:
            # Anchor the buffer to where the seek REALLY landed.
            pts = packet_frame.pts
            tb = packet_frame.time_base or self._stream.time_base
            if pts is not None and tb is not None:
                self._buffer_start = int(round(pts * tb * self.format.sample_rate))
            else:
                self._buffer_start = self._target

        chunks = []
        for resampled in self._resampler.resample(packet_frame):
            array = resampled.to_ndarray()          # (channels, samples), fltp
            chunks.append(np.ascontiguousarray(array.T, dtype=np.float32))
        if not chunks:
            return True
        block = np.concatenate(chunks)
        if block.ndim == 1:
            block = block[:, None]
        if block.shape[1] != self.format.channels:
            block = np.repeat(block[:, :1], self.format.channels, axis=1)

        self._buffer = np.concatenate([self._buffer, block]) if len(self._buffer) else block
        # Keep the buffer bounded: a few seconds is plenty for forward play.
        limit = self.format.sample_rate * 4
        if len(self._buffer) > limit:
            drop = len(self._buffer) - limit
            self._buffer = self._buffer[drop:]
            self._buffer_start += drop
        return True

    def close(self) -> None:
        try:
            self._container.close()
        except Exception:
            pass
