"""QML bridge over the music catalogue, with a preview player.

The catalogue (ive/music/library.py) is plain Python; this QObject hands
QML the categories and tracks - titles localised - the starred ids, and
owns the PREVIEW: one QMediaPlayer that plays a track on its own, without
touching the timeline or the project. Starting a preview pauses the
transport (two sounds at once help nobody); placing or selecting stops
it.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from ive.music.library import (USER_CATEGORY, categories, list_tracks,
                               reload, track_by_id)

log = logging.getLogger(__name__)

__all__ = ["MusicService"]


class MusicService(QObject):
    """What the Music tab of the Audio panel binds to."""

    changed = Signal()
    favoritesChanged = Signal()
    previewChanged = Signal()

    def __init__(self, translations=None, settings=None, playback=None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._translations = translations
        self._settings = settings
        self._playback = playback
        self._player = None
        self._output = None
        self._previewing = ""
        if translations is not None:
            translations.languageChanged.connect(self.changed)
        if settings is not None:
            settings.changed.connect(self._on_setting_changed)

    def _on_setting_changed(self, key: str, _value) -> None:
        if key == "music.favorites":
            self.favoritesChanged.emit()

    def _language(self) -> str:
        try:
            return str(self._translations.language) if self._translations else "en"
        except Exception:
            return "en"

    def _title(self, track: dict[str, Any]) -> str:
        lang = self._language()
        return (track["titles"].get(lang) or track["titles"].get("en")
                or next(iter(track["titles"].values()), track["id"]))

    # ── catalogue ─────────────────────────────────────────────────────

    @Property("QVariantList", notify=changed)
    def categories(self) -> list[dict[str, Any]]:
        out = []
        for category in categories():
            count = sum(1 for t in list_tracks() if t["category"] == category)
            out.append({"id": category, "count": count,
                        "mine": category == USER_CATEGORY})
        return out

    @Slot(str, result="QVariantList")
    def tracks(self, category: str) -> list[dict[str, Any]]:
        """The tracks of one category ("" = every track), localised."""
        out = []
        for track in list_tracks():
            if category and track["category"] != category:
                continue
            out.append(self._as_map(track))
        return out

    def _as_map(self, track: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": track["id"],
            "title": self._title(track),
            "artist": track["artist"],
            "category": track["category"],
            "tags": list(track["tags"]),
            "bpm": track["bpm"],
            "vocals": track["vocals"],
            "duration": track["duration"],
            "license": track["license"],
            "attribution": track["attribution"],
            "path": track["path"],
            "source": track["source"],
        }

    @Property("QVariantList", notify=favoritesChanged)
    def favorites(self) -> list[str]:
        if self._settings is None:
            return []
        try:
            return [str(v) for v in (self._settings.get("music.favorites") or [])]
        except Exception:
            return []

    @Slot(result="QVariantList")
    def favorite_tracks(self) -> list[dict[str, Any]]:
        out = []
        for track_id in self.favorites:
            track = track_by_id(track_id)
            if track is not None:
                out.append(self._as_map(track))
        return out

    # ── preview ───────────────────────────────────────────────────────

    @Property(str, notify=previewChanged)
    def previewing(self) -> str:
        """The id of the track playing in preview, "" when silent."""
        return self._previewing

    def _ensure_player(self) -> bool:
        if self._player is not None:
            return True
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        except ImportError:
            log.warning("QtMultimedia unavailable: no music preview")
            return False
        self._output = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._output)
        self._player.mediaStatusChanged.connect(self._on_status)
        self._player.errorOccurred.connect(
            lambda code, text: log.warning("Music preview error: %s", text))
        return True

    def _on_status(self, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer

        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._previewing:
            self._previewing = ""
            self.previewChanged.emit()

    @Slot(str, result=bool)
    def preview(self, track_id: str) -> bool:
        """Play a track on its own; the same id again stops it."""
        track = track_by_id(str(track_id))
        if track is None or not self._ensure_player():
            return False
        if self._previewing == track["id"]:
            self.stop()
            return True
        if self._playback is not None:
            try:
                if getattr(self._playback, "isPlaying", False):
                    self._playback.pause()
            except Exception:
                log.exception("Could not pause the transport for a preview")
        self._player.setSource(QUrl.fromLocalFile(track["path"]))
        self._player.play()
        self._previewing = track["id"]
        self.previewChanged.emit()
        log.info("Music preview: %s", track["id"])
        return True

    @Slot()
    def stop(self) -> None:
        if self._player is not None:
            self._player.stop()
            # Release the file: a pack being removed must not find its
            # track still open in the preview player.
            self._player.setSource(QUrl())
        if self._previewing:
            self._previewing = ""
            self.previewChanged.emit()

    @Slot()
    def refresh(self) -> None:
        """Rescan - a pack came or went, or a file landed in the folder."""
        self.stop()
        reload()
        self.changed.emit()
