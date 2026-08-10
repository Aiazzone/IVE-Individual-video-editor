"""QML bridge over the colour-effect catalogue.

The catalogue itself (ive/color/library.py) is plain Python; this thin
QObject gives QML the sections and effects with names already localised,
and re-resolves them when the interface language flips.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ive.color.library import list_effects, reload, sections

log = logging.getLogger(__name__)

__all__ = ["ColorLibraryService"]


class ColorLibraryService(QObject):
    """What the Color panel binds to."""

    changed = Signal()

    favoritesChanged = Signal()

    def __init__(self, translations=None, settings=None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._translations = translations
        self._settings = settings
        if translations is not None:
            translations.languageChanged.connect(self.changed)
        if settings is not None:
            settings.changed.connect(self._on_setting_changed)

    def _on_setting_changed(self, key: str, _value) -> None:
        if key == "color.favorites":
            self.favoritesChanged.emit()

    @Property("QVariantList", notify=favoritesChanged)
    def favorites(self) -> list[str]:
        """Starred effect ids, in the order they were starred."""
        if self._settings is None:
            return []
        try:
            return [str(v) for v in (self._settings.get("color.favorites") or [])]
        except Exception:
            return []

    def _language(self) -> str:
        try:
            return str(self._translations.language) if self._translations else "en"
        except Exception:
            return "en"

    @Property("QVariantList", notify=changed)
    def sections(self) -> list[dict[str, Any]]:
        out = []
        for section in sections():
            inside = [e for e in list_effects() if e["section"] == section]
            out.append({
                "id": section,
                "count": len(inside),
                # The first effect stands in as the section's cover.
                "coverEffect": inside[0]["id"] if inside else "",
            })
        return out

    @Property("QVariantList", notify=changed)
    def effects(self) -> list[dict[str, Any]]:
        lang = self._language()
        return [
            {
                "id": effect["id"],
                "section": effect["section"],
                "name": effect["names"].get(lang)
                        or effect["names"].get("en") or effect["id"],
                "builtin": effect["builtin"],
            }
            for effect in list_effects()
        ]

    @Slot()
    def refresh(self) -> None:
        """Rescan the folders - after the user dropped in a new effect."""
        reload()
        self.changed.emit()
