"""Keyframes: a list of timed value snapshots, linearly interpolated.

Shared by the MODEL (capture, edit) and the ENGINE (evaluation) - it
lives in utils because the engine must not import the model and the
model must not import the engine. A keyframe is
``{"t": clip-local seconds, <param>: value, ...}``: each frame carries
only the parameters it pins, so one param can be animated while
another stays static.

Semantics, the classic ones: before the first keyframe of a param the
first value holds, after the last the last holds, and between two the
value runs linearly. No easing curves yet - when the curve editor
lands, an "easing" field per keyframe slots in here without touching
the callers.
"""

from __future__ import annotations

__all__ = ["evaluate", "upsert", "remove_at", "keyframe_at"]

#: Two keyframes closer than this are the same instant: a capture on an
#: existing diamond REPLACES it instead of stacking a twin.
_TOLERANCE = 0.05


def evaluate(keyframes: list, t: float, defaults: dict) -> dict:
    """The parameter values at clip-local ``t``.

    ``defaults`` names the parameters wanted and their static values;
    a param no keyframe pins keeps its default.
    """
    out = dict(defaults)
    if not keyframes:
        return out
    t = float(t)
    for param in defaults:
        timed = [(float(k["t"]), float(k[param]))
                 for k in keyframes if param in k]
        if not timed:
            continue
        timed.sort()
        if t <= timed[0][0]:
            out[param] = timed[0][1]
            continue
        if t >= timed[-1][0]:
            out[param] = timed[-1][1]
            continue
        for (t0, v0), (t1, v1) in zip(timed, timed[1:]):
            if t0 <= t <= t1:
                span = max(1e-9, t1 - t0)
                out[param] = v0 + (v1 - v0) * (t - t0) / span
                break
    return out


def keyframe_at(keyframes: list, t: float,
                tolerance: float = _TOLERANCE) -> dict | None:
    """The keyframe standing at ``t``, or None."""
    return next((k for k in keyframes or []
                 if abs(float(k.get("t", 0.0)) - float(t)) <= tolerance),
                None)


def upsert(keyframes: list, t: float, values: dict,
           tolerance: float = _TOLERANCE) -> list:
    """A new list with ``values`` pinned at ``t`` (replacing a diamond
    already there), sorted by time."""
    entry = {"t": round(float(t), 3)}
    entry.update({str(k): float(v) for k, v in (values or {}).items()})
    out = [k for k in keyframes or []
           if abs(float(k.get("t", 0.0)) - float(t)) > tolerance]
    out.append(entry)
    out.sort(key=lambda k: float(k.get("t", 0.0)))
    return out


def remove_at(keyframes: list, t: float,
              tolerance: float = _TOLERANCE) -> list | None:
    """A new list without the keyframe at ``t``; None when none stood
    there (so the caller can refuse instead of no-opping)."""
    kept = [k for k in keyframes or []
            if abs(float(k.get("t", 0.0)) - float(t)) > tolerance]
    if len(kept) == len(keyframes or []):
        return None
    return kept
