"""The motion-preset catalogue.

A preset is a JSON document, not code - the same rule as colours,
transitions and stickers. Factory presets ship in
``ive/config/defaults/motion/``; the user's own live in
``user_data/motion/``, and installed content packs bring theirs in a
``motion/`` folder.

Shape of one preset::

    {
      "schema_version": 1,
      "id": "bounce",
      "name": {"en": "Bounce", "it": "Rimbalzo"},
      "kind": "loop",                # "in" | "out" | "loop"
      "duration": 0.9,               # seconds: the loop period, or how
                                     # long the entrance/exit plays
      "tracks": [
        { "parameter": "y",
          "keyframes": [
            {"t": 0.0, "value": 0.0},
            {"t": 0.5, "value": -0.06, "easing": "out_quad"},
            {"t": 1.0, "value": 0.0, "easing": "in_quad"} ] }
      ]
    }

``t`` is NORMALISED 0..1 over the duration, so the same recipe works
at any speed. Parameters and their meaning (all RELATIVE to the clip's
own transform, so a preset composes with wherever the user dragged the
sticker): ``x``/``y`` offsets in canvas fractions, ``scale`` a
multiplier around 1, ``rotation`` degrees added, ``opacity`` a 0..1
multiplier. The easing on a keyframe shapes the segment LEAVING it;
the closed set lives in runtime.py. Unknown parameters degrade with a
warning, never break.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ive.utils.paths import get_data_path, get_defaults_path

log = logging.getLogger(__name__)

__all__ = ["list_presets", "preset_by_id", "recipe_for", "sections",
           "reload", "KINDS"]

KINDS = ("in", "out", "loop")
_SECTION_ORDER = ("in", "loop", "out")

_cache: list[dict[str, Any]] | None = None


def _coerce(entry: Any, origin: str, builtin: bool) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    preset_id = str(entry.get("id") or "").strip()
    tracks = entry.get("tracks")
    if not preset_id or not isinstance(tracks, list) or not tracks:
        log.warning("Skipping a motion preset without id/tracks in %s",
                    origin)
        return None
    kind = str(entry.get("kind") or "loop")
    if kind not in KINDS:
        log.warning("Motion preset %r has unknown kind %r; treated as loop",
                    preset_id, kind)
        kind = "loop"
    names = entry.get("name")
    if not isinstance(names, dict):
        names = {"en": str(names) if names else preset_id}
    return {
        "id": preset_id,
        "names": {str(k): str(v) for k, v in names.items()},
        "kind": kind,
        "duration": min(10.0, max(0.1,
                                  float(entry.get("duration") or 0.8))),
        "tracks": [dict(t) for t in tracks if isinstance(t, dict)],
        "builtin": builtin,
    }


def _scan(folder: Path, builtin: bool) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not folder.is_dir():
        return found
    for path in sorted(folder.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Unreadable motion preset file %s: %s",
                        path.name, exc)
            continue
        entries = raw if isinstance(raw, list) else [raw]
        for entry in entries:
            preset = _coerce(entry, path.name, builtin)
            if preset is not None:
                found.append(preset)
    return found


def _load() -> list[dict[str, Any]]:
    from ive.packs.pack import pack_content_dirs

    presets: list[dict[str, Any]] = []
    seen: set[str] = set()
    scanned = (_scan(get_defaults_path("motion"), True)
               + _scan(get_data_path("motion"), False))
    for folder in pack_content_dirs("motion"):
        scanned += _scan(folder, False)
    for preset in scanned:
        if preset["id"] in seen:
            log.warning("Duplicate motion preset id %r ignored",
                        preset["id"])
            continue
        seen.add(preset["id"])
        presets.append(preset)
    log.info("Motion presets loaded: %d (%d factory)",
             len(presets), sum(1 for p in presets if p["builtin"]))
    return presets


def list_presets() -> list[dict[str, Any]]:
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache


def reload() -> None:
    """Forget the cache; the next query rescans the folders."""
    global _cache
    _cache = None


def preset_by_id(preset_id: str) -> dict[str, Any] | None:
    return next((p for p in list_presets() if p["id"] == preset_id), None)


def recipe_for(preset_id: str) -> dict[str, Any] | None:
    """The pure-data recipe behind an id; None for an unknown preset (a
    project can reference one the user has since deleted - it must load
    anyway, the sticker simply stands still)."""
    preset = preset_by_id(preset_id)
    if preset is None:
        return None
    return {"kind": preset["kind"], "duration": preset["duration"],
            "tracks": [dict(t) for t in preset["tracks"]]}


def sections() -> list[str]:
    """The kinds that actually have presets, in display order."""
    return [k for k in _SECTION_ORDER
            if any(p["kind"] == k for p in list_presets())]
