"""QML bridge over the content packs.

The pack machinery itself (ive/packs/pack.py) is plain Python; this
thin QObject hands QML the installed packs, builds a pack from the
panel's selection, and owns the INSTALL HANDSHAKE: a dropped (or
picked) ``.ivepack`` becomes ``pending`` - the confirmation card the
user sees before anything lands on disk - and only confirm_install()
unpacks it. After every install or removal the three catalogue
services refresh, so the panels gain (or lose) the content at once.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ive.packs.pack import (build_pack, install_pack, installed_packs,
                            preview_pack, remove_pack)
from ive.utils.paths import local_path_from_url

log = logging.getLogger(__name__)

__all__ = ["PackService"]


class PackService(QObject):
    """What the Packs panel (and the drop overlay) binds to."""

    changed = Signal()
    pendingChanged = Signal()
    #: (path) after a successful export - the panel shows where it went.
    created = Signal(str)
    error = Signal(str)

    def __init__(self, translations=None, colorfx=None, stickers=None,
                 transitions=None, parent: QObject | None = None, *,
                 motion=None, export=None) -> None:
        super().__init__(parent)
        self._translations = translations
        self._colorfx = colorfx
        self._stickers = stickers
        self._transitions = transitions
        self._motion = motion
        self._export = export
        self._pending: dict[str, Any] = {}

    def _language(self) -> str:
        try:
            return str(self._translations.language) if self._translations else "en"
        except Exception:
            return "en"

    def _description_text(self, value: Any) -> str:
        if isinstance(value, dict):
            lang = self._language()
            return str(value.get(lang) or value.get("en")
                       or next(iter(value.values()), ""))
        return str(value or "")

    def _refresh_catalogues(self) -> None:
        """Installed content must appear (or vanish) everywhere at once."""
        for service in (self._colorfx, self._stickers, self._transitions,
                        self._motion, self._export):
            if service is not None and hasattr(service, "refresh"):
                try:
                    service.refresh()
                except Exception:
                    log.exception("Catalogue refresh failed")
        self.changed.emit()

    # ── installed packs ───────────────────────────────────────────────

    @Property("QVariantList", notify=changed)
    def installed(self) -> list[dict[str, Any]]:
        out = []
        for pack in installed_packs():
            counts = pack["counts"]
            out.append({
                "id": pack["id"],
                "name": pack["name"],
                "author": pack["author"],
                "version": pack["version"],
                "description": self._description_text(pack["description"]),
                "colors": counts["color_effects"],
                "transitions": counts["transitions"],
                "stickers": counts["stickers"],
                "motion": counts.get("motion", 0),
                "exportPresets": counts.get("export_presets", 0),
            })
        return out

    @Slot(str, result=bool)
    def remove(self, pack_id: str) -> bool:
        if not remove_pack(pack_id):
            return False
        self._refresh_catalogues()
        return True

    # ── the install handshake ─────────────────────────────────────────

    @Property("QVariantMap", notify=pendingChanged)
    def pending(self) -> dict[str, Any]:
        """The pack awaiting the user's confirmation; empty when none."""
        return self._pending

    @Slot(str, result=bool)
    def request_install(self, url_or_path: str) -> bool:
        """Preview a pack file and put it up for confirmation."""
        path = local_path_from_url(str(url_or_path))
        preview = preview_pack(path)
        if not preview.get("ok"):
            log.warning("Not a usable pack: %s (%s)", path,
                        preview.get("error"))
            self.error.emit(str(preview.get("error") or "not_a_pack"))
            return False
        preview["description"] = self._description_text(
            preview.get("description"))
        self._pending = preview
        self.pendingChanged.emit()
        return True

    @Slot(result=bool)
    def confirm_install(self) -> bool:
        if not self._pending:
            return False
        result = install_pack(self._pending["path"])
        self._pending = {}
        self.pendingChanged.emit()
        if not result.get("ok"):
            self.error.emit(str(result.get("error") or "install_failed"))
            return False
        self._refresh_catalogues()
        return True

    @Slot()
    def cancel_install(self) -> None:
        if self._pending:
            self._pending = {}
            self.pendingChanged.emit()

    # ── creating ──────────────────────────────────────────────────────

    @Slot(str, str, str, "QVariantMap", str, result=bool)
    def create(self, name: str, author: str, description: str,
               selection: dict, destination: str) -> bool:
        """Build a ``.ivepack`` from the panel's selection.

        ``selection`` holds id lists per category: ``colors``,
        ``transitions``, ``stickers``, ``motion``, ``export_presets`` -
        a map, so a new
        category is a new key, not a new positional argument."""
        path = local_path_from_url(str(destination))
        selection = dict(selection or {})

        def ids(key: str) -> list[str]:
            return [str(v) for v in (selection.get(key) or [])]

        try:
            report = build_pack(path, name=name, author=author,
                                description=description,
                                color_ids=ids("colors"),
                                transition_ids=ids("transitions"),
                                sticker_ids=ids("stickers"),
                                motion_ids=ids("motion"),
                                export_preset_ids=ids("export_presets"))
        except (ValueError, OSError) as exc:
            log.exception("Pack export failed")
            self.error.emit(str(exc))
            return False
        self.created.emit(report["path"])
        return True
