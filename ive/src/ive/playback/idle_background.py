"""Looping background shown when no project is open.

Decoration, and treated as such - it must never cost the editor anything:

* it stops the moment a media file is opened, because from then on the user's
  own frame is the background;
* it stops when the window is not active, so a minimised IVE decodes nothing;
* the clip is bundled at 720p (see ``assets/backgrounds/SOURCES.md``), so the
  decode is a rounding error next to a 4K preview;
* if the file is missing or unreadable the app simply has a plain background.
  Nothing else depends on it.

It reuses the same reader as the preview: one decoding path, one set of bugs.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Property, QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QImage

from ive.media.reader import VideoReader
from ive.utils.paths import get_asset_path

log = logging.getLogger(__name__)

__all__ = ["IdleBackgroundService", "ASSET_NAME"]

ASSET_NAME = "backgrounds/idle_loop.mp4"


class IdleBackgroundService(QObject):
    """Plays a short clip on repeat behind the empty state."""

    frameImage = Signal(QImage)
    availabilityChanged = Signal()
    runningChanged = Signal()

    def __init__(self, settings=None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._reader: VideoReader | None = None
        self._path: str = ""
        self._available = False
        self._running = False
        self._frames = 0
        self._position = 0
        self._fps = 30.0
        #: Always advance ONE frame per tick. Skipping frames forces a seek
        #: per frame, which costs far more than the frames it saves - the loop
        #: stutters and the CPU load goes up, not down. To make it cheaper,
        #: ship a smaller clip; do not skip frames.
        self._decode_fps = 30.0
        #: Set by the app when a media file is open, or the window is hidden.
        self._suppressed = False

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.CoarseTimer)  # decoration: precision is pointless
        self._timer.timeout.connect(self._advance)

        self._load()

    # ── properties ────────────────────────────────────────────────────

    @Property(bool, notify=availabilityChanged)
    def available(self) -> bool:
        """True when the clip loaded and can be shown."""
        return self._available

    @Property(bool, notify=runningChanged)
    def running(self) -> bool:
        return self._running

    @Property(float, notify=availabilityChanged)
    def aspect(self) -> float:
        if self._reader is None or self._reader.info is None:
            return 16.0 / 9.0
        video = self._reader.info.primary_video
        if video is None:
            return 16.0 / 9.0
        width, height = video.display_size
        return width / height if height else 16.0 / 9.0

    # ── control ───────────────────────────────────────────────────────

    @Slot(bool)
    def set_suppressed(self, suppressed: bool) -> None:
        """Stop decoding while a project is open or the window is not visible."""
        if suppressed == self._suppressed:
            return
        self._suppressed = suppressed
        self._sync()

    @Slot()
    def refresh(self) -> None:
        """Re-read the enabled setting and start or stop accordingly."""
        self._sync()

    def _enabled(self) -> bool:
        if self._settings is None:
            return True
        return bool(self._settings.get("appearance.idle_background"))

    def _sync(self) -> None:
        should_run = self._available and self._enabled() and not self._suppressed
        if should_run == self._running:
            return
        self._running = should_run
        if should_run:
            self._timer.start(max(16, int(1000 / max(1.0, self._fps))))
            log.info("Idle background running")
        else:
            self._timer.stop()
            log.info("Idle background stopped")
        self.runningChanged.emit()

    # ── internals ─────────────────────────────────────────────────────

    def _load(self) -> None:
        path = get_asset_path(ASSET_NAME)
        if not path.is_file():
            log.info("No idle background clip at %s; using a plain background", path)
            return

        self._reader = VideoReader(self)
        self._reader.frameReady.connect(self._on_frame)
        self._reader.failed.connect(self._on_failed)
        if not self._reader.open(path):
            self._reader = None
            return
        self._path = str(path)

        info = self._reader.info
        video = info.primary_video
        self._fps = float(video.fps) or 30.0
        self._decode_fps = self._fps
        self._frames = video.frames or max(1, int(round(info.duration * self._fps)))
        self._available = True
        log.info("Idle background: %s, %d frames @ %.2f fps", path.name, self._frames, self._fps)
        self.availabilityChanged.emit()
        self._sync()

    def _advance(self) -> None:
        if self._reader is None:
            return
        # One frame at a time, so the decoder stays on its sequential path.
        # Wrapping to zero is the only seek in the whole loop.
        self._position = (self._position + 1) % max(1, self._frames)
        # VideoReader serves several sources now, so the path is
        # part of every request.
        self._reader.request_frame(self._path, self._position)

    def _on_frame(self, _path: str, _index: int, _time: float,
                  image: QImage) -> None:
        self.frameImage.emit(image)

    def _on_failed(self, message: str) -> None:
        log.warning("Idle background failed, disabling it: %s", message)
        self._available = False
        self._timer.stop()
        self._running = False
        self.availabilityChanged.emit()
        self.runningChanged.emit()

    def shutdown(self) -> None:
        self._timer.stop()
        if self._reader is not None:
            self._reader.shutdown()
            self._reader = None
