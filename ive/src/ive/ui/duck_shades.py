"""Ducking shades: WHERE the music dips, drawn on the clip.

Same shape as WaveformService (files from a worker thread, QML loads
them with Qt's native loader - no Python on Qt's image threads). QML
asks ``DuckShade.shade(clipId)``; if the strip exists its file URL comes
back, otherwise the worker computes it and ``rev`` bumps.

The strip is the DUCKER'S OWN envelope run offline: the guide level is
approximated from the A/V clips' cached peak strips (the same data the
timeline's waveforms use), fed to the same ``Ducker`` maths the engine
plays - threshold, attack and release included. Peaks overstate an RMS
detector slightly, so the shade may start a hair early; for a picture of
"the voice is here" that honesty trade is fine and costs no decoding.

Cache: ``user_data/cache/duckshades``, keyed on everything the envelope
depends on (the music span, its depth, and the guide clips' files and
placement) - an edit changes the key, so stale strips are simply never
asked for again; leftovers older than a week are swept at startup.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import Property, QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QImage

log = logging.getLogger(__name__)

__all__ = ["DuckShadeService"]

#: Envelope columns per second - one per waveform column.
_COLUMNS_PER_SECOND = 100
#: Strip height; the timeline stretches it to the lane height.
_HEIGHT = 16
#: Bumped when the painted format changes, so old caches regenerate.
_FORMAT = "ds1"
#: Full-depth ducking paints this alpha; lighter dips scale down.
_MAX_ALPHA = 150
#: Ducker times in engine track-frames (40 ms) converted to columns.
_ATTACK_COLUMNS = 2.0 * 4
_RELEASE_COLUMNS = 15.0 * 4
#: Strips older than this are swept at startup: their keys can never be
#: asked for again once the timeline moved on.
_SWEEP_SECONDS = 7 * 24 * 3600


class DuckShadeService(QObject):
    """What QML binds to for the ducking shade on Music-lane clips."""

    changed = Signal()
    _jobDone = Signal()

    def __init__(self, project, parent: QObject | None = None) -> None:
        from ive.utils.paths import get_data_path

        super().__init__(parent)
        self._project = project
        self._dir = Path(get_data_path("cache/duckshades"))
        self._dir.mkdir(parents=True, exist_ok=True)
        self._sweep()
        self._rev = 0
        self._queued: set[str] = set()
        self._jobs: "queue.Queue[tuple[dict, Path] | None]" = queue.Queue()
        self._jobDone.connect(self._bump, Qt.ConnectionType.QueuedConnection)
        if project is not None:
            # An edit changes the keys; the bindings must re-ask.
            project.timelineChanged.connect(self._bump)
        self._worker = threading.Thread(target=self._run, daemon=True,
                                        name="duckshades")
        self._worker.start()

    # ── QML face ──────────────────────────────────────────────────────

    @Property(int, notify=changed)
    def rev(self) -> int:
        return self._rev

    @Slot(str, result=str)
    def shade(self, clip_id: str) -> str:
        """File URL of the clip's ducking strip, or "" (not ducked, no
        guide audio, or still rendering)."""
        spec = self._spec(str(clip_id))
        if spec is None:
            return ""
        target = self._dir / f"{self._digest(spec)}.png"
        if target.is_file():
            return QUrl.fromLocalFile(str(target)).toString()
        key = str(target)
        if key not in self._queued:
            self._queued.add(key)
            self._jobs.put((spec, target))
        return ""

    # ── the job description ───────────────────────────────────────────

    def _spec(self, clip_id: str) -> dict[str, Any] | None:
        if self._project is None:
            return None
        clips = self._project.timelineClips
        clip = next((c for c in clips if c["id"] == clip_id), None)
        if clip is None or not clip.get("duck") \
                or float(clip.get("duckDb") or 0.0) <= 0.0:
            return None
        start, end = float(clip["start"]), float(clip["end"])
        guides = []
        for c in clips:
            if c["track"] != 0 or not c.get("hasAudio") \
                    or not c.get("audioEnabled") or c.get("muted"):
                continue
            if c["end"] <= start or c["start"] >= end or not c.get("path"):
                continue
            try:
                mtime = int(os.path.getmtime(c["path"]))
            except OSError:
                continue
            guides.append({
                "path": c["path"], "mtime": mtime,
                "start": float(c["start"]), "end": float(c["end"]),
                "sourceIn": float(c.get("sourceIn") or 0.0),
                "volume": float(c.get("volume", 1.0)),
                "mediaDuration": float(c.get("mediaDuration") or 0.0),
            })
        return {"start": start, "end": end,
                "depth": float(clip["duckDb"]), "guides": guides}

    @staticmethod
    def _digest(spec: dict[str, Any]) -> str:
        blob = json.dumps(spec, sort_keys=True).encode("utf-8")
        return hashlib.md5(f"{_FORMAT}|".encode() + blob).hexdigest()[:20]

    # ── worker ────────────────────────────────────────────────────────

    def _bump(self) -> None:
        self._rev += 1
        self.changed.emit()

    def _run(self) -> None:
        peaks_cache: dict[tuple[str, int], Any] = {}
        while True:
            job = self._jobs.get()
            if job is None:
                return
            spec, target = job
            try:
                if not target.is_file():
                    self._generate(spec, target, peaks_cache)
            except Exception:
                log.exception("No ducking shade for span %.2f-%.2f",
                              spec["start"], spec["end"])
            finally:
                self._jobDone.emit()

    def _generate(self, spec: dict[str, Any], target: Path,
                  peaks_cache: dict) -> None:
        from ive.audio.ducking import Ducker
        from ive.media.waveform import extract_peaks

        span = spec["end"] - spec["start"]
        width = int(min(8192, max(16, round(span * _COLUMNS_PER_SECOND))))
        guide_db = np.full(width, -120.0)
        for c in spec["guides"]:
            key = (c["path"], c["mtime"])
            if key not in peaks_cache:
                if len(peaks_cache) > 16:
                    peaks_cache.clear()
                peaks_cache[key] = extract_peaks(c["path"])
            peaks = peaks_cache[key]
            if peaks is None or not len(peaks):
                continue
            file_dur = c["mediaDuration"] or (c["end"] - c["start"])
            for i in range(width):
                t = spec["start"] + (i + 0.5) / _COLUMNS_PER_SECOND
                if not (c["start"] <= t < c["end"]):
                    continue
                pos = (t - c["start"] + c["sourceIn"]) / max(0.01, file_dur)
                amp = float(peaks[min(len(peaks) - 1,
                                      int(pos * len(peaks)))]) * c["volume"]
                if amp > 1e-6:
                    guide_db[i] = max(guide_db[i],
                                      20.0 * np.log10(amp))
        ducker = Ducker(lambda i: guide_db[i], spec["depth"],
                        attack_frames=_ATTACK_COLUMNS,
                        release_frames=_RELEASE_COLUMNS)
        fraction = np.array([ducker.reduction_at(i) for i in range(width)],
                            dtype=np.float32) / spec["depth"]
        rgba = np.zeros((_HEIGHT, width, 4), dtype=np.uint8)
        rgba[..., 3] = (np.clip(fraction, 0.0, 1.0)
                        * _MAX_ALPHA)[None, :].astype(np.uint8)
        image = QImage(rgba.tobytes(), width, _HEIGHT, width * 4,
                       QImage.Format.Format_RGBA8888).copy()
        tmp = target.with_suffix(".tmp.png")
        if image.save(str(tmp), "PNG"):
            tmp.replace(target)
            log.info("Ducking shade rendered (%d columns, max dip %.0f%%)",
                     width, float(fraction.max()) * 100)

    def _sweep(self) -> None:
        cutoff = time.time() - _SWEEP_SECONDS
        try:
            for old in self._dir.glob("*.png"):
                if old.stat().st_mtime < cutoff:
                    old.unlink(missing_ok=True)
        except OSError:
            pass

    def shutdown(self) -> None:
        self._jobs.put(None)
