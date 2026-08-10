"""The QML item that shows the decoded frame.

Implemented with ``QQuickPaintedItem`` for now: correct, simple, and fast
enough at 1080p. When the render graph lands it is replaced by a texture-based
item that uploads straight to the GPU - the QML API stays the same, so nothing
in the shell has to change.

The frame is always fitted, never cropped and never stretched: an editor that
lies about framing is useless. Letterbox bars are painted in the project's
canvas colour.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Property, QObject, QRectF, Signal, Slot
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtQuick import QQuickPaintedItem

log = logging.getLogger(__name__)

__all__ = ["PreviewItem"]


class PreviewItem(QQuickPaintedItem):
    """Displays one frame at a time, fitted inside its own bounds."""

    frameChanged = Signal()
    sourceSizeChanged = Signal()
    sourceChanged = Signal()
    fillModeChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._image = QImage()
        self._source = None
        self._background = QColor("#000000")
        self._fill_mode = "fit"
        self.setAntialiasing(True)
        # The frame changes rarely relative to the compositor; repainting only
        # when it does keeps the item off the per-frame budget.
        self.setRenderTarget(QQuickPaintedItem.RenderTarget.FramebufferObject)

    # ── QML API ───────────────────────────────────────────────────────

    @Property(bool, notify=frameChanged)
    def hasFrame(self) -> bool:
        return not self._image.isNull()

    @Property(int, notify=sourceSizeChanged)
    def sourceWidth(self) -> int:
        return self._image.width()

    @Property(int, notify=sourceSizeChanged)
    def sourceHeight(self) -> int:
        return self._image.height()

    @Property(float, notify=sourceSizeChanged)
    def sourceAspect(self) -> float:
        if self._image.isNull() or self._image.height() == 0:
            return 16.0 / 9.0
        return self._image.width() / self._image.height()

    def _get_fill_mode(self) -> str:
        return self._fill_mode

    def _set_fill_mode(self, mode: str) -> None:
        """``"fit"`` shows the whole frame, ``"cover"`` fills and crops.

        The shell's preview uses "cover" WITH an item shaped by
        ``Playback.viewAspect``: when the two ratios match (explicit canvas)
        nothing is cropped, and on "auto" the crop removes exactly the bars
        the compositor baked around the current clip - never the picture.
        Cropping actual content would be lying about framing; see the
        viewAspect docstring in transport.py before changing this.
        """
        mode = "cover" if str(mode) == "cover" else "fit"
        if mode == self._fill_mode:
            return
        self._fill_mode = mode
        self.fillModeChanged.emit()
        self.update()

    fillMode = Property(str, _get_fill_mode, _set_fill_mode, notify=fillModeChanged)

    @Slot(QColor)
    def setBackground(self, color: QColor) -> None:
        self._background = QColor(color)
        self.update()

    def _get_source(self):
        return self._source

    def _set_source(self, service) -> None:
        """Bind to a playback service: ``PreviewItem { source: Playback }``.

        Wiring the signal here rather than fishing the item out of the QML tree
        from Python keeps the dependency where it belongs - QML says what it
        wants to show, Python does not need to know the tree shape.
        """
        if service is self._source:
            return
        if self._source is not None:
            try:
                self._source.frameImage.disconnect(self.set_image)
            except (RuntimeError, TypeError):
                pass
        self._source = service
        if service is not None:
            service.frameImage.connect(self.set_image)
        self.sourceChanged.emit()

    source = Property(QObject, _get_source, _set_source, notify=sourceChanged)

    # ── Python API ────────────────────────────────────────────────────

    def set_image(self, image: QImage) -> None:
        """Show a new frame. Safe to call from the GUI thread only."""
        changed_size = (
            image.width() != self._image.width() or image.height() != self._image.height()
        )
        was_empty = self._image.isNull()
        self._image = image
        if changed_size:
            self.sourceSizeChanged.emit()
        if was_empty != image.isNull():
            self.frameChanged.emit()
        self.update()

    @Slot()
    def clear(self) -> None:
        if self._image.isNull():
            return
        self._image = QImage()
        self.frameChanged.emit()
        self.sourceSizeChanged.emit()
        self.update()

    # ── painting ──────────────────────────────────────────────────────

    def paint(self, painter: QPainter) -> None:
        bounds = QRectF(0, 0, self.width(), self.height())
        painter.fillRect(bounds, self._background)
        if self._image.isNull() or bounds.isEmpty():
            return

        pick = max if self._fill_mode == "cover" else min
        scale = pick(
            bounds.width() / self._image.width(),
            bounds.height() / self._image.height(),
        )
        width = self._image.width() * scale
        height = self._image.height() * scale
        target = QRectF(
            bounds.x() + (bounds.width() - width) / 2,
            bounds.y() + (bounds.height() - height) / 2,
            width,
            height,
        )

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(target, self._image)
