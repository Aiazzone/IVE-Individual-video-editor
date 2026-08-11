"""Waveform strips, generated as FILES by a worker thread.

Same shape as ThumbnailService, for the same reason: no Python may ever
run on Qt's image threads in this app (the pixmap-store mutex vs GIL
deadlock, see ive/ui/thumbnails.py). QML asks ``Waves.wave(path)``; if
the PNG exists its file URL comes back and Qt's NATIVE loader reads it;
otherwise "" comes back, a daemon worker decodes the audio and paints the
strip, and ``rev`` is bumped so the bindings re-ask.

The strip covers the WHOLE file once - white peaks on transparency, one
column per ~10 ms - and the timeline crops/stretches it per clip, so
trimming, splitting and zooming never re-decode anything.

Cache: ``user_data/cache/waveforms``, keyed on path and mtime.
"""

from __future__ import annotations

import hashlib
import logging
import os
import queue
import threading
from pathlib import Path

import numpy as np
from PySide6.QtCore import Property, QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QImage

log = logging.getLogger(__name__)

__all__ = ["WaveformService"]

#: Strip height in pixels; the timeline stretches it to the lane height.
_HEIGHT = 64
#: Bumped when the painted format changes, so old caches regenerate.
_FORMAT = "wf1"
#: A touch below full white: reads as texture, not as a hole in the clip.
_ALPHA = 235
#: Perceptual lift: quiet material stays visible without lying about
#: loud material. Pure linear made speech-level audio look near-empty.
_GAMMA = 0.7


class WaveformService(QObject):
    """What QML binds to for the audio strips on the timeline."""

    changed = Signal()
    _jobDone = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        from ive.utils.paths import get_data_path

        super().__init__(parent)
        self._dir = Path(get_data_path("cache/waveforms"))
        self._dir.mkdir(parents=True, exist_ok=True)
        self._rev = 0
        self._queued: set[str] = set()
        self._jobs: "queue.Queue[tuple[str, Path] | None]" = queue.Queue()
        self._jobDone.connect(self._bump, Qt.ConnectionType.QueuedConnection)
        self._worker = threading.Thread(target=self._run, daemon=True,
                                        name="waveforms")
        self._worker.start()

    # ── QML face ──────────────────────────────────────────────────────

    @Property(int, notify=changed)
    def rev(self) -> int:
        """Bumped when a strip lands; bindings read it to re-resolve."""
        return self._rev

    @Slot(str, result=str)
    def wave(self, path: str) -> str:
        """File URL of the file's waveform strip, or "" while it renders."""
        path = str(path or "")
        if not path:
            return ""
        target = self._target(path)
        if target is None:
            return ""
        if target.is_file():
            return QUrl.fromLocalFile(str(target)).toString()
        key = str(target)
        if key not in self._queued:
            self._queued.add(key)
            self._jobs.put((path, target))
        return ""

    # ── worker ────────────────────────────────────────────────────────

    def _bump(self) -> None:
        self._rev += 1
        self.changed.emit()

    def _target(self, path: str) -> Path | None:
        try:
            mtime = int(os.path.getmtime(path))
        except OSError:
            return None
        digest = hashlib.md5(
            f"{_FORMAT}|{path}|{mtime}".encode("utf-8")).hexdigest()[:20]
        return self._dir / f"{digest}.png"

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            path, target = job
            try:
                if not target.is_file():
                    self._generate(path, target)
            except Exception:
                log.exception("No waveform for %s", Path(path).name)
            finally:
                self._jobDone.emit()

    def _generate(self, path: str, target: Path) -> None:
        from ive.media.waveform import extract_peaks

        peaks = extract_peaks(path)
        if peaks is None or peaks.size == 0:
            # A file with no sound gets an EMPTY (fully transparent) strip:
            # caching the answer stops the timeline re-asking forever.
            peaks = np.zeros(64, dtype=np.float32)
        image = self._paint(peaks)
        tmp = target.with_suffix(".tmp.png")
        # Write-then-rename: a half-written PNG must never be servable.
        if image.save(str(tmp), "PNG"):
            tmp.replace(target)
            log.info("Waveform rendered for %s (%d columns)",
                     Path(path).name, peaks.size)

    @staticmethod
    def _paint(peaks: np.ndarray) -> QImage:
        """White symmetric peaks on transparency, one column per peak."""
        height, width = _HEIGHT, int(peaks.size)
        half = height / 2.0 - 1.0
        # A hairline at silence keeps the lane readable: the user sees
        # "this stretch is quiet", not "the waveform is missing".
        amp = np.maximum(np.power(peaks, _GAMMA) * half, 1.0)
        rows = np.abs(np.arange(height, dtype=np.float32)
                      - (height / 2.0 - 0.5))[:, None]          # (H, 1)
        mask = rows <= amp[None, :]                             # (H, W)
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        rgba[..., :3] = 255
        rgba[..., 3] = np.where(mask, _ALPHA, 0)
        image = QImage(rgba.tobytes(), width, height, width * 4,
                       QImage.Format.Format_RGBA8888)
        return image.copy()     # detach from the numpy buffer's lifetime

    def shutdown(self) -> None:
        self._jobs.put(None)
