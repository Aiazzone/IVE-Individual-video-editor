"""QML bridge over the sticker catalogue.

The catalogue itself (ive/stickers/library.py) is plain Python; this thin
QObject hands QML the two tabs (static / animated), the families of each,
and the stickers inside a family - names already localised, files as URLs
Qt's native image loader reads directly (SVG included, via the qtsvg
image plugin: no thumbnail worker is needed for vector stickers).
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from ive.stickers.library import list_stickers, reload, sections

log = logging.getLogger(__name__)

__all__ = ["StickerLibraryService"]


class StickerLibraryService(QObject):
    """What the Stickers panel binds to."""

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
    def staticSections(self) -> list[dict[str, Any]]:
        return self._sections("static")

    @Property("QVariantList", notify=changed)
    def animatedSections(self) -> list[dict[str, Any]]:
        return self._sections("animated")

    def _sections(self, kind: str) -> list[dict[str, Any]]:
        out = []
        for section in sections(kind):
            inside = [s for s in list_stickers()
                      if s["kind"] == kind and s["section"] == section]
            out.append({"id": section, "count": len(inside)})
        return out

    @Slot(str, str, result="QVariantList")
    def stickers(self, kind: str, section: str) -> list[dict[str, Any]]:
        """The stickers of one family, localised, files as URLs."""
        lang = self._language()
        out = []
        for sticker in list_stickers():
            if sticker["kind"] != kind or sticker["section"] != section:
                continue
            out.append({
                "id": sticker["id"],
                "name": sticker["names"].get(lang)
                        or sticker["names"].get("en") or sticker["id"],
                "kind": sticker["kind"],
                "fileUrl": QUrl.fromLocalFile(sticker["path"]).toString(),
                "builtin": sticker["builtin"],
            })
        return out

    @Slot()
    def refresh(self) -> None:
        """Rescan the folders - the user just dropped a file in."""
        reload()
        self.changed.emit()
