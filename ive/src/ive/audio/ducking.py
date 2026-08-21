"""Ducking: the music bed dips while the cut is talking.

Two parts, kept apart on purpose:

* ``GuideLevel`` listens to the GUIDE - the A/V playlists' audio at a
  track position - and answers "how loud is the cut here?" in dBFS, one
  number per frame, cached so every ducked bed at that frame asks once.
  It is the "simple" detector of docs/AUDIO.md: energy, not speech. The
  "smart" mode (a voice-activity model telling words from a car horn)
  plugs in HERE when its model ships; until then asking for it logs once
  and uses the energy detector, so a project made on a machine with the
  model still plays everywhere.
* ``Ducker`` is the filter on a music entry: a one-pole envelope with a
  fast attack (the bed must get out of the way on the first word) and a
  slow release (it must not pump between words), applied as a gain to
  the bed. Gain is constant within a frame - a step every 40 ms at 25
  fps, below what a release of half a second lets anyone hear.
"""

from __future__ import annotations

import logging
import math
from typing import Callable

import numpy as np

from ive.engine.filters import Filter
from ive.engine.frame import Frame

log = logging.getLogger(__name__)

__all__ = ["GuideLevel", "Ducker", "MODES"]

MODES = ("simple", "smart")
_warned_smart = False


class GuideLevel:
    """The cut's loudness per track frame, from its playlists' audio."""

    def __init__(self, producers: list, mode: str = "simple") -> None:
        global _warned_smart
        self.producers = list(producers)
        self.mode = mode if mode in MODES else "simple"
        if self.mode == "smart" and not _warned_smart:
            _warned_smart = True
            log.warning("Ducking 'smart' mode asked for but no voice model "
                        "is installed; using the level detector")
        self._cache: dict[int, float] = {}

    def level_db(self, position: int) -> float:
        """RMS of the guide at ``position``, in dBFS (-120 = silence)."""
        cached = self._cache.get(position)
        if cached is not None:
            return cached
        total = 0.0
        count = 0
        for producer in self.producers:
            try:
                frame = producer.frame_at(position)
            except Exception:
                log.exception("Guide producer failed at %d", position)
                continue
            if frame is None:
                continue
            audio = frame.audio()
            if audio is None or not len(audio):
                continue
            total += float(np.sum(audio.astype(np.float64) ** 2))
            count += audio.size
        level = (20.0 * math.log10(math.sqrt(total / count))
                 if count and total > 0.0 else -120.0)
        if len(self._cache) > 256:
            self._cache.clear()
        self._cache[position] = level
        return level


class Ducker(Filter):
    """Dips a bed by up to ``depth_db`` while the guide is above
    ``threshold_db``; attack and release in TRACK frames."""

    def __init__(self, guide: GuideLevel | Callable[[int], float],
                 depth_db: float = 12.0, *, threshold_db: float = -42.0,
                 attack_frames: float = 2.0,
                 release_frames: float = 15.0) -> None:
        self.guide = guide
        self.depth_db = max(0.0, float(depth_db))
        self.threshold_db = float(threshold_db)
        self.a_att = math.exp(-1.0 / max(0.5, float(attack_frames)))
        self.a_rel = math.exp(-1.0 / max(0.5, float(release_frames)))
        self._reduction = 0.0      # dB currently taken off the bed
        self._next_position: int | None = None

    def reduction_at(self, position: int) -> float:
        """Advance the envelope to ``position`` and return the dB dip."""
        if self._next_position is not None \
                and position != self._next_position:
            self._reduction = 0.0          # a seek: start from rest
        self._next_position = position + 1
        level = (self.guide.level_db(position)
                 if hasattr(self.guide, "level_db") else self.guide(position))
        target = self.depth_db if level > self.threshold_db else 0.0
        coef = self.a_att if target > self._reduction else self.a_rel
        self._reduction = coef * self._reduction + (1.0 - coef) * target
        return self._reduction

    def process(self, frame: Frame) -> Frame:
        if self.depth_db <= 0.0:
            return frame
        position = frame.position

        def ducked():
            audio = frame.audio()
            if audio is None:
                return None
            dip = self.reduction_at(position)
            if dip < 0.05:
                return audio
            return audio * np.float32(10.0 ** (-dip / 20.0))

        return self._wrap(frame, audio_fn=ducked)
