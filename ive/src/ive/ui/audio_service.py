"""QML bridge over the audio-effect catalogue.

The catalogue (ive/audio/library.py) is plain Python; this thin QObject
hands QML the sections and effects - names already localised - and the
starred ids, mirroring the colour service so the panels read alike.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ive.audio.library import list_effects, reload, sections

log = logging.getLogger(__name__)

__all__ = ["AudioLibraryService"]


class AudioLibraryService(QObject):
    """What the Audio panel binds to."""

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
        if key == "audio.favorites":
            self.favoritesChanged.emit()

    def _language(self) -> str:
        try:
            return str(self._translations.language) if self._translations else "en"
        except Exception:
            return "en"

    @Property("QVariantList", notify=favoritesChanged)
    def favorites(self) -> list[str]:
        """Starred effect ids, in the order they were starred."""
        if self._settings is None:
            return []
        try:
            return [str(v) for v in (self._settings.get("audio.favorites") or [])]
        except Exception:
            return []

    @Property("QVariantList", notify=changed)
    def sections(self) -> list[dict[str, Any]]:
        out = []
        for section in sections():
            inside = [e for e in list_effects() if e["section"] == section]
            out.append({"id": section, "count": len(inside)})
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

    @Slot(str, result=str)
    def effect_name(self, effect_id: str) -> str:
        from ive.audio.library import effect_by_id

        effect = effect_by_id(str(effect_id))
        if effect is None:
            return str(effect_id)
        lang = self._language()
        return (effect["names"].get(lang) or effect["names"].get("en")
                or effect["id"])

    @Slot()
    def refresh(self) -> None:
        """Rescan the folders - a pack came or went, or a file was dropped."""
        reload()
        self.changed.emit()
