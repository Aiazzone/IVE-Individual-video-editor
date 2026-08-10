"""Audio output: plays the graph's samples and owns the playback clock.

The one architectural decision in this file: **when audio plays, audio IS the
clock.** A sound card consumes samples at its own crystal's idea of 48 kHz,
which is not the same as QElapsedTimer's idea of a second. Two clocks in
disagreement drift apart - video timed by the timer slides against audio timed
by the hardware, and lip sync is gone within minutes. So the transport asks
this class what time it is (`elapsed_seconds`, derived from how much audio the
device has actually processed) and the timer remains only as the fallback for
machines with no audio device at all.

Push mode, deliberately: the GUI tick hands blocks in and this class writes as
much as the sink will take, keeping the rest in a pending queue. Pull mode
would mean a Qt-driven callback asking the graph for audio on its own
schedule - a second consumer thread on a graph that only allows one.

The class never touches the graph. It receives ready blocks, float32
``(samples, channels)`` in [-1, 1] - the engine format from
:class:`ive.engine.frame.AudioFormat` - and converts once at this edge.
"""

from __future__ import annotations

import logging
import threading
from collections import deque

import numpy as np
from PySide6.QtCore import QObject

from ive.engine.frame import AudioFormat

log = logging.getLogger(__name__)

__all__ = ["AudioOutput"]

#: How much sound may sit in the device buffer. Latency and safety margin at
#: once: smaller reacts faster to a seek, larger survives a busy GUI tick.
_SINK_SECONDS = 0.2
#: How much this class holds beyond the device buffer before it stops asking
#: the transport for more. Bounded, or a stalled sink would hoard the session.
_PENDING_SECONDS = 0.4


class AudioOutput(QObject):
    """Owns the QAudioSink; created and used on the GUI thread only."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sink = None
        self._io = None                     # QIODevice while started
        self._format = AudioFormat()
        self._float_samples = True          # sink takes float32; else int16
        self._bytes_per_row = 8
        self._pending: deque[np.ndarray] = deque()
        self._pending_samples = 0
        #: Test tap: called with every float32 block ACCEPTED by the sink, in
        #: order. This is how the tone test measures after the sink instead of
        #: after the graph - it sees exactly what the device is given.
        self.on_write = None

    # -- lifecycle ------------------------------------------------------

    _warm_thread: threading.Thread | None = None

    @classmethod
    def warm_up(cls) -> None:
        """Pay the audio backend's first-touch cost off the GUI thread.

        The first format query of the process takes ~0.5 s on Windows (the
        WASAPI session handshake); paid inside play(), it held the first
        frame back for half a second and read as "pressing play is slow".
        Measured: after this probe runs anywhere, the same query on the GUI
        thread is instant and the first sink start drops to ~0.19 s.

        Call it once, early - the transport does so at construction.
        """
        if cls._warm_thread is not None:
            return

        def probe() -> None:
            try:
                from PySide6.QtMultimedia import QAudioFormat, QMediaDevices
                device = QMediaDevices.defaultAudioOutput()
                if device.isNull():
                    return
                wanted = QAudioFormat()
                engine = AudioFormat()
                wanted.setSampleRate(engine.sample_rate)
                wanted.setChannelCount(engine.channels)
                wanted.setSampleFormat(QAudioFormat.SampleFormat.Float)
                device.isFormatSupported(wanted)
            except Exception:
                log.debug("Audio warm-up failed; configure() pays the cost",
                          exc_info=True)

        cls._warm_thread = threading.Thread(target=probe, name="audio-warmup",
                                            daemon=True)
        cls._warm_thread.start()

    def configure(self, audio_format: AudioFormat) -> bool:
        """Open the default output device for the engine format.

        False means "no audio on this machine" - missing QtMultimedia, no
        device, or a device that takes neither float nor int16. The caller
        must then keep its timer clock; nothing here half-works.
        """
        self.stop()
        warm = AudioOutput._warm_thread
        if warm is not None and warm.is_alive():
            # Never race the warm-up probe into the backend: two first-touch
            # initialisations at once is exactly the kind of native-level
            # concurrency nobody tests.
            warm.join(timeout=3.0)
        try:
            from PySide6.QtMultimedia import (QAudioFormat, QAudioSink,
                                              QMediaDevices)
        except ImportError:
            log.warning("QtMultimedia is not available; playback is silent")
            return False

        device = QMediaDevices.defaultAudioOutput()
        if device.isNull():
            log.warning("No audio output device; playback is silent")
            return False

        wanted = QAudioFormat()
        wanted.setSampleRate(audio_format.sample_rate)
        wanted.setChannelCount(audio_format.channels)
        wanted.setSampleFormat(QAudioFormat.SampleFormat.Float)
        self._float_samples = True
        if not device.isFormatSupported(wanted):
            wanted.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            self._float_samples = False
            if not device.isFormatSupported(wanted):
                log.warning("Device %s takes neither float32 nor int16 at "
                            "%d Hz; playback is silent",
                            device.description(), audio_format.sample_rate)
                return False

        self._format = audio_format
        sample_bytes = 4 if self._float_samples else 2
        self._bytes_per_row = sample_bytes * audio_format.channels
        self._sink = QAudioSink(device, wanted, self)
        self._sink.setBufferSize(
            int(audio_format.sample_rate * self._bytes_per_row * _SINK_SECONDS))
        log.info("Audio output ready: %s, %d Hz, %d ch, %s",
                 device.description(), audio_format.sample_rate,
                 audio_format.channels,
                 "float32" if self._float_samples else "int16")
        return True

    def restart(self) -> None:
        """Discard everything buffered and zero the clock.

        Called at every play and every seek: whatever was queued belongs to a
        position the user just left, and `elapsed_seconds` must restart from
        zero so the transport can anchor it to the new position.
        """
        if self._sink is None:
            return
        self._sink.stop()
        self._pending.clear()
        self._pending_samples = 0
        self._io = self._sink.start()
        if self._io is None:
            log.warning("Audio sink failed to start; playback is silent")

    def stop(self) -> None:
        if self._sink is not None:
            self._sink.stop()
        self._io = None
        self._pending.clear()
        self._pending_samples = 0

    # -- data -----------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._io is not None

    def room_samples(self) -> int:
        """How many more samples this class wants right now. May be zero."""
        if self._io is None:
            return 0
        cap = int(self._format.sample_rate * _PENDING_SECONDS)
        return max(0, cap - self._pending_samples)

    def push(self, block: np.ndarray) -> None:
        """Queue one engine-format block. Cheap; the write happens in pump()."""
        if self._io is None or block is None or not len(block):
            return
        self._pending.append(block)
        self._pending_samples += len(block)

    def pump(self) -> None:
        """Write as much pending audio as the sink will take, never blocking."""
        if self._io is None or self._sink is None:
            return
        while self._pending:
            rows = self._sink.bytesFree() // self._bytes_per_row
            if rows <= 0:
                return
            block = self._pending[0]
            take = block[:rows] if rows < len(block) else block
            written = self._io.write(self._convert(take))
            if written is None or written <= 0:
                return
            accepted = int(written) // self._bytes_per_row
            self._pending_samples -= accepted
            if accepted < len(block):
                self._pending[0] = block[accepted:]
            else:
                self._pending.popleft()
            if self.on_write is not None:
                self.on_write(block[:accepted])
            if accepted < len(take):
                return                      # the sink is full mid-block

    # -- the clock ------------------------------------------------------

    def elapsed_seconds(self) -> float:
        """Seconds of audio the device has processed since restart().

        This is the master clock during playback. It advances only as the
        hardware consumes samples: while the sink is starved it stands still,
        so video timed against it waits instead of drifting ahead of sound.
        """
        if self._sink is None:
            return 0.0
        return self._sink.processedUSecs() / 1_000_000.0

    def _convert(self, block: np.ndarray) -> bytes:
        data = np.ascontiguousarray(block, dtype=np.float32)
        if self._float_samples:
            return data.tobytes()
        return (np.clip(data, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
