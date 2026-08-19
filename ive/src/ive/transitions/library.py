"""The transition catalogue.

A transition is a JSON document, not code - same rule as the colour
effects. Factory transitions ship in ``ive/config/defaults/transitions/``
(luma PNGs in subfolders next to their manifests); the user's own live
in ``user_data/transitions/`` - dropping the files there is the whole
installation, and a hand-drawn greyscale PNG plus four lines of JSON IS
a brand-new transition.

Shape of one transition::

    {
      "schema_version": 1,
      "id": "circle_open",
      "name": {"en": "Circle open", "it": "Cerchio che si apre"},
      "section": "wipe",
      "duration": 0.8,
      "easing": "smooth",
      "op": {"kind": "luma", "file": "luma/circle_open.png",
             "softness": 0.12}
    }

``op.kind`` vocabulary (engine/transitions.make_blender): ``mix``,
``luma`` (file = greyscale map, relative to the manifest), ``wipe``
(direction: left/right/up/down/circle_in/circle_out), ``push``,
``slide`` (direction), ``zoom``, ``through_color`` (color). Unknown
kinds degrade with a warning, never break.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ive.utils.paths import get_data_path, get_defaults_path

log = logging.getLogger(__name__)

__all__ = ["list_transitions", "transition_by_id", "payload_for",
           "sections", "reload"]

_SECTION_ORDER = ("dissolve", "wipe", "motion")

_cache: list[dict[str, Any]] | None = None


def _coerce(entry: Any, folder: Path, origin: str,
            builtin: bool) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    transition_id = str(entry.get("id") or "").strip()
    op = entry.get("op")
    if not transition_id or not isinstance(op, dict):
        log.warning("Skipping a transition without id/op in %s", origin)
        return None
    payload = {str(k): v for k, v in op.items()}
    file_name = str(payload.get("file") or "")
    if file_name:
        target = (folder / file_name).resolve()
        if not target.is_file():
            log.warning("Transition %r skipped: file %s is missing",
                        transition_id, file_name)
            return None
        payload["file"] = str(target)
    names = entry.get("name")
    if not isinstance(names, dict):
        names = {"en": str(names) if names else transition_id}
    return {
        "id": transition_id,
        "names": {str(k): str(v) for k, v in names.items()},
        "section": str(entry.get("section") or "dissolve"),
        "duration": min(5.0, max(0.1, float(entry.get("duration") or 0.5))),
        "easing": str(entry.get("easing") or "smooth"),
        "op": payload,
        "builtin": builtin,
    }


def _scan(folder: Path, builtin: bool) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not folder.is_dir():
        return found
    # Manifests sit at the TOP of the folder; graphics in subfolders, so
    # a stray PNG next to them can never be mistaken for a manifest.
    for path in sorted(folder.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Unreadable transition file %s: %s", path.name, exc)
            continue
        entries = raw if isinstance(raw, list) else [raw]
        for entry in entries:
            transition = _coerce(entry, folder, path.name, builtin)
            if transition is not None:
                found.append(transition)
    return found


def _load() -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for transition in (_scan(get_defaults_path("transitions"), True)
                       + _scan(get_data_path("transitions"), False)):
        if transition["id"] in seen:
            log.warning("Duplicate transition id %r ignored",
                        transition["id"])
            continue
        seen.add(transition["id"])
        transitions.append(transition)
    log.info("Transitions loaded: %d (%d factory)",
             len(transitions), sum(1 for t in transitions if t["builtin"]))
    return transitions


def list_transitions() -> list[dict[str, Any]]:
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache


def reload() -> None:
    """Forget the cache; the next query rescans the folders."""
    global _cache
    _cache = None


def transition_by_id(transition_id: str) -> dict[str, Any] | None:
    return next((t for t in list_transitions() if t["id"] == transition_id),
                None)


def payload_for(transition_id: str) -> dict[str, Any] | None:
    """``{op..., easing}`` behind an id; None for an unknown transition (a
    project can reference one the user has since deleted - it must load
    anyway, the cut simply plays plain)."""
    transition = transition_by_id(transition_id)
    if transition is None:
        return None
    payload = dict(transition["op"])
    payload["easing"] = transition["easing"]
    return payload


def sections() -> list[str]:
    ordered = [s for s in _SECTION_ORDER
               if any(t["section"] == s for t in list_transitions())]
    for transition in list_transitions():
        if transition["section"] not in ordered:
            ordered.append(transition["section"])
    return ordered
