"""The colour-effect catalogue.

An effect is a JSON document, not code (docs/CONTENT_PACKS.md rule:
installing content must be safe because nothing executes). Factory effects
ship in ``ive/config/defaults/color_effects/``; the user's own live in
``user_data/effects/color/`` - dropping a ``.json`` there (or receiving one
from another user) is the whole installation. A file may hold one effect
or a list of them.

Shape of one effect::

    {
      "schema_version": 1,
      "id": "warm_memory",
      "name": {"en": "Warm memory", "it": "Ricordo caldo"},
      "section": "nostalgia",
      "ops": [ {"op": "temperature", "amount": 0.35}, ... ]
    }

The ``ops`` vocabulary is documented in engine/filters.py
(:func:`~ive.engine.filters.apply_colour_ops`). Unknown ops degrade with a
warning rather than break: a recipe written by a newer version must still
load.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ive.utils.paths import get_data_path, get_defaults_path

log = logging.getLogger(__name__)

__all__ = ["list_effects", "effect_by_id", "ops_for", "sections", "reload"]

#: Display order of the factory sections; user sections follow, in the
#: order they are first seen.
_SECTION_ORDER = ("nostalgia", "cyberpunk", "cinema", "base")

_cache: list[dict[str, Any]] | None = None


def _coerce(entry: Any, origin: str, builtin: bool) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    effect_id = str(entry.get("id") or "").strip()
    ops = entry.get("ops")
    if not effect_id or not isinstance(ops, list):
        log.warning("Skipping a colour effect without id/ops in %s", origin)
        return None
    names = entry.get("name")
    if not isinstance(names, dict):
        names = {"en": str(names) if names else effect_id}
    return {
        "id": effect_id,
        "names": {str(k): str(v) for k, v in names.items()},
        "section": str(entry.get("section") or "base"),
        "ops": [dict(op) for op in ops if isinstance(op, dict)],
        "builtin": builtin,
    }


def _scan(folder: Path, builtin: bool) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not folder.is_dir():
        return found
    for path in sorted(folder.glob("*.json")):
        try:
            # utf-8-sig: files that crossed a Windows editor may carry a BOM.
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Unreadable colour effect file %s: %s", path.name, exc)
            continue
        entries = raw if isinstance(raw, list) else [raw]
        for entry in entries:
            effect = _coerce(entry, path.name, builtin)
            if effect is not None:
                found.append(effect)
    return found


def _load() -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    seen: set[str] = set()
    for effect in (_scan(get_defaults_path("color_effects"), True)
                   + _scan(get_data_path("effects/color"), False)):
        if effect["id"] in seen:
            # A user effect never overrides a factory one silently; same
            # rule as export presets.
            log.warning("Duplicate colour effect id %r ignored", effect["id"])
            continue
        seen.add(effect["id"])
        effects.append(effect)
    log.info("Colour effects loaded: %d (%d factory)",
             len(effects), sum(1 for e in effects if e["builtin"]))
    return effects


def list_effects() -> list[dict[str, Any]]:
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache


def reload() -> None:
    """Forget the cache; the next query rescans the folders."""
    global _cache
    _cache = None


def effect_by_id(effect_id: str) -> dict[str, Any] | None:
    return next((e for e in list_effects() if e["id"] == effect_id), None)


def ops_for(effect_id: str) -> list[dict[str, Any]]:
    """The recipe behind an id; empty for an unknown effect (a project can
    reference an effect the user has since deleted - it must load anyway,
    the stretch simply plays ungraded)."""
    effect = effect_by_id(effect_id)
    return list(effect["ops"]) if effect else []


def sections() -> list[str]:
    ordered = [s for s in _SECTION_ORDER
               if any(e["section"] == s for e in list_effects())]
    for effect in list_effects():
        if effect["section"] not in ordered:
            ordered.append(effect["section"])
    return ordered
