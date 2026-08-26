"""The QML item that shows the decoded frame - as a GPU texture.

The frame goes straight onto the scene graph: ``updatePaintNode``
uploads the QImage as a texture and draws two nodes, a background
rectangle and the fitted picture. The previous ``QQuickPaintedItem``
rasterised every frame through QPainter into an FBO first - one full
extra copy plus a raster pass, per frame, on the render thread's time.

Threading, because it is the whole point of the scene-graph API:
``set_image`` runs on the GUI thread and only stores the image and
calls ``update()``; ``updatePaintNode`` runs on the RENDER thread while
the GUI thread is blocked by the sync phase - the one moment both may
touch the same state, which is why the image can be read there without
a lock. Textures are created and destroyed only inside
``updatePaintNode`` (``QSGSimpleTextureNode`` owns them and frees the
old one when a new one is set).

The frame is always fitted, never stretched: an editor that lies about
framing is useless. "cover" exists for the shell's shaped viewport -
see ``fillMode`` below. The QML API is unchanged from the painted
implementation, exactly as docs/ROADMAP.md promised.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Property, QObject, QRectF, Signal, Slot
from PySide6.QtGui import QColor, QImage
from PySide6.QtQuick import (QQuickItem, QSGNode, QSGSimpleTextureNode,
                             QSGTexture)

log = logging.getLogger(__name__)

__all__ = ["PreviewItem"]


class PreviewItem(QQuickItem):
    """Displays one frame at a time, fitted inside its own bounds."""

    frameChanged = Signal()
    sourceSizeChanged = Signal()
    sourceChanged = Signal()
    fillModeChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._image = QImage()
        self._image_serial = 0
        self._uploaded_serial = -1
        self._source = None
        self._background = QColor("#000000")
        self._fill_mode = "fit"
        self.setFlag(QQuickItem.Flag.ItemHasContents, True)

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
        self._image_serial += 1
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
        self._image_serial += 1
        self.frameChanged.emit()
        self.sourceSizeChanged.emit()
        self.update()

    # ── the scene graph ───────────────────────────────────────────────

    def _target_rect(self, bounds: QRectF) -> QRectF:
        pick = max if self._fill_mode == "cover" else min
        scale = pick(
            bounds.width() / self._image.width(),
            bounds.height() / self._image.height(),
        )
        width = self._image.width() * scale
        height = self._image.height() * scale
        return QRectF(
            bounds.x() + (bounds.width() - width) / 2,
            bounds.y() + (bounds.height() - height) / 2,
            width,
            height,
        )

    def updatePaintNode(self, node, _data):  # noqa: N802 - Qt naming
        from PySide6.QtQuick import QSGSimpleRectNode

        bounds = QRectF(0, 0, self.width(), self.height())
        window = self.window()
        if bounds.isEmpty() or window is None:
            return node

        background = node
        if background is None or not isinstance(background,
                                                QSGSimpleRectNode):
            background = QSGSimpleRectNode()
        background.setRect(bounds)
        background.setColor(self._background)

        picture = (background.firstChild()
                   if background.childCount() else None)
        if self._image.isNull():
            if picture is not None:
                background.removeAllChildNodes()
            return background

        if picture is None:
            picture = QSGSimpleTextureNode()
            # The node deletes its texture when a new one lands and when
            # the node itself goes - the whole lifecycle stays on the
            # render thread, where it must be.
            picture.setOwnsTexture(True)
            picture.setFiltering(QSGTexture.Filtering.Linear)
            background.appendChildNode(picture)
        # Hold Python references: the C++ side owns the nodes, but a
        # garbage-collected WRAPPER of a Python-created node would take
        # the C++ object with it mid-scene.
        self._nodes = (background, picture)
        if self._uploaded_serial != self._image_serial:
            picture.setTexture(window.createTextureFromImage(self._image))
            self._uploaded_serial = self._image_serial
        picture.setRect(self._target_rect(bounds))
        background.markDirty(QSGNode.DirtyState.DirtyGeometry)
        return background
