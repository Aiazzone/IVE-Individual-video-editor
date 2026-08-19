"""The sticker catalogue.

Same philosophy as the colour effects (docs/CONTENT_PACKS.md): a sticker
is DATA - a manifest entry plus a graphic file - never code, so
installing one is safe and sending it to another user is just sending
files. Factory stickers ship in ``ive/config/defaults/stickers/``
(manifest ``*.json`` at the top, graphics in subfolders); the user's own
live in ``user_data/stickers/`` with the same shape.

Shape of one entry (a manifest file holds one or a list)::

    {
      "schema_version": 1,
      "id": "shape_star",
      "name": {"en": "Star", "it": "Stella"},
      "section": "shapes",
      "kind": "static",              # "static" (SVG/PNG) | "animated" (Lottie)
      "file": "shapes/star.svg"      # relative to the manifest's folder
    }

``kind`` decides which tab of the panel the sticker lives in. Static
stickers are SVG (preferred: they scale to any export size) or PNG.
Animated ones are Lottie JSON - the open, declarative animation format;
they are catalogued and installable today, and start playing when the
renderer lands (see docs/STICKERS.md).

An entry whose file is missing is skipped with a warning, never a crash:
a half-copied pack must not break the panel.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ive.utils.paths import get_data_path, get_defaults_path

log = logging.getLogger(__name__)

__all__ = ["list_stickers", "sticker_by_id", "sections", "reload",
           "KINDS"]

KINDS = ("static", "animated")

#: Display order of the factory sections, per tab; user sections follow
#: in the order they are first seen.
_SECTION_ORDER: dict[str, tuple[str, ...]] = {
    "static": ("shapes", "goodmorning", "greetings", "birthday"),
    "animated": ("demo",),
}

_cache: list[dict[str, Any]] | None = None


def _coerce(entry: Any, base: Path, origin: str,
            builtin: bool) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    sticker_id = str(entry.get("id") or "").strip()
    file_name = str(entry.get("file") or "").strip()
    if not sticker_id or not file_name:
        # Lottie animations are JSON too; a user may drop one next to a
        # manifest. Without id/file it is simply not a manifest entry.
        log.debug("Skipping a non-manifest entry in %s", origin)
        return None
    kind = str(entry.get("kind") or "static")
    if kind not in KINDS:
        log.warning("Sticker %r has unknown kind %r; treated as static",
                    sticker_id, kind)
        kind = "static"
    path = (base / file_name).resolve()
    if not path.is_file():
        log.warning("Sticker %r skipped: file missing (%s)", sticker_id, path)
        return None
    names = entry.get("name")
    if not isinstance(names, dict):
        names = {"en": str(names) if names else sticker_id}
    return {
        "id": sticker_id,
        "names": {str(k): str(v) for k, v in names.items()},
        "section": str(entry.get("section") or "shapes"),
        "kind": kind,
        "path": str(path),
        "builtin": builtin,
    }


def _scan(folder: Path, builtin: bool) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not folder.is_dir():
        return found
    # Manifests sit at the top of the folder; graphics live in subfolders,
    # so an animation's own .json can never be mistaken for a manifest.
    for path in sorted(folder.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Unreadable sticker manifest %s: %s", path.name, exc)
            continue
        entries = raw if isinstance(raw, list) else [raw]
        for entry in entries:
            sticker = _coerce(entry, path.parent, path.name, builtin)
            if sticker is not None:
                found.append(sticker)
    return found


def _load() -> list[dict[str, Any]]:
    from ive.packs.pack import pack_content_dirs

    stickers: list[dict[str, Any]] = []
    seen: set[str] = set()
    scanned = (_scan(get_defaults_path("stickers"), True)
               + _scan(get_data_path("stickers"), False))
    # Installed content packs bring their own stickers (graphics ride
    # relative to each pack's own folder); same duplicate-id rules.
    for folder in pack_content_dirs("stickers"):
        scanned += _scan(folder, False)
    for sticker in scanned:
        if sticker["id"] in seen:
            log.warning("Duplicate sticker id %r ignored", sticker["id"])
            continue
        seen.add(sticker["id"])
        stickers.append(sticker)
    log.info("Stickers loaded: %d (%d factory)",
             len(stickers), sum(1 for s in stickers if s["builtin"]))
    return stickers


def list_stickers() -> list[dict[str, Any]]:
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache


def reload() -> None:
    """Forget the cache; the next query rescans the folders."""
    global _cache
    _cache = None


def sticker_by_id(sticker_id: str) -> dict[str, Any] | None:
    return next((s for s in list_stickers() if s["id"] == sticker_id), None)


def sections(kind: str) -> list[str]:
    """The families of one tab, factory order first."""
    inside = [s for s in list_stickers() if s["kind"] == kind]
    ordered = [name for name in _SECTION_ORDER.get(kind, ())
               if any(s["section"] == name for s in inside)]
    for sticker in inside:
        if sticker["section"] not in ordered:
            ordered.append(sticker["section"])
    return ordered
