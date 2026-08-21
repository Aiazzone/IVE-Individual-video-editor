"""The audio-effect catalogue.

An effect is a JSON document, not code - the same rule as colours,
transitions, stickers and motion. Factory effects ship in
``ive/config/defaults/audio_effects/``; the user's own live in
``user_data/audio_effects/``; installed content packs bring theirs in an
``audio_effects/`` folder. A file may hold one effect or a list.

Shape of one effect::

    {
      "schema_version": 1,
      "id": "voice_clear",
      "name": {"en": "Clear voice", "it": "Voce chiara"},
      "section": "voice",
      "ops": [ {"op": "highpass", "hz": 90},
               {"op": "peak", "hz": 3000, "q": 1.0, "db": 3},
               {"op": "compressor", "threshold_db": -20, "ratio": 3} ]
    }

The ``ops`` vocabulary lives in :mod:`ive.audio.dsp`. Unknown ops degrade
with a warning, never break.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ive.utils.paths import get_data_path, get_defaults_path

log = logging.getLogger(__name__)

__all__ = ["list_effects", "effect_by_id", "ops_for", "sections", "reload"]

_SECTION_ORDER = ("voice", "music", "clean", "fx")

_cache: list[dict[str, Any]] | None = None


def _coerce(entry: Any, origin: str, builtin: bool) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    effect_id = str(entry.get("id") or "").strip()
    ops = entry.get("ops")
    if not effect_id or not isinstance(ops, list):
        log.warning("Skipping an audio effect without id/ops in %s", origin)
        return None
    names = entry.get("name")
    if not isinstance(names, dict):
        names = {"en": str(names) if names else effect_id}
    return {
        "id": effect_id,
        "names": {str(k): str(v) for k, v in names.items()},
        "section": str(entry.get("section") or "fx"),
        "ops": [dict(op) for op in ops if isinstance(op, dict)],
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
            log.warning("Unreadable audio effect file %s: %s", path.name, exc)
            continue
        entries = raw if isinstance(raw, list) else [raw]
        for entry in entries:
            effect = _coerce(entry, path.name, builtin)
            if effect is not None:
                found.append(effect)
    return found


def _load() -> list[dict[str, Any]]:
    from ive.packs.pack import pack_content_dirs

    effects: list[dict[str, Any]] = []
    seen: set[str] = set()
    scanned = (_scan(get_defaults_path("audio_effects"), True)
               + _scan(get_data_path("audio_effects"), False))
    for folder in pack_content_dirs("audio_effects"):
        scanned += _scan(folder, False)
    for effect in scanned:
        if effect["id"] in seen:
            log.warning("Duplicate audio effect id %r ignored", effect["id"])
            continue
        seen.add(effect["id"])
        effects.append(effect)
    log.info("Audio effects loaded: %d (%d factory)", len(effects),
             sum(1 for e in effects if e["builtin"]))
    return effects


def list_effects() -> list[dict[str, Any]]:
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache


def reload() -> None:
    global _cache
    _cache = None


def effect_by_id(effect_id: str) -> dict[str, Any] | None:
    return next((e for e in list_effects() if e["id"] == effect_id), None)


def ops_for(effect_id: str) -> list[dict[str, Any]]:
    """The pure-data ops behind an id; [] for an unknown effect (a project
    may reference one the user has since removed - it must still play)."""
    effect = effect_by_id(effect_id)
    return [dict(op) for op in effect["ops"]] if effect else []


def sections() -> list[str]:
    """Sections in display order: the known ones first, then any others
    a pack brought, alphabetically."""
    present = {e["section"] for e in list_effects()}
    out = [s for s in _SECTION_ORDER if s in present]
    out += sorted(s for s in present if s not in _SECTION_ORDER)
    return out
