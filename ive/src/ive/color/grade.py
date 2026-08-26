"""The manual grade: nine dials over the recipes' own op vocabulary.

A grade is a dict of dial values stored on a Color-lane clip
(``TimelineClip.grade``). It compiles to the SAME ops the JSON recipes
use (engine/filters.apply_colour_ops), appended after the clip's
effect recipe when there is one - so hand adjustments layer on top of
a look, and preview and export grade identically because both read the
compiled ops.

Only values away from their default are stored and compiled: an
untouched dial costs nothing, and a grade dict says exactly what the
user changed.
"""

from __future__ import annotations

__all__ = ["DIALS", "clamp_grade", "ops_from_grade"]

#: key -> (default, minimum, maximum). The ORDER is the compile order:
#: exposure first, colour casts, then the tonal shapers, vignette last.
DIALS: dict[str, tuple[float, float, float]] = {
    "brightness": (0.0, -0.5, 0.5),
    "contrast": (1.0, 0.2, 2.0),
    "saturation": (1.0, 0.0, 2.0),
    "gamma": (1.0, 0.3, 2.5),
    "temperature": (0.0, -1.0, 1.0),
    "tint": (0.0, -1.0, 1.0),
    "shadows": (0.0, -1.0, 1.0),
    "highlights": (0.0, -1.0, 1.0),
    "vignette": (0.0, 0.0, 1.0),
}

#: Which op each dial compiles to, and the payload key it fills.
_OP_KEY = {"gamma": "value", "vignette": "strength"}


def clamp_grade(grade: dict) -> dict:
    """Known dials only, clamped, defaults dropped."""
    out: dict[str, float] = {}
    for key, (default, low, high) in DIALS.items():
        if key not in (grade or {}):
            continue
        try:
            value = float(grade[key])
        except (TypeError, ValueError):
            continue
        value = min(high, max(low, value))
        if abs(value - default) > 1e-4:
            out[key] = round(value, 4)
    return out


def ops_from_grade(grade: dict) -> list[dict]:
    """The grade as engine ops, in the compile order of DIALS."""
    grade = clamp_grade(grade)
    ops: list[dict] = []
    for key in DIALS:
        if key not in grade:
            continue
        payload_key = _OP_KEY.get(key, "amount")
        ops.append({"op": key, payload_key: grade[key]})
    return ops
