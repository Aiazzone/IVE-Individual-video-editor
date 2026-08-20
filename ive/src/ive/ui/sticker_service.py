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
        if key == "sticker.favorites":
            self.favoritesChanged.emit()

    @Property("QVariantList", notify=favoritesChanged)
    def favorites(self) -> list[str]:
        """Starred sticker ids, in the order they were starred."""
        if self._settings is None:
            return []
        try:
            return [str(v)
                    for v in (self._settings.get("sticker.favorites") or [])]
        except Exception:
            return []

    @Slot(result="QVariantList")
    def favorite_stickers(self) -> list[dict[str, Any]]:
        """The starred stickers, localised, in starred order - both kinds
        mixed, which is the point of the tab. A starred id whose files
        are gone is simply skipped."""
        from ive.stickers.library import sticker_by_id

        lang = self._language()
        out = []
        for sticker_id in self.favorites:
            sticker = sticker_by_id(sticker_id)
            if sticker is None:
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

    @Slot(str, result=str)
    def preview(self, sticker_id: str) -> str:
        """A still preview of an ANIMATED sticker, as a file URL.

        One rlottie render of a mid-animation frame (~1 ms), cached as a
        PNG on disk. Synchronous on purpose: it is cheaper than a
        thumbnail worker round-trip and runs once per sticker.
        """
        import hashlib
        import os

        from PySide6.QtGui import QImage

        from ive.stickers.library import sticker_by_id
        from ive.utils.paths import get_data_path

        sticker = sticker_by_id(str(sticker_id))
        if sticker is None or sticker["kind"] != "animated":
            return ""
        path = sticker["path"]
        try:
            mtime = int(os.path.getmtime(path))
        except OSError:
            return ""
        folder = get_data_path("cache/sticker_previews")
        folder.mkdir(parents=True, exist_ok=True)
        digest = hashlib.md5(f"{path}|{mtime}".encode("utf-8")).hexdigest()[:20]
        target = folder / f"{digest}.png"
        if not target.is_file():
            from ive.stickers.raster import lottie_info, render_lottie_frame

            info = lottie_info(path)
            if info is None:
                return ""
            # A third of the way in: past any empty intro frame.
            rgba = render_lottie_frame(path, 160, info["total"] // 3)
            if rgba is None:
                return ""
            h, w = rgba.shape[:2]
            image = QImage(rgba.tobytes(), w, h, w * 4,
                           QImage.Format.Format_RGBA8888)
            tmp = target.with_suffix(".tmp.png")
            if not image.save(str(tmp), "PNG"):
                return ""
            tmp.replace(target)
        return QUrl.fromLocalFile(str(target)).toString()

    @Slot(str, result="QVariantMap")
    def preview_strip(self, sticker_id: str) -> dict:
        """An ANIMATED sticker as a film strip for the hover preview.

        Twelve frames spread across the whole animation, each rendered
        by rlottie and centred on a square transparent canvas (so the
        strip stretches into a square card without distortion), cached
        as one PNG. AnimatedPreview.qml plays it on hover."""
        import hashlib
        import os

        import numpy as np
        from PySide6.QtGui import QImage

        from ive.stickers.library import sticker_by_id
        from ive.stickers.raster import lottie_info, render_lottie_frame
        from ive.utils.paths import get_data_path

        sticker = sticker_by_id(str(sticker_id))
        if sticker is None or sticker["kind"] != "animated":
            return {}
        path = sticker["path"]
        try:
            mtime = int(os.path.getmtime(path))
        except OSError:
            return {}
        info = lottie_info(path)
        if info is None:
            return {}
        folder = get_data_path("cache/sticker_previews")
        folder.mkdir(parents=True, exist_ok=True)
        digest = hashlib.md5(
            f"{path}|{mtime}|strip1".encode("utf-8")).hexdigest()[:20]
        target = folder / f"{digest}.png"
        side = 120
        count = min(12, max(2, int(info["total"])))
        if not target.is_file():
            aspect = max(0.05, float(info["aspect"]))
            height = side if aspect <= 1.0 else max(2, round(side / aspect))
            cells = []
            for index in range(count):
                frame_index = int(index * info["total"] / count)
                rgba = render_lottie_frame(path, height, frame_index)
                cell = np.zeros((side, side, 4), dtype=np.uint8)
                if rgba is not None:
                    h, w = rgba.shape[:2]
                    if w > side:
                        x0 = (w - side) // 2
                        rgba, w = rgba[:, x0:x0 + side], side
                    top = (side - h) // 2
                    left = (side - w) // 2
                    cell[top:top + h, left:left + w] = rgba
                cells.append(cell)
            strip = np.ascontiguousarray(np.hstack(cells))
            image = QImage(strip.tobytes(), strip.shape[1], strip.shape[0],
                           strip.shape[1] * 4, QImage.Format.Format_RGBA8888)
            tmp = target.with_suffix(".tmp.png")
            if not image.save(str(tmp), "PNG"):
                return {}
            tmp.replace(target)
        return {"url": QUrl.fromLocalFile(str(target)).toString(),
                "frames": count, "width": side, "height": side}

    @Slot(str, result=str)
    def still_url(self, sticker_id: str) -> str:
        """A resting image for any sticker: the file itself for a
        static one, the cached rlottie frame for an animated one."""
        from ive.stickers.library import sticker_by_id

        sticker = sticker_by_id(str(sticker_id))
        if sticker is None:
            return ""
        if sticker["kind"] == "animated":
            return self.preview(sticker_id)
        return QUrl.fromLocalFile(sticker["path"]).toString()

    @Slot(result="QVariantList")
    def motion_presets(self) -> list[dict[str, Any]]:
        """The motion catalogue, localised, grouped by kind order."""
        from ive.ui.motion_service import localized_presets

        return localized_presets(self._language())

    @Slot(str, str, result="QVariantMap")
    def motion_strip(self, sticker_id: str, motion_id: str) -> dict:
        """THIS sticker animated by THAT preset, as a hover film strip.

        Fourteen frames across the preset's duration (one period for a
        loop), each the sticker's own still transformed by the recipe -
        so the card previews exactly what the video will do. Cached as
        one PNG per (sticker, preset)."""
        import os

        from ive.motion.library import recipe_for
        from ive.stickers.library import sticker_by_id
        from ive.stickers.raster import (lottie_info, render_lottie_frame,
                                         render_static)
        from ive.ui.motion_service import cached_strip

        sticker = sticker_by_id(str(sticker_id))
        recipe = recipe_for(str(motion_id))
        if sticker is None or recipe is None:
            return {}
        path = sticker["path"]
        try:
            mtime = int(os.path.getmtime(path))
        except OSError:
            return {}

        def still(height_px, rotation):
            if sticker["kind"] == "animated":
                info = lottie_info(path)
                if info is None:
                    return None
                frame = render_lottie_frame(path, height_px,
                                            info["total"] // 3)
                if frame is not None and abs(rotation) > 0.01:
                    from ive.stickers.raster import _rotate_rgba

                    frame = _rotate_rgba(frame, rotation)
                return frame
            return render_static(path, height_px, rotation)

        return cached_strip(f"{path}|{mtime}|{motion_id}|mstrip1",
                            still, recipe)

    @Slot(str, result=float)
    def aspect(self, sticker_id: str) -> float:
        """Width / height of a sticker's graphic, for the preview handles."""
        from ive.stickers.library import sticker_by_id
        from ive.stickers.raster import sprite_aspect

        sticker = sticker_by_id(str(sticker_id))
        if sticker is None:
            return 1.0
        try:
            return float(sprite_aspect(sticker["path"], sticker["kind"]))
        except Exception:
            log.exception("Could not measure sticker %s", sticker_id)
            return 1.0

    @Slot()
    def refresh(self) -> None:
        """Rescan the folders - the user just dropped a file in."""
        reload()
        self.changed.emit()
