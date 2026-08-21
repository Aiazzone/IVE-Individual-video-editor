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

from PySide6.QtCore import Property, QObject, QThread, Signal, Slot

from ive.packs import official
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
    #: The official catalogue's state changed (download progress, landing).
    officialChanged = Signal()
    #: (pack_id, reason) when a download did not end in an install.
    downloadFailed = Signal(str, str)
    _startDownload = Signal(str)

    def __init__(self, translations=None, colorfx=None, stickers=None,
                 transitions=None, parent: QObject | None = None, *,
                 motion=None, export=None, audiofx=None,
                 music=None) -> None:
        super().__init__(parent)
        self._translations = translations
        self._colorfx = colorfx
        self._stickers = stickers
        self._transitions = transitions
        self._motion = motion
        self._export = export
        self._audiofx = audiofx
        self._music = music
        self._pending: dict[str, Any] = {}
        # Official packs: one worker thread, one download at a time, the
        # rest wait in a queue. State per pack id: idle | queued |
        # downloading | installed | error.
        self._states: dict[str, str] = {}
        self._progress: dict[str, float] = {}
        self._queue: list[str] = []
        self._active: str = ""
        self._cancel = False
        self._thread: QThread | None = None
        self._worker: _DownloadWorker | None = None

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
                        self._motion, self._export, self._audiofx,
                        self._music):
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
                "audioEffects": counts.get("audio_effects", 0),
                "music": counts.get("music", 0),
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

    # ── official packs ────────────────────────────────────────────────

    @Property("QVariantList", notify=officialChanged)
    def official(self) -> list[dict[str, Any]]:
        """The catalogue with, per pack, whether it is installed and
        what its download is doing."""
        installed = {pack["id"] for pack in installed_packs()}
        lang = self._language()
        out = []
        for entry in official.load_catalog():
            is_installed = entry["id"] in installed
            state = self._states.get(entry["id"], "idle")
            if is_installed and state not in ("downloading", "queued"):
                state = "installed"
            out.append({
                "id": entry["id"],
                "name": entry["names"].get(lang) or entry["names"].get("en")
                        or entry["id"],
                "description": self._description_text(entry["descriptions"]),
                "kind": entry["kind"],
                "version": entry["version"],
                "size": entry["size"],
                "sizeMb": round(entry["size"] / 1024 / 1024),
                "license": entry["license"],
                "author": entry["author"],
                "installed": is_installed,
                "state": state,
                "progress": self._progress.get(entry["id"], 0.0),
            })
        return out

    @Property(bool, notify=officialChanged)
    def downloading(self) -> bool:
        return bool(self._active or self._queue)

    @Slot(str, result=bool)
    def download(self, pack_id: str) -> bool:
        """Queue an official pack; the worker fetches, verifies, installs."""
        pack_id = str(pack_id)
        if official.catalog_entry(pack_id) is None:
            log.warning("No official pack %r", pack_id)
            return False
        if pack_id in {p["id"] for p in installed_packs()}:
            return False
        if pack_id == self._active or pack_id in self._queue:
            return True
        self._states[pack_id] = "queued"
        self._progress[pack_id] = 0.0
        self._queue.append(pack_id)
        self.officialChanged.emit()
        self._pump()
        return True

    @Slot("QVariantList", result=int)
    def download_many(self, pack_ids: list) -> int:
        return sum(1 for pack_id in (pack_ids or []) if self.download(str(pack_id)))

    @Slot()
    def cancel_downloads(self) -> None:
        """Drop the queue and stop the active download."""
        for pack_id in self._queue:
            self._states[pack_id] = "idle"
        self._queue.clear()
        if self._active:
            self._cancel = True
        self.officialChanged.emit()

    def _ensure_worker(self) -> None:
        if self._thread is not None:
            return
        self._thread = QThread()
        self._thread.setObjectName("pack-downloads")
        self._worker = _DownloadWorker(lambda: self._cancel)
        self._worker.moveToThread(self._thread)
        self._startDownload.connect(self._worker.fetch)
        self._worker.progressed.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def _pump(self) -> None:
        if self._active or not self._queue:
            return
        self._ensure_worker()
        self._active = self._queue.pop(0)
        self._cancel = False
        self._states[self._active] = "downloading"
        self.officialChanged.emit()
        log.info("Official pack download starts: %s", self._active)
        self._startDownload.emit(self._active)

    def _on_progress(self, pack_id: str, fraction: float) -> None:
        self._progress[pack_id] = fraction
        self.officialChanged.emit()

    def _on_finished(self, pack_id: str) -> None:
        self._states[pack_id] = "installed"
        self._progress[pack_id] = 1.0
        self._active = ""
        self._refresh_catalogues()
        self.officialChanged.emit()
        self._pump()

    def _on_failed(self, pack_id: str, reason: str) -> None:
        self._states[pack_id] = "idle" if reason == "cancelled" else "error"
        self._active = ""
        self.officialChanged.emit()
        if reason != "cancelled":
            self.downloadFailed.emit(pack_id, reason)
        self._pump()

    def shutdown(self) -> None:
        self.cancel_downloads()
        if self._thread is not None:
            self._thread.quit()
            if not self._thread.wait(5000):
                log.warning("Pack download thread did not stop in time")
                self._thread.terminate()
                self._thread.wait(1000)
            self._thread = None
            self._worker = None

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
                                export_preset_ids=ids("export_presets"),
                                audio_effect_ids=ids("audio_effects"),
                                track_ids=ids("music"))
        except (ValueError, OSError) as exc:
            log.exception("Pack export failed")
            self.error.emit(str(exc))
            return False
        self.created.emit(report["path"])
        return True


class _DownloadWorker(QObject):
    """Lives on the download thread: fetch -> verify -> install."""

    progressed = Signal(str, float)
    finished = Signal(str)
    failed = Signal(str, str)

    def __init__(self, cancelled) -> None:
        super().__init__()
        self._cancelled = cancelled

    @Slot(str)
    def fetch(self, pack_id: str) -> None:
        entry = official.catalog_entry(pack_id)
        if entry is None:
            self.failed.emit(pack_id, "not_found")
            return
        last = [0.0]

        def progress(done: int, total: int) -> None:
            if total <= 0:
                return
            fraction = min(1.0, done / total)
            if fraction - last[0] >= 0.01 or fraction >= 1.0:
                last[0] = fraction
                self.progressed.emit(pack_id, fraction)

        try:
            official.fetch_pack(entry, progress=progress,
                                cancelled=self._cancelled)
        except official.DownloadError as exc:
            log.warning("Official pack %s not installed: %s", pack_id,
                        exc.reason)
            self.failed.emit(pack_id, exc.reason)
            return
        except Exception:
            log.exception("Official pack %s: unexpected failure", pack_id)
            self.failed.emit(pack_id, "network")
            return
        self.finished.emit(pack_id)
