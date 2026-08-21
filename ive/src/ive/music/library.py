"""The music catalogue: tracks from installed packs and the user's folder.

Two sources, one list:

* **Packs** bring ``music/tracks.json`` (a list of track documents) plus
  the files they reference, relative to the ``music/`` folder. That is
  how the official "Business" pack ships (build_scripts/make_music_pack.py)
  and how anyone can share a collection.
* **The user's folder** ``user_data/music/``: any audio file dropped there
  is a track (category "mine"), titled by its file name. No manifest,
  no registration - the folder IS the library.

Shape of a track document::

    {
      "schema_version": 1,
      "id": "km_inspired",
      "title": {"en": "Inspired"},
      "artist": "Kevin MacLeod",
      "category": "business",            # free text; "mine" is reserved
      "tags": ["uplifting"],
      "bpm": 120,
      "vocals": false,
      "duration": 187.5,                 # seconds, 0 = probe it
      "license": "CC-BY-4.0",            # informative, never enforced
      "attribution": "...credit line...",
      "file": "files/km_inspired.mp3"
    }

Licence fields are information for the user (docs/CONTENT_PACKS.md §8):
the app offers the credit text at export, it never blocks anything.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ive.utils.paths import get_data_path

log = logging.getLogger(__name__)

__all__ = ["list_tracks", "track_by_id", "categories", "reload",
           "AUDIO_SUFFIXES", "USER_CATEGORY"]

AUDIO_SUFFIXES = {".mp3", ".ogg", ".opus", ".wav", ".flac", ".m4a", ".aac"}
USER_CATEGORY = "mine"

_cache: list[dict[str, Any]] | None = None


def _coerce(entry: Any, folder: Path, origin: str, source: str
            ) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    track_id = str(entry.get("id") or "").strip()
    file = str(entry.get("file") or "").strip()
    if not track_id or not file:
        log.warning("Skipping a track without id/file in %s", origin)
        return None
    path = (folder / file).resolve()
    if not path.is_file():
        log.warning("Track %r points at a missing file %s", track_id, path)
        return None
    titles = entry.get("title")
    if not isinstance(titles, dict):
        titles = {"en": str(titles) if titles else track_id}
    try:
        duration = max(0.0, float(entry.get("duration") or 0.0))
        bpm = int(entry.get("bpm") or 0)
    except (TypeError, ValueError):
        duration, bpm = 0.0, 0
    return {
        "id": track_id,
        "titles": {str(k): str(v) for k, v in titles.items()},
        "artist": str(entry.get("artist") or ""),
        "category": str(entry.get("category") or "music").strip().lower()
                    or "music",
        "tags": [str(t) for t in (entry.get("tags") or [])
                 if isinstance(t, (str, int, float))],
        "bpm": bpm,
        "vocals": bool(entry.get("vocals", False)),
        "duration": duration,
        "license": str(entry.get("license") or ""),
        "license_url": str(entry.get("license_url") or ""),
        "source_url": str(entry.get("source_url") or ""),
        "attribution": str(entry.get("attribution") or ""),
        "attribution_required": bool(entry.get("attribution_required",
                                               False)),
        "path": str(path),
        "source": source,
    }


def _scan_pack_folder(folder: Path) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Unreadable track list %s: %s", path.name, exc)
            continue
        entries = raw if isinstance(raw, list) else [raw]
        for entry in entries:
            track = _coerce(entry, folder, path.name, "pack")
            if track is not None:
                found.append(track)
    return found


def _scan_user_folder(folder: Path) -> list[dict[str, Any]]:
    """Bare audio files: the file name is the title, the folder the
    library. A sidecar ``<name>.json`` next to a file may add fields."""
    found: list[dict[str, Any]] = []
    if not folder.is_dir():
        return found
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        entry: dict[str, Any] = {"id": f"mine_{path.stem}",
                                 "title": path.stem, "file": path.name,
                                 "category": USER_CATEGORY}
        sidecar = path.with_suffix(".json")
        if sidecar.is_file():
            try:
                extra = json.loads(sidecar.read_text(encoding="utf-8-sig"))
                if isinstance(extra, dict):
                    extra.pop("file", None)
                    extra.pop("id", None)
                    entry.update(extra)
                    entry["category"] = USER_CATEGORY
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("Unreadable sidecar %s: %s", sidecar.name, exc)
        track = _coerce(entry, folder, path.name, "user")
        if track is not None:
            found.append(track)
    return found


def _load() -> list[dict[str, Any]]:
    from ive.packs.pack import pack_content_dirs

    tracks: list[dict[str, Any]] = []
    seen: set[str] = set()
    scanned = _scan_user_folder(get_data_path("music"))
    for folder in pack_content_dirs("music"):
        scanned += _scan_pack_folder(folder)
    for track in scanned:
        if track["id"] in seen:
            log.warning("Duplicate track id %r ignored", track["id"])
            continue
        seen.add(track["id"])
        tracks.append(track)
    log.info("Music tracks loaded: %d (%d from packs)", len(tracks),
             sum(1 for t in tracks if t["source"] == "pack"))
    return tracks


def list_tracks() -> list[dict[str, Any]]:
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache


def reload() -> None:
    global _cache
    _cache = None


def track_by_id(track_id: str) -> dict[str, Any] | None:
    return next((t for t in list_tracks() if t["id"] == track_id), None)


def categories() -> list[str]:
    """Pack categories alphabetically, the user's own folder last."""
    present = {t["category"] for t in list_tracks()}
    out = sorted(c for c in present if c != USER_CATEGORY)
    if USER_CATEGORY in present:
        out.append(USER_CATEGORY)
    return out
