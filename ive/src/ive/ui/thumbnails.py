"""Video thumbnails, generated as FILES by a worker thread.

This replaced a QQuickImageProvider, deliberately. A Python provider runs
on Qt's image-reader thread, which holds Qt's pixmap-store mutex while it
calls into Python - and Python needs the GIL. Whenever the GUI thread
entered QML machinery from Python (holding the GIL) and touched that same
mutex, the two threads deadlocked: GUI waiting for the mutex, reader
waiting for the GIL. With a ~1 s video decode inside the provider the
collision window was enormous, and it froze the shell repeatedly
(py-spy native stack: QQuickPixmap::load -> QBasicMutex::lockInternal).

So: no Python on Qt's image threads at all. QML asks
``Thumbs.thumb(path, effect)``; if the PNG exists its file URL comes back
and Qt's NATIVE loader reads it; if not, "" comes back and a daemon worker
generates it (one frame decode per video, one cheap graded variant per
effect), then bumps ``rev`` so the bindings re-ask.

The cache lives in ``user_data/cache/thumbnails`` and is keyed on path,
mtime and effect - editing the file invalidates its thumbs naturally.
"""

from __future__ import annotations

import hashlib
import logging
import os
import queue
import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QImage

log = logging.getLogger(__name__)

__all__ = ["ThumbnailService"]

#: Decoded size: small enough to be instant, big enough for a 2x panel card.
_WIDTH = 160
#: Where in the file the frame is taken: 10% in, capped at 3 seconds.
_PEEK_FRACTION = 0.1
_PEEK_MAX_SECONDS = 3.0


class ThumbnailService(QObject):
    """What QML binds to for every thumbnail in the interface."""

    changed = Signal()
    _jobDone = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        from ive.utils.paths import get_data_path

        super().__init__(parent)
        self._dir = Path(get_data_path("cache/thumbnails"))
        self._dir.mkdir(parents=True, exist_ok=True)
        self._rev = 0
        self._queued: set[str] = set()
        self._jobs: "queue.Queue[tuple[str, str, Path] | None]" = queue.Queue()
        #: Base frames by path, so ten graded variants cost ONE decode.
        self._frames: dict[str, object] = {}
        # Queued back to the GUI thread; the worker never touches QML state.
        self._jobDone.connect(self._bump, Qt.ConnectionType.QueuedConnection)
        self._worker = threading.Thread(target=self._run, daemon=True,
                                        name="thumbnails")
        self._worker.start()

    # ── QML face ──────────────────────────────────────────────────────

    @Property(int, notify=changed)
    def rev(self) -> int:
        """Bumped when a thumbnail lands; bindings read it to re-resolve."""
        return self._rev

    @Slot(str, result=str)
    @Slot(str, str, result=str)
    def thumb(self, path: str, effect: str = "") -> str:
        """File URL of the thumbnail, or "" while it is being generated."""
        path = str(path or "")
        if not path:
            return ""
        target = self._target(path, effect)
        if target is None:
            return ""
        if target.is_file():
            return QUrl.fromLocalFile(str(target)).toString()
        key = str(target)
        if key not in self._queued:
            self._queued.add(key)
            self._jobs.put((path, str(effect or ""), target))
        return ""

    # ── worker ────────────────────────────────────────────────────────

    def _bump(self) -> None:
        self._rev += 1
        self.changed.emit()

    def _target(self, path: str, effect: str) -> Path | None:
        try:
            mtime = int(os.path.getmtime(path))
        except OSError:
            return None
        digest = hashlib.md5(
            f"{path}|{mtime}|{effect}".encode("utf-8")).hexdigest()[:20]
        return self._dir / f"{digest}.png"

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            path, effect, target = job
            try:
                if not target.is_file():
                    self._generate(path, effect, target)
            except Exception:
                log.exception("No thumbnail for %s", Path(path).name)
            finally:
                self._jobDone.emit()

    def _generate(self, path: str, effect: str, target: Path) -> None:
        array = self._frames.get(path)
        if array is None:
            array = self._decode_array(path)
            if array is None:
                return
            self._frames[path] = array
        if effect:
            from ive.color.library import ops_for
            from ive.engine.filters import ColorGrade

            ops = ops_for(effect)
            if ops:
                array = ColorGrade(ops).apply(array)
        h, w = array.shape[:2]
        image = QImage(array.tobytes(), w, h, w * 3,
                       QImage.Format.Format_RGB888)
        tmp = target.with_suffix(".tmp.png")
        # Write-then-rename: a half-written PNG must never be servable.
        if image.save(str(tmp), "PNG"):
            tmp.replace(target)

    @staticmethod
    def _decode_array(path: str):
        """One small RGB frame from a little way into the file, or None."""
        from ive.media.decoder import VideoDecoder

        if not Path(path).is_file():
            return None
        decoder = None
        try:
            decoder = VideoDecoder(path)
            width, height = decoder.video.display_size
            if width and height:
                out_h = max(2, int(round(_WIDTH * height / width))) & ~1
                decoder.set_output_size(_WIDTH, out_h)
            seconds = min(_PEEK_MAX_SECONDS,
                          (decoder.frame_count / decoder.fps) * _PEEK_FRACTION
                          if decoder.fps else 0.0)
            index = int(seconds * decoder.fps) if decoder.fps else 0
            frame = decoder.frame_at(index) or decoder.frame_at(0)
            return frame.array.copy() if frame is not None else None
        except Exception:
            log.exception("Could not decode a thumbnail frame from %s",
                          Path(path).name)
            return None
        finally:
            if decoder is not None:
                try:
                    decoder.close()
                except Exception:
                    pass

    def shutdown(self) -> None:
        self._jobs.put(None)
