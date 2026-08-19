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

    @Slot(str, result=str)
    def preview(self, transition_id: str) -> str:
        """The transition caught mid-blend, as a cached PNG file URL.

        Rendered by the REAL engine blender over two solid plates
        (~1 ms at card size), synchronously, once per transition.
        """
        import hashlib

        import numpy as np
        from PySide6.QtGui import QImage

        from ive.utils.paths import get_data_path

        transition = transition_by_id(str(transition_id))
        if transition is None:
            return ""
        folder = get_data_path("cache/transition_previews")
        folder.mkdir(parents=True, exist_ok=True)
        stamp = repr(sorted(transition["op"].items()))
        digest = hashlib.md5(
            f"{transition_id}|{stamp}|v1".encode("utf-8")).hexdigest()[:20]
        target = folder / f"{digest}.png"
        if not target.is_file():
            from ive.transitions.loader import attach_blenders

            spans = attach_blenders([{
                "start": 0.0, "end": 1.0,
                "payload": dict(transition["op"]),
                "easing": transition["easing"],
            }])
            if not spans:
                return ""
            height, width = 90, 160
            base = np.zeros((height, width, 3), dtype=np.uint8)
            base[...] = (56, 96, 214)                      # the outgoing blue
            top = np.zeros((height, width, 3), dtype=np.uint8)
            top[...] = (235, 148, 56)                      # the incoming orange
            blended = spans[0]["blender"].blend(base, top, 0.55)
            blended = np.ascontiguousarray(blended)
            image = QImage(blended.tobytes(), width, height, width * 3,
                           QImage.Format.Format_RGB888)
            tmp = target.with_suffix(".tmp.png")
            if not image.save(str(tmp), "PNG"):
                return ""
            tmp.replace(target)
        return QUrl.fromLocalFile(str(target)).toString()

    @Slot(str, result=float)
    def default_duration(self, transition_id: str) -> float:
        transition = transition_by_id(str(transition_id))
        return float(transition["duration"]) if transition else 0.5

    @Slot()
    def refresh(self) -> None:
        """Rescan the folders - the user just dropped a file in."""
        reload()
        self.changed.emit()
