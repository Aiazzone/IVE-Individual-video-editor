"""Decoding off the GUI thread, across several source files.

Decoding a 4K frame takes tens of milliseconds. Doing that on the Qt thread
would freeze the interface on every scrub, so a worker thread owns the
decoders and hands finished frames back through a queued signal.

Two things make this fast enough to play a sequence:

**Request coalescing.** While dragging the playhead the user generates far
more requests than can be served. Serving them all would run the decoder
minutes behind the pointer, so the worker always jumps to the newest request
and drops the rest.

**A small decoder cache.** A timeline crosses from one file to the next
constantly. Reopening a container at every boundary would stall on each cut,
so a handful of decoders stay open, evicted least-recently-used.

**Read-ahead for playback.** Scrubbing and playing are different problems and
get different paths. Requesting a frame only once it is due - which is what
playback used to do - puts the whole decode latency on the critical path, and
worse, the decoder only has a fast path for the frame right after the last one
(`VideoDecoder.frame_at`). One late frame makes the clock skip an index, the
skip costs a seek, the seek is slower than a decode, and the next request skips
further: the stutter feeds itself. Measured at 2.1 fps on a 1080p file with
100% of frames seeking (`tests/test_playback_pacing.py`).

So playback runs a producer loop that decodes strictly in sequence into a small
buffer, and the clock takes whatever is ready. This is the shape of MLT's
consumer, which Kdenlive drives: a read-ahead thread fills a frame queue, and
the output side drops rather than waits. Same file, same machine: 30.2 fps with
one seek in ninety frames.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, Signal, Slot
from PySide6.QtGui import QImage

from ive.media.decoder import VideoDecoder
from ive.media.probe import MediaInfo, probe

log = logging.getLogger(__name__)

__all__ = ["VideoReader"]

#: How many containers stay open. Enough for the clip playing, the one before
#: and the one after, which is what a sequence actually touches.
_CACHE_SIZE = 3

#: Frames decoded in advance during playback. Deep enough to absorb the
#: variance between an I-frame and a B-frame, shallow enough that a seek does
#: not throw away much work.
_READ_AHEAD = 12
#: ...but the depth is capped by memory, not by frame count: twelve 4K frames
#: are 300 MB of RGB, which is not a buffer, it is a leak with a schedule.
_READ_AHEAD_BYTES = 64 * 1024 * 1024


def _read_ahead_depth(width: int, height: int) -> int:
    """How many frames to run ahead, given how big they are."""
    per_frame = max(1, int(width) * int(height) * 3)
    return max(3, min(_READ_AHEAD, _READ_AHEAD_BYTES // per_frame))


def _to_qimage(array) -> QImage:
    """RGB888 numpy array -> QImage that owns its pixels.

    The copy is mandatory: QImage does not take ownership of the buffer, and
    the array is freed as soon as the next frame is decoded.
    """
    height, width, _ = array.shape
    image = QImage(array.data, width, height, array.strides[0], QImage.Format.Format_RGB888)
    return image.copy()


class _Worker(QObject):
    """Lives on the decoding thread. Never touched directly from the GUI."""

    frameReady = Signal(str, int, float, QImage)   # path, index, time, image
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._decoders: "OrderedDict[str, VideoDecoder]" = OrderedDict()
        self._mutex = QMutex()
        self._pending: tuple[str, int] | None = None
        self._busy = False

    # ── decoder cache ─────────────────────────────────────────────────

    def _decoder_for(self, path: str) -> VideoDecoder | None:
        decoder = self._decoders.get(path)
        if decoder is not None:
            self._decoders.move_to_end(path)
            return decoder
        try:
            decoder = VideoDecoder(path)
        except Exception as exc:
            log.warning("Cannot open %s for decoding: %s", Path(path).name, exc)
            self.failed.emit(str(exc))
            return None
        self._decoders[path] = decoder
        self._decoders.move_to_end(path)
        while len(self._decoders) > _CACHE_SIZE:
            evicted_path, evicted = self._decoders.popitem(last=False)
            log.debug("Closing cached decoder for %s", Path(evicted_path).name)
            evicted.close()
        log.info("Decoder ready for %s (%d cached)", Path(path).name, len(self._decoders))
        return decoder

    @Slot(str)
    def preload(self, path: str) -> None:
        """Open a file before it is needed, so a cut does not stall."""
        if path and path not in self._decoders:
            self._decoder_for(path)

    @Slot()
    def close(self) -> None:
        for decoder in self._decoders.values():
            decoder.close()
        self._decoders.clear()

    # ── requests: the scrubbing path ──────────────────────────────────

    @Slot(str, int)
    def request(self, path: str, index: int) -> None:
        """Queue a frame request, keeping only the newest."""
        with QMutexLocker(self._mutex):
            self._pending = (path, index)
            if self._busy:
                return              # the running loop will pick this up
            self._busy = True
        try:
            self._drain()
        finally:
            with QMutexLocker(self._mutex):
                self._busy = False

    def _drain(self) -> None:
        while True:
            with QMutexLocker(self._mutex):
                job = self._pending
                self._pending = None
            if job is None:
                return
            path, index = job
            decoder = self._decoder_for(path)
            if decoder is None:
                return
            try:
                frame = decoder.frame_at(index)
            except Exception as exc:
                log.exception("Decode failed at frame %d of %s", index, Path(path).name)
                self.failed.emit(str(exc))
                return
            if frame is not None:
                self.frameReady.emit(path, frame.index, frame.time,
                                     _to_qimage(frame.array))


class _ReadAhead:
    """The playback producer: one thread that runs ahead of the clock.

    It pulls from a **source callable** - ``source(index)`` returning
    ``(time, rgb_array)`` or None past the end - so it does not care whether
    that is a single decoder or the whole render graph. Playback uses the
    graph; keeping the producer ignorant of it is what lets preview and export
    pull the same graph without this file knowing about either.

    Deliberately its own thread, and the ONLY thread that touches the source.
    Two reasons, both measured:

    * a producer driven by queued signals only runs when it is poked, and the
      poke rate is the consumption rate, so it can never build a reserve: 33
      fps where the same decoder standalone did 58, and every hiccup emptied
      the buffer;
    * two threads pulling one decoder move its cursor, and
      `VideoDecoder.frame_at` is only fast for cursor + 1, so everything after
      goes back on the seek path.

    A caller that needs to touch the source itself - rebuilding the graph
    after an edit - must call :meth:`suspend` and wait for it first.

    Plain threading rather than QThread: there is no event loop here, only a
    loop and a condition variable.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._thread: threading.Thread | None = None
        self._source = None
        self._key = ""
        self._next = 0
        self._end = -1
        self._depth = _READ_AHEAD
        #: Bumped on every start/stop, so a frame produced for a position the
        #: user has already left is discarded instead of shown.
        self._generation = 0
        #: Entries are ``[index, stamp, image, audio]``. Audio is taken once,
        #: in order, by take_audio(); image by take(). Mutable on purpose:
        #: taking the audio marks the slot None without touching the video.
        self._buffer: list = []
        #: Audio of entries popped by take() before take_audio() reached them.
        #: Front pops are older than everything left in the buffer, so playing
        #: this list first keeps the sample stream in order with no gaps.
        self._audio_backlog: list = []
        self._closing = False
        self._parked = True
        #: Called with an error message when the producer dies. Without it a
        #: failing source parked the thread in silence and playback stayed
        #: "playing" forever with a frozen picture. Runs on the read-ahead
        #: thread: the callback must be thread-safe (a queued signal emit is).
        self.on_error = None

    # -- control, called from the GUI thread ---------------------------

    def start(self, source, key: str, index: int, end: int,
              depth: int = _READ_AHEAD) -> None:
        """Produce from ``index``, discarding whatever was buffered."""
        with self._cond:
            self._source = source
            self._key = str(key)
            self._next = max(0, int(index))
            self._end = int(end)
            self._depth = max(2, int(depth))
            self._buffer.clear()
            self._audio_backlog.clear()
            self._generation += 1
            self._cond.notify_all()
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run,
                                            name="read-ahead", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Ask the producer to stop. Does not wait; see :meth:`suspend`."""
        with self._cond:
            self._source = None
            self._key = ""
            self._buffer.clear()
            self._audio_backlog.clear()
            self._generation += 1
            self._cond.notify_all()

    def suspend(self, timeout: float = 2.0) -> bool:
        """Stop, and wait until the producer is parked.

        The caller may then touch the source - rebuild the graph, close
        producers - knowing nothing is pulling on it. Returns False if it did
        not park in time, in which case the caller must not touch anything.
        """
        self.stop()
        deadline = time.monotonic() + timeout
        with self._cond:
            while not self._parked:
                thread = self._thread
                if thread is None or not thread.is_alive():
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    log.warning("Read-ahead did not park within %.1fs", timeout)
                    return False
                self._cond.wait(remaining)
        return True

    def take(self, key: str, index: int):
        """Newest buffered frame at or before ``index``; None if not ready.

        Older frames are dropped rather than shown. Falling behind has to cost
        frames, not time, or playback drifts away from the clock and never
        comes back. This is what MLT does with a positive ``real_time``.
        """
        with self._cond:
            if self._key != str(key) or not self._buffer:
                return None
            chosen = None
            while self._buffer and self._buffer[0][0] <= index:
                chosen = self._buffer.pop(0)
                if chosen[3] is not None:
                    # The clock reached this frame before its sound was taken
                    # (right after priming, mostly). The samples are still the
                    # NEXT ones due at the device - late video costs frames,
                    # late audio must never cost samples, or every drop leaves
                    # a click and shortens the sound track.
                    self._audio_backlog.append(chosen[3])
                    chosen[3] = None
            if chosen is not None:
                self._cond.notify_all()      # room for the producer
            return (chosen[0], chosen[1], chosen[2]) if chosen else None

    def take_audio(self, key: str, max_samples: int) -> list:
        """Blocks of sound not yet handed out, in order, consumed exactly once.

        Audio and video leave the buffer independently: the picture of a frame
        is taken when the clock reaches it, its sound as soon as the sink has
        room - which is EARLIER, since the sink buffers ahead. Whole blocks
        are returned until ``max_samples`` is covered; the last one may
        overshoot rather than be split.
        """
        with self._cond:
            if self._key != str(key):
                return []
            blocks: list = []
            taken = 0
            while self._audio_backlog and taken < max_samples:
                block = self._audio_backlog.pop(0)
                blocks.append(block)
                taken += len(block)
            for entry in self._buffer:
                if taken >= max_samples:
                    break
                if entry[3] is not None:
                    blocks.append(entry[3])
                    taken += len(entry[3])
                    entry[3] = None
            return blocks

    def shutdown(self) -> None:
        with self._cond:
            self._closing = True
            self._source = None
            self._cond.notify_all()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)

    # -- the producer thread -------------------------------------------

    def _run(self) -> None:
        log.info("Read-ahead thread started")
        while True:
            with self._cond:
                while not self._closing and (
                        self._source is None
                        or len(self._buffer) >= self._depth
                        or (self._end >= 0 and self._next > self._end)):
                    self._parked = True
                    self._cond.notify_all()
                    self._cond.wait(0.25)
                if self._closing:
                    break
                self._parked = False
                source = self._source
                index = self._next
                generation = self._generation

            try:
                produced = source(index)
            except Exception as exc:
                log.exception("Read-ahead failed at frame %d", index)
                with self._cond:
                    if self._generation == generation:
                        self._source = None
                notify = self.on_error
                if notify is not None:
                    try:
                        notify(f"Playback stopped at frame {index}: {exc}")
                    except Exception:
                        log.exception("Read-ahead error callback failed")
                continue

            image = None
            stamp = 0.0
            audio = None
            if produced is not None:
                # (time, image) from a plain video source, or
                # (time, image, audio) from the graph. Either may be None.
                if len(produced) == 3:
                    stamp, array, audio = produced
                else:
                    stamp, array = produced
                if array is not None:
                    image = _to_qimage(array)

            with self._cond:
                # A seek, a stop or a rebuild happened while this frame was
                # being produced: it belongs to a position already left.
                if self._generation != generation:
                    continue
                if image is None and audio is None:
                    # A frame with no picture is NOT the end of the stream. It
                    # happens in the middle of a sequence - a gap between
                    # clips, a boundary where the playlist has nothing for one
                    # index. Treating it as the end stopped the producer for
                    # good, so playback froze on the last picture of the first
                    # clip and never reached the second.
                    #
                    # Where the stream really ends is already known: `end` was
                    # given at start() and the wait loop above stops there. So
                    # here we only step over the hole.
                    #
                    # A frame with sound but no picture is buffered: on the
                    # timeline that is a gap under a live soundtrack, and
                    # dropping it would cut a hole in the audio.
                    self._next = index + 1
                    continue
                self._buffer.append([index, stamp, image, audio])
                self._next = index + 1

        with self._cond:
            self._parked = True
            self._cond.notify_all()
        log.info("Read-ahead thread stopped")


class VideoReader(QObject):
    """GUI-side handle on the decoding thread."""

    #: (source path, frame index, presentation time, image)
    frameReady = Signal(str, int, float, QImage)
    opened = Signal(object)      # MediaInfo
    failed = Signal(str)

    _preloadRequested = Signal(str)
    _frameRequested = Signal(str, int)
    _closeRequested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.info: MediaInfo | None = None
        #: Metadata for every source seen, so a sequence does not re-probe.
        self._known: dict[str, MediaInfo] = {}

        #: The playback producer, on its own thread with its own decoders.
        self._ahead = _ReadAhead()
        # Emitted from the read-ahead thread; a cross-thread signal emit is
        # queued, so the GUI-side slots run on the GUI thread.
        self._ahead.on_error = self.failed.emit

        self._thread = QThread()
        self._thread.setObjectName("media-decode")
        self._worker = _Worker()
        self._worker.moveToThread(self._thread)

        self._preloadRequested.connect(self._worker.preload)
        self._frameRequested.connect(self._worker.request)
        self._closeRequested.connect(self._worker.close)
        self._worker.frameReady.connect(self.frameReady)
        self._worker.failed.connect(self.failed)

        self._thread.start()

    # ── sources ───────────────────────────────────────────────────────

    def describe(self, path: str | Path) -> MediaInfo | None:
        """Probe a file once and remember it."""
        key = str(path)
        if key in self._known:
            return self._known[key]
        try:
            info = probe(key)
        except Exception as exc:
            log.warning("Probe failed for %s: %s", Path(key).name, exc)
            self.failed.emit(str(exc))
            return None
        self._known[key] = info
        return info

    def open(self, path: str | Path) -> bool:
        """Make ``path`` the current single source."""
        info = self.describe(path)
        if info is None:
            return False
        if not info.has_video:
            message = f"{Path(str(path)).name} has no video stream"
            log.warning(message)
            self.failed.emit(message)
            return False
        self.info = info
        self._preloadRequested.emit(str(path))
        self.opened.emit(info)
        return True

    def preload(self, path: str | Path) -> None:
        self._preloadRequested.emit(str(path))

    def request_frame(self, path: str | Path, index: int) -> None:
        """One frame, now. For scrubbing, stepping and the paused view."""
        self._frameRequested.emit(str(path), int(index))

    # ── playback ──────────────────────────────────────────────────────

    def start_stream(self, source, key: str, index: int, end: int = -1,
                     depth: int = _READ_AHEAD) -> None:
        """Begin producing ahead from ``index``. Call on play, and on seek."""
        self._ahead.start(source, key, int(index), int(end), depth)

    def stop_stream(self) -> None:
        self._ahead.stop()

    def suspend_stream(self, timeout: float = 2.0) -> bool:
        """Stop and wait, so the caller can safely rebuild the source."""
        return self._ahead.suspend(timeout)

    @staticmethod
    def read_ahead_depth(width: int, height: int) -> int:
        """Frames to run ahead at this frame size, capped by memory."""
        return _read_ahead_depth(width, height)

    def take_frame(self, key: str, index: int):
        """The newest ready frame at or before ``index``, or None.

        Returns ``(index, time, QImage)``; the image is None for a frame that
        is a gap in the video but carries sound. Called from the GUI thread on
        every tick: it never blocks, so a decoder that falls behind costs a
        repeated frame rather than a frozen interface.
        """
        return self._ahead.take(str(key), int(index))

    def take_audio(self, key: str, max_samples: int) -> list:
        """Sound produced ahead and not yet handed out, in order.

        Each element is a float32 ``(samples, channels)`` block in the engine
        format. Every block is returned exactly once; the transport feeds them
        straight to the audio sink.
        """
        return self._ahead.take_audio(str(key), int(max_samples))

    def close(self) -> None:
        self._ahead.stop()
        self._closeRequested.emit()
        self.info = None

    def shutdown(self) -> None:
        """Stop both threads cleanly. Called once, at application exit."""
        self._ahead.shutdown()
        self.close()
        self._thread.quit()
        if not self._thread.wait(3000):
            log.warning("Decoding thread did not stop in time; terminating")
            self._thread.terminate()
            self._thread.wait(1000)
        log.info("Decoding thread stopped")
