"""QML bridge over the motion presets.

The catalogue (ive/motion/library.py) is plain Python; this QObject hands
QML the localised list and the hover film strips of a TITLE moved by a
preset - the text counterpart of ``Stickers.motion_strip``. Both go
through ``cached_strip``: one PNG per (overlay, preset) on disk, composed
by ``ive.motion.preview`` so stickers and titles look the same in their
cards.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from ive.motion.library import list_presets, reload, sections
from ive.motion.preview import STRIP_FRAMES, STRIP_SIDE, compose_strip

log = logging.getLogger(__name__)

__all__ = ["MotionService", "cached_strip", "localized_presets"]

#: Titles in the cards are drawn at this reference size before the preset
#: scales them; long words just get smaller, they never spill the cell.
_TEXT_STRIP_HEIGHT = 0.32


def localized_presets(lang: str) -> list[dict[str, Any]]:
    """The catalogue in kind order, names in ``lang`` (English fallback)."""
    out = []
    for kind in sections():
        for preset in list_presets():
            if preset["kind"] != kind:
                continue
            out.append({
                "id": preset["id"],
                "name": preset["names"].get(lang)
                        or preset["names"].get("en") or preset["id"],
                "kind": preset["kind"],
                "builtin": preset["builtin"],
            })
    return out


def cached_strip(key: str, still: Callable, recipe: dict[str, Any]) -> dict:
    """Compose (once) and return the strip descriptor QML's
    AnimatedPreview expects: ``{url, frames, width, height}``.

    ``key`` must change whenever the still or the recipe does - the
    caller knows what the still depends on (file + mtime, or the words
    and style of a title)."""
    from PySide6.QtGui import QImage

    from ive.utils.paths import get_data_path

    folder = get_data_path("cache/motion_previews")
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:20]
    target = folder / f"{digest}.png"
    if not target.is_file():
        strip = compose_strip(still, recipe)
        if strip is None:
            return {}
        image = QImage(strip.tobytes(), strip.shape[1], strip.shape[0],
                       strip.shape[1] * 4, QImage.Format.Format_RGBA8888)
        tmp = target.with_suffix(".tmp.png")
        if not image.save(str(tmp), "PNG"):
            return {}
        tmp.replace(target)
    return {"url": QUrl.fromLocalFile(str(target)).toString(),
            "frames": STRIP_FRAMES, "width": STRIP_SIDE,
            "height": STRIP_SIDE}


class MotionService(QObject):
    """What the Text panel's Animation section (and anyone else) binds to."""

    changed = Signal()

    def __init__(self, translations=None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._translations = translations
        if translations is not None and hasattr(translations, "languageChanged"):
            translations.languageChanged.connect(self.changed)

    def _language(self) -> str:
        try:
            return str(self._translations.language) if self._translations else "en"
        except Exception:
            return "en"

    @Property("QVariantList", notify=changed)
    def presets(self) -> list[dict[str, Any]]:
        """The motion catalogue, localised, grouped by kind order."""
        return localized_presets(self._language())

    @Slot(str, str, str, str, bool, bool, result=str)
    def text_still_url(self, text: str, font: str, color: str, outline: str,
                       bold: bool, italic: bool) -> str:
        """A resting raster of the title, for the cards' still state."""
        from PySide6.QtGui import QImage

        from ive.text.raster import render_text
        from ive.utils.paths import get_data_path

        key = f"{text}|{font}|{color}|{outline}|{bold}|{italic}|tstill1"
        folder = get_data_path("cache/motion_previews")
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (hashlib.md5(key.encode("utf-8")).hexdigest()[:20]
                           + ".png")
        if not target.is_file():
            rgba = render_text(str(text), 64, font=str(font), color=str(color),
                               outline=str(outline), bold=bool(bold),
                               italic=bool(italic))
            if rgba is None:
                return ""
            image = QImage(rgba.tobytes(), rgba.shape[1], rgba.shape[0],
                           rgba.shape[1] * 4, QImage.Format.Format_RGBA8888)
            tmp = target.with_suffix(".tmp.png")
            if not image.save(str(tmp), "PNG"):
                return ""
            tmp.replace(target)
        return QUrl.fromLocalFile(str(target)).toString()

    @Slot(str, str, str, str, bool, bool, str, result="QVariantMap")
    def text_strip(self, text: str, font: str, color: str, outline: str,
                   bold: bool, italic: bool, motion_id: str) -> dict:
        """THIS title animated by THAT preset, as a hover film strip."""
        from ive.motion.library import recipe_for
        from ive.text.raster import render_text

        recipe = recipe_for(str(motion_id))
        if recipe is None or not str(text).strip():
            return {}

        def still(height_px, rotation):
            # The cell's rest height suits a square sticker; a title is a
            # wide block, so it is drawn shorter to keep its words inside.
            return render_text(str(text),
                               max(2, int(height_px * _TEXT_STRIP_HEIGHT
                                          / 0.55)),
                               font=str(font), color=str(color),
                               outline=str(outline), bold=bool(bold),
                               italic=bool(italic), rotation=rotation)

        key = (f"{text}|{font}|{color}|{outline}|{bold}|{italic}"
               f"|{motion_id}|tstrip1")
        return cached_strip(key, still, recipe)

    @Slot()
    def refresh(self) -> None:
        """Rescan the folders - a pack just came or went."""
        reload()
        self.changed.emit()
