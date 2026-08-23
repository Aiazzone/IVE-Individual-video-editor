"""Voice activity detection: is somebody TALKING here?

Silero VAD (snakers4/silero-vad, MIT - weights included) as a ~2 MB
ONNX model run on the CPU: 16 kHz mono in 512-sample chunks, each
prefixed with 64 samples of context from the previous chunk (the v5
model expects 576 in; without the context every probability collapses
to zero), an LSTM state carried between chunks, one speech probability
out. Measured on this pipeline: real speech ~0.8 mean, a 440 Hz tone or
white noise under 0.05 - which is exactly the distinction the "smart"
ducking mode is for (docs/AUDIO.md §6).

The model lives in ``models/vad/silero_vad.onnx`` (the heavy-resources
sister folder, never the repository). ``SpeechDetector.load()`` returns
``None`` when the model or onnxruntime is missing; callers fall back to
the energy detector and say so once.
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

__all__ = ["SpeechDetector"]

_RATE = 16000
_CHUNK = 512
_CONTEXT = 64


class SpeechDetector:
    """One Silero session with its rolling state; NOT thread-safe -
    each consumer (a GuideLevel) owns its own."""

    def __init__(self, session) -> None:
        self._session = session
        self._sr = np.array(_RATE, dtype=np.int64)
        self.reset()

    @classmethod
    def load(cls) -> "SpeechDetector | None":
        """The detector, or ``None`` (no model / no runtime / bad file)."""
        from ive.utils.paths import get_model_path

        path = get_model_path("vad/silero_vad.onnx")
        if not path.is_file():
            log.info("No VAD model at %s", path)
            return None
        try:
            import onnxruntime as ort
        except ImportError:
            log.info("onnxruntime not installed: no VAD")
            return None
        try:
            options = ort.SessionOptions()
            options.log_severity_level = 3
            session = ort.InferenceSession(
                str(path), sess_options=options,
                providers=["CPUExecutionProvider"])
        except Exception:
            log.exception("VAD model would not load (%s)", path)
            return None
        log.info("VAD model loaded: %s", path.name)
        return cls(session)

    def reset(self) -> None:
        """Forget the stream - call on a seek, not between blocks."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(_CONTEXT, dtype=np.float32)
        self._pending = np.zeros(0, dtype=np.float32)
        self._last = 0.0

    def speech_probability(self, samples: np.ndarray, rate: int) -> float:
        """Highest speech probability over this block of audio.

        ``samples`` is float in [-1, 1], mono ``(n,)`` or ``(n, ch)`` at
        ``rate``. A block shorter than one chunk is buffered and answered
        with the previous probability until enough sound has arrived.
        """
        mono = np.asarray(samples, dtype=np.float32)
        if mono.ndim == 2:
            mono = mono.mean(axis=1)
        if rate != _RATE and mono.size:
            wanted = max(1, int(round(mono.size * _RATE / float(rate))))
            mono = np.interp(
                np.linspace(0.0, mono.size - 1.0, wanted,
                            dtype=np.float64),
                np.arange(mono.size, dtype=np.float64), mono
            ).astype(np.float32)
        stream = np.concatenate([self._pending, mono])
        best = None
        offset = 0
        while stream.size - offset >= _CHUNK:
            chunk = stream[offset:offset + _CHUNK]
            fed = np.concatenate([self._context, chunk])[None, :]
            out, self._state = self._session.run(
                None, {"input": fed, "state": self._state, "sr": self._sr})
            probability = float(out[0, 0])
            best = probability if best is None else max(best, probability)
            self._context = chunk[-_CONTEXT:]
            offset += _CHUNK
        self._pending = stream[offset:]
        if best is not None:
            self._last = best
        return self._last
