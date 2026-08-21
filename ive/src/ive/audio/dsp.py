"""Audio effect ops: the vocabulary behind an audio-effect recipe.

A recipe is a list of ops (docs/AUDIO.md). Each op is a small, named
stage; ``AudioChain`` runs them in order over the engine's float32
``(samples, channels)`` blocks, one block per TRACK frame (40 ms at
25 fps). Filters and dynamics keep STATE across blocks - a biquad cut at
every frame boundary would click, a compressor with no memory would
pump - and that state resets whenever the blocks stop arriving in
sequence (a seek, a different clip).

Ops (all parameters optional, with the defaults below):

    gain        db=0                          plain level change
    highpass    hz=80,   q=0.707              rumble, handling noise
    lowpass     hz=8000, q=0.707              hiss, telephone feel
    low_shelf   hz=200,  db=0                 warmth / mud
    high_shelf  hz=4000, db=0                 air / harshness
    peak        hz=1000, q=1.0, db=0          presence, a resonance
    compressor  threshold_db=-18, ratio=3, attack_ms=10, release_ms=120,
                makeup_db=0                   evens the level out
    loudness    target_db=-16, max_gain_db=12 steers the RMS level to a
                                              target, slowly (normalise)
    limiter     ceiling_db=-1                 nothing above the ceiling

Unknown ops are skipped with one warning, never a crash: a recipe from a
newer version still plays. dB in, linear inside.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

__all__ = ["AudioChain", "OPS", "db_to_gain"]

OPS = ("gain", "highpass", "lowpass", "low_shelf", "high_shelf", "peak",
       "compressor", "loudness", "limiter")

_warned: set[str] = set()


def db_to_gain(db: float) -> float:
    return float(10.0 ** (float(db) / 20.0))


def _f(op: dict, key: str, default: float) -> float:
    try:
        return float(op.get(key, default))
    except (TypeError, ValueError):
        return float(default)


# ── biquads (RBJ cookbook) ─────────────────────────────────────────────

def _biquad(kind: str, rate: int, hz: float, q: float, db: float):
    """``(b, a)`` normalised so a[0] == 1."""
    hz = max(10.0, min(hz, rate * 0.45))
    w0 = 2.0 * math.pi * hz / rate
    cos_w0, sin_w0 = math.cos(w0), math.sin(w0)
    alpha = sin_w0 / (2.0 * max(0.1, q))
    A = 10.0 ** (db / 40.0)
    if kind == "lowpass":
        b = [(1 - cos_w0) / 2, 1 - cos_w0, (1 - cos_w0) / 2]
        a = [1 + alpha, -2 * cos_w0, 1 - alpha]
    elif kind == "highpass":
        b = [(1 + cos_w0) / 2, -(1 + cos_w0), (1 + cos_w0) / 2]
        a = [1 + alpha, -2 * cos_w0, 1 - alpha]
    elif kind == "peak":
        b = [1 + alpha * A, -2 * cos_w0, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cos_w0, 1 - alpha / A]
    elif kind == "low_shelf":
        s = 2 * math.sqrt(A) * alpha
        b = [A * ((A + 1) - (A - 1) * cos_w0 + s),
             2 * A * ((A - 1) - (A + 1) * cos_w0),
             A * ((A + 1) - (A - 1) * cos_w0 - s)]
        a = [(A + 1) + (A - 1) * cos_w0 + s,
             -2 * ((A - 1) + (A + 1) * cos_w0),
             (A + 1) + (A - 1) * cos_w0 - s]
    elif kind == "high_shelf":
        s = 2 * math.sqrt(A) * alpha
        b = [A * ((A + 1) + (A - 1) * cos_w0 + s),
             -2 * A * ((A - 1) + (A + 1) * cos_w0),
             A * ((A + 1) + (A - 1) * cos_w0 - s)]
        a = [(A + 1) - (A - 1) * cos_w0 + s,
             2 * ((A - 1) - (A + 1) * cos_w0),
             (A + 1) - (A - 1) * cos_w0 - s]
    else:
        raise ValueError(kind)
    a0 = a[0]
    return (np.array([v / a0 for v in b], dtype=np.float64),
            np.array([v / a0 for v in a], dtype=np.float64))


class _Biquad:
    def __init__(self, kind: str, op: dict, rate: int) -> None:
        defaults = {"lowpass": (8000.0, 0.707, 0.0),
                    "highpass": (80.0, 0.707, 0.0),
                    "low_shelf": (200.0, 0.707, 0.0),
                    "high_shelf": (4000.0, 0.707, 0.0),
                    "peak": (1000.0, 1.0, 0.0)}[kind]
        self.b, self.a = _biquad(kind, rate, _f(op, "hz", defaults[0]),
                                 _f(op, "q", defaults[1]),
                                 _f(op, "db", defaults[2]))
        self.identity = (kind in ("low_shelf", "high_shelf", "peak")
                         and abs(_f(op, "db", 0.0)) < 1e-6)
        self.zi = None

    def reset(self) -> None:
        self.zi = None

    def __call__(self, block: np.ndarray) -> np.ndarray:
        if self.identity:
            return block
        from scipy.signal import lfilter

        if self.zi is None:
            self.zi = np.zeros((2, block.shape[1]), dtype=np.float64)
        out, self.zi = lfilter(self.b, self.a, block, axis=0, zi=self.zi)
        return out


class _Gain:
    def __init__(self, op: dict, rate: int) -> None:
        self.gain = db_to_gain(_f(op, "db", 0.0))

    def reset(self) -> None:
        pass

    def __call__(self, block: np.ndarray) -> np.ndarray:
        return block if abs(self.gain - 1.0) < 1e-9 else block * self.gain


class _Compressor:
    """Feed-forward RMS compressor with one-pole attack/release envelope,
    gain computed per sub-block of ~1 ms so a 40 ms frame still has a
    shaped response instead of one step."""

    SUB = 48

    def __init__(self, op: dict, rate: int) -> None:
        self.threshold = _f(op, "threshold_db", -18.0)
        self.ratio = max(1.0, _f(op, "ratio", 3.0))
        attack = max(0.1, _f(op, "attack_ms", 10.0)) / 1000.0
        release = max(1.0, _f(op, "release_ms", 120.0)) / 1000.0
        sub_seconds = self.SUB / rate
        self.a_att = math.exp(-sub_seconds / attack)
        self.a_rel = math.exp(-sub_seconds / release)
        self.makeup = db_to_gain(_f(op, "makeup_db", 0.0))
        self.env_db = -120.0

    def reset(self) -> None:
        self.env_db = -120.0

    def __call__(self, block: np.ndarray) -> np.ndarray:
        n = block.shape[0]
        out = np.empty_like(block)
        for i in range(0, n, self.SUB):
            piece = block[i:i + self.SUB]
            rms = float(np.sqrt(np.mean(piece.astype(np.float64) ** 2)))
            level_db = 20.0 * math.log10(rms) if rms > 1e-9 else -120.0
            coef = self.a_att if level_db > self.env_db else self.a_rel
            self.env_db = coef * self.env_db + (1.0 - coef) * level_db
            over = self.env_db - self.threshold
            reduction = over - over / self.ratio if over > 0.0 else 0.0
            out[i:i + self.SUB] = piece * (db_to_gain(-reduction)
                                           * self.makeup)
        return out


class _Loudness:
    """Slow automatic gain towards a target RMS level (a practical stand-in
    for LUFS normalisation, which needs the whole programme up front).
    Rises slowly, falls fast, never more than ``max_gain_db`` of boost."""

    def __init__(self, op: dict, rate: int) -> None:
        self.target = _f(op, "target_db", -16.0)
        self.max_gain = _f(op, "max_gain_db", 12.0)
        self.gain_db = 0.0
        self.measured: list[float] = []

    def reset(self) -> None:
        self.gain_db = 0.0
        self.measured = []

    def __call__(self, block: np.ndarray) -> np.ndarray:
        rms = float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))
        if rms > 1e-5:                       # ignore silence
            level_db = 20.0 * math.log10(rms)
            self.measured.append(level_db)
            if len(self.measured) > 75:      # ~3 s window at 25 fps
                self.measured.pop(0)
            window = sum(self.measured) / len(self.measured)
            wanted = max(-60.0, min(self.max_gain, self.target - window))
            step = 0.3 if wanted > self.gain_db else 1.5   # dB per block
            if wanted > self.gain_db:
                self.gain_db = min(wanted, self.gain_db + step)
            else:
                self.gain_db = max(wanted, self.gain_db - step)
        return block * db_to_gain(self.gain_db)


class _Limiter:
    """Hard ceiling with a tanh soft knee just below it."""

    def __init__(self, op: dict, rate: int) -> None:
        self.ceiling = db_to_gain(_f(op, "ceiling_db", -1.0))

    def reset(self) -> None:
        pass

    def __call__(self, block: np.ndarray) -> np.ndarray:
        peak = float(np.max(np.abs(block))) if block.size else 0.0
        if peak <= self.ceiling:
            return block
        return np.tanh(block / self.ceiling) * self.ceiling


_FACTORIES = {
    "gain": _Gain, "compressor": _Compressor, "loudness": _Loudness,
    "limiter": _Limiter,
}


class AudioChain:
    """The ops of one recipe, armed for one sample rate, with state."""

    def __init__(self, ops: list[dict[str, Any]], rate: int) -> None:
        self.rate = int(rate)
        self.stages = []
        for op in ops or []:
            if not isinstance(op, dict):
                continue
            name = str(op.get("op") or "")
            if name in ("lowpass", "highpass", "low_shelf", "high_shelf",
                        "peak"):
                self.stages.append(_Biquad(name, op, self.rate))
            elif name in _FACTORIES:
                self.stages.append(_FACTORIES[name](op, self.rate))
            elif name not in _warned:
                _warned.add(name)
                log.warning("Unknown audio op %r skipped", name)
        self._next_position: int | None = None

    def reset(self) -> None:
        for stage in self.stages:
            stage.reset()

    def process(self, block: np.ndarray, position: int | None = None
                ) -> np.ndarray:
        """Run one block. ``position`` (track frame) detects seeks: a
        block that does not follow the previous one resets the state."""
        if position is not None:
            if self._next_position is not None \
                    and position != self._next_position:
                self.reset()
            self._next_position = position + 1
        if not self.stages or block is None or block.size == 0:
            return block
        out = block.astype(np.float64, copy=False)
        for stage in self.stages:
            out = stage(out)
        return np.clip(out, -1.0, 1.0).astype(np.float32)
