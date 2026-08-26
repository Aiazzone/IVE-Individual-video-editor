"""Keyframes: a list of timed value snapshots, linearly interpolated.

Shared by the MODEL (capture, edit) and the ENGINE (evaluation) - it
lives in utils because the engine must not import the model and the
model must not import the engine. A keyframe is
``{"t": clip-local seconds, <param>: value, ...}``: each frame carries
only the parameters it pins, so one param can be animated while
another stays static.

Semantics, the classic ones: before the first keyframe of a param the
first value holds, after the last the last holds, and between two the
value runs along the DESTINATION pin's easing - ``"linear"`` when it
says nothing. The easing belongs to the arriving keyframe (the
CapCut/After Effects convention): it describes how the value travels
INTO that pin, so every segment can have its own character.

``"spring"`` is not a curve between 0 and 1: it overshoots the
destination and settles, like something with mass arriving - the
response of an underdamped oscillator tuned to settle exactly over the
segment (~12% overshoot). Callers that cannot tolerate overshoot
(opacity, scale) clamp at the point of use, which they already do.
"""

from __future__ import annotations

import math

__all__ = ["evaluate", "upsert", "remove_at", "keyframe_at", "EASINGS"]

#: The easing vocabulary, in display order. "spring" is the physical
#: one; the others are the classic polynomial trio plus identity.
EASINGS = ("linear", "smooth", "ease_in", "ease_out", "spring")

#: Spring tuning: damping ratio and the natural frequency that settles
#: the response within the segment (4 / (zeta * omega) = 1).
_SPRING_ZETA = 0.55
_SPRING_OMEGA = 4.0 / _SPRING_ZETA
_SPRING_OMEGA_D = _SPRING_OMEGA * math.sqrt(1.0 - _SPRING_ZETA ** 2)


def _ease(u: float, easing: str) -> float:
    """Progress 0..1 -> eased progress (spring may exceed 1)."""
    u = min(1.0, max(0.0, float(u)))
    if easing == "smooth":
        return u * u * (3.0 - 2.0 * u)
    if easing == "ease_in":
        return u * u
    if easing == "ease_out":
        return 1.0 - (1.0 - u) * (1.0 - u)
    if easing == "spring":
        if u >= 1.0:
            return 1.0
        decay = math.exp(-_SPRING_ZETA * _SPRING_OMEGA * u)
        return 1.0 - decay * (math.cos(_SPRING_OMEGA_D * u)
                              + (_SPRING_ZETA * _SPRING_OMEGA
                                 / _SPRING_OMEGA_D)
                              * math.sin(_SPRING_OMEGA_D * u))
    return u

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
        timed = [(float(k["t"]), float(k[param]),
                  str(k.get("easing") or "linear"))
                 for k in keyframes if param in k]
        if not timed:
            continue
        timed.sort(key=lambda entry: entry[0])
        if t <= timed[0][0]:
            out[param] = timed[0][1]
            continue
        if t >= timed[-1][0]:
            out[param] = timed[-1][1]
            continue
        for (t0, v0, _e0), (t1, v1, easing) in zip(timed, timed[1:]):
            if t0 <= t <= t1:
                span = max(1e-9, t1 - t0)
                fraction = _ease((t - t0) / span, easing)
                out[param] = v0 + (v1 - v0) * fraction
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
    already there), sorted by time.

    ``values`` may carry ``"easing"`` (a string from EASINGS); when it
    does not, a replaced diamond KEEPS the easing it had - re-pinning a
    position must not silently straighten a spring.
    """
    entry: dict = {"t": round(float(t), 3)}
    for key, value in (values or {}).items():
        if key == "easing":
            if str(value) in EASINGS:
                entry["easing"] = str(value)
        else:
            entry[str(key)] = float(value)
    standing = keyframe_at(keyframes, t, tolerance)
    if standing is not None and "easing" not in entry \
            and standing.get("easing"):
        entry["easing"] = str(standing["easing"])
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
