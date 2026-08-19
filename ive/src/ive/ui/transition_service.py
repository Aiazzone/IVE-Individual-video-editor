"""QML bridge over the transition catalogue.

The catalogue itself (ive/transitions/library.py) is plain Python; this
thin QObject hands QML the families and the transitions inside each -
names already localised - plus a PREVIEW image per transition: the real
engine blender caught mid-blend between a blue and an orange plate, so
the card shows exactly what the cut will do.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from ive.transitions.library import (list_transitions, reload, sections,
                                     transition_by_id)

log = logging.getLogger(__name__)

__all__ = ["TransitionLibraryService"]


class TransitionLibraryService(QObject):
    """What the Transitions panel binds to."""

    changed = Signal()

    def __init__(self, translations=None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._translations = translations
        if translations is not None:
            translations.languageChanged.connect(self.changed)

    def _language(self) -> str:
        try:
            return str(self._translations.language) if self._translations else "en"
        except Exception:
            return "en"

    @Property("QVariantList", notify=changed)
    def sections(self) -> list[dict[str, Any]]:
        out = []
        for section in sections():
            inside = [t for t in list_transitions()
                      if t["section"] == section]
            out.append({"id": section, "count": len(inside)})
        return out

    @Slot(str, result="QVariantList")
    def transitions(self, section: str) -> list[dict[str, Any]]:
        """The transitions of one family, localised."""
        lang = self._language()
        out = []
        for transition in list_transitions():
            if transition["section"] != section:
                continue
            out.append({
                "id": transition["id"],
                "name": transition["names"].get(lang)
                        or transition["names"].get("en") or transition["id"],
                "duration": transition["duration"],
                "builtin": transition["builtin"],
            })
        return out

    #: Card preview size; the strip holds this many animation frames
    #: plus short holds on either end so the loop reads as A -> B.
    _PREVIEW_W, _PREVIEW_H = 160, 90
    _STRIP_STEPS = 12
    _plates_cache = None

    @classmethod
    def _plates(cls):
        """The two demo scenes every preview blends between: a blue
        plate marked A (the outgoing clip) and an orange one marked B
        (the incoming) - light, legible imagery whose only job is to
        make the MOTION of the transition obvious."""
        if cls._plates_cache is not None:
            return cls._plates_cache

        import numpy as np
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import (QColor, QFont, QImage, QLinearGradient,
                                   QPainter)

        def plate(top_colour, bottom_colour, letter):
            image = QImage(cls._PREVIEW_W, cls._PREVIEW_H,
                           QImage.Format.Format_RGB888)
            painter = QPainter(image)
            gradient = QLinearGradient(0, 0, 0, cls._PREVIEW_H)
            gradient.setColorAt(0.0, QColor(top_colour))
            gradient.setColorAt(1.0, QColor(bottom_colour))
            painter.fillRect(0, 0, cls._PREVIEW_W, cls._PREVIEW_H, gradient)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            font = QFont()
            font.setPixelSize(int(cls._PREVIEW_H * 0.62))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255, 230))
            painter.drawText(QRectF(0, 0, cls._PREVIEW_W, cls._PREVIEW_H),
                             Qt.AlignmentFlag.AlignCenter, letter)
            painter.end()
            width, height = image.width(), image.height()
            data = image.constBits().tobytes()
            return np.frombuffer(data, dtype=np.uint8).reshape(
                height, image.bytesPerLine() // 3, 3)[:, :width].copy()

        cls._plates_cache = (plate("#2C4A8F", "#4A6FD0", "A"),
                             plate("#B4652A", "#E8964A", "B"))
        return cls._plates_cache

    def _blender_for(self, transition):
        from ive.transitions.loader import attach_blenders

        spans = attach_blenders([{
            "start": 0.0, "end": 1.0,
            "payload": dict(transition["op"]),
            "easing": transition["easing"],
        }])
        return spans[0]["blender"] if spans else None

    def _cache_target(self, transition, suffix: str):
        import hashlib

        from ive.utils.paths import get_data_path

        folder = get_data_path("cache/transition_previews")
        folder.mkdir(parents=True, exist_ok=True)
        stamp = repr(sorted(transition["op"].items()))
        digest = hashlib.md5(
            f"{transition['id']}|{stamp}|v2".encode("utf-8")).hexdigest()[:20]
        return folder / f"{digest}{suffix}.png"

    @Slot(str, result=str)
    def preview(self, transition_id: str) -> str:
        """The transition caught mid-blend, as a cached PNG file URL.

        Rendered by the REAL engine blender over the A/B plates
        (~1 ms at card size), synchronously, once per transition.
        """
        import numpy as np
        from PySide6.QtGui import QImage

        transition = transition_by_id(str(transition_id))
        if transition is None:
            return ""
        target = self._cache_target(transition, "")
        if not target.is_file():
            blender = self._blender_for(transition)
            if blender is None:
                return ""
            base, top = self._plates()
            blended = np.ascontiguousarray(blender.blend(base, top, 0.55))
            image = QImage(blended.tobytes(), self._PREVIEW_W,
                           self._PREVIEW_H, self._PREVIEW_W * 3,
                           QImage.Format.Format_RGB888)
            tmp = target.with_suffix(".tmp.png")
            if not image.save(str(tmp), "PNG"):
                return ""
            tmp.replace(target)
        return QUrl.fromLocalFile(str(target)).toString()

    @Slot(str, result="QVariantMap")
    def preview_strip(self, transition_id: str) -> dict:
        """The whole transition as a FILM STRIP for the hover preview.

        One PNG holding the frames side by side - A held briefly, the
        blend at its own easing, B held briefly - rendered by the real
        engine blender and cached. AnimatedPreview.qml slides it under
        a clipped viewport, so playing it costs a texture offset."""
        import numpy as np
        from PySide6.QtGui import QImage

        from ive.engine.transitions import ease

        transition = transition_by_id(str(transition_id))
        if transition is None:
            return {}
        target = self._cache_target(transition, "_strip")
        steps = ([0.0] * 2
                 + [i / (self._STRIP_STEPS - 1)
                    for i in range(self._STRIP_STEPS)]
                 + [1.0] * 2)
        if not target.is_file():
            blender = self._blender_for(transition)
            if blender is None:
                return {}
            base, top = self._plates()
            frames = [np.ascontiguousarray(
                blender.blend(base, top, ease(t, transition["easing"])))
                for t in steps]
            strip = np.ascontiguousarray(np.hstack(frames))
            image = QImage(strip.tobytes(), strip.shape[1], strip.shape[0],
                           strip.shape[1] * 3, QImage.Format.Format_RGB888)
            tmp = target.with_suffix(".tmp.png")
            if not image.save(str(tmp), "PNG"):
                return {}
            tmp.replace(target)
        return {"url": QUrl.fromLocalFile(str(target)).toString(),
                "frames": len(steps),
                "width": self._PREVIEW_W, "height": self._PREVIEW_H}

    @Slot(str, result=float)
    def default_duration(self, transition_id: str) -> float:
        transition = transition_by_id(str(transition_id))
        return float(transition["duration"]) if transition else 0.5

    @Slot()
    def refresh(self) -> None:
        """Rescan the folders - the user just dropped a file in."""
        reload()
        self.changed.emit()
