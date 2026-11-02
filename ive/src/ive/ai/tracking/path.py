"""From the target's path on the canvas to the overlay's keyframes.

The tracker reports where the TARGET is; the overlay keeps the relation
to it that the user set before tracking - a sticker placed above a
head stays above the head, and (following size) the gap grows as the
head comes closer. Two passes make the result something a person can
still edit by hand (docs/AI_FEATURES.md §1, "correggibile"):

* smoothing - a centred moving average. The box a tracker reports
  breathes by a pixel or two even on a still target, and the size more
  than the position, so size gets the wider window;
* thinning - Ramer-Douglas-Peucker over (x, y, scale): a pin is kept
  only where linear interpolation between its neighbours would miss by
  more than the tolerance. A straight pan collapses to two diamonds, a
  wobble keeps what it needs.

Pure Python, no Qt, no NumPy.
"""

from __future__ import annotations

__all__ = ["overlay_samples", "smooth", "thin"]

#: Position tolerance, canvas heights: ~2 px on a 1080 canvas.
POSITION_TOLERANCE = 0.002
#: Scale tolerance, relative to the overlay's own scale.
SCALE_TOLERANCE = 0.01

_POSITION_WINDOW = 5
_SIZE_WINDOW = 9


def smooth(values: list[float], window: int) -> list[float]:
    """Centred moving average; the window shrinks at the ends so the
    first and last values stay put (they anchor the overlay)."""
    n = len(values)
    half = max(0, int(window) // 2)
    out = []
    for i in range(n):
        reach = min(half, i, n - 1 - i)
        chunk = values[i - reach:i + reach + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def thin(samples: list[dict], tolerances: dict) -> list[dict]:
    """Ramer-Douglas-Peucker on timed samples, several params at once.

    ``tolerances`` maps each param to its allowed miss; a sample is
    dropped only if EVERY param interpolates within its tolerance.
    """
    n = len(samples)
    if n <= 2:
        return list(samples)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        t0, t1 = samples[first]["t"], samples[last]["t"]
        span = max(1e-9, t1 - t0)
        worst, worst_at = 1.0, -1
        for i in range(first + 1, last):
            u = (samples[i]["t"] - t0) / span
            for param, tolerance in tolerances.items():
                v0, v1 = samples[first][param], samples[last][param]
                miss = abs(samples[i][param] - (v0 + (v1 - v0) * u))
                ratio = miss / max(1e-9, tolerance)
                if ratio > worst:
                    worst, worst_at = ratio, i
        if worst_at >= 0:
            keep[worst_at] = True
            stack.append((first, worst_at))
            stack.append((worst_at, last))
    return [s for s, kept in zip(samples, keep) if kept]


def overlay_samples(observations: list[dict], anchor: dict,
                    canvas_aspect: float, overlay_start: float,
                    follow_size: bool = True,
                    anchor_index: int = 0) -> list[dict]:
    """The overlay's clip-local pins along the target's path.

    ``observations`` are ``{"t": timeline s, "cx", "cy": canvas
    fractions, "h": target height in canvas heights}``, in time order,
    trusted frames only. ``anchor`` is the overlay's transform at
    observation ``anchor_index`` - the frame the box was drawn on, which
    is not the first one when tracking ran backwards - and the relation
    to keep (``x``, ``y``, ``scale``).
    """
    if not observations:
        return []
    width = max(1e-6, float(canvas_aspect))
    cx = smooth([float(o["cx"]) for o in observations], _POSITION_WINDOW)
    cy = smooth([float(o["cy"]) for o in observations], _POSITION_WINDOW)
    h = smooth([max(1e-6, float(o["h"])) for o in observations],
               _SIZE_WINDOW)
    # The gap overlay-target, in canvas heights on both axes so that a
    # size ratio scales it isotropically.
    a = max(0, min(len(observations) - 1, int(anchor_index)))
    gap_x = (float(anchor["x"]) - cx[a]) * width
    gap_y = float(anchor["y"]) - cy[a]
    scale0 = float(anchor.get("scale", 0.3))
    samples = []
    for i, obs in enumerate(observations):
        ratio = h[i] / h[a] if follow_size else 1.0
        sample = {
            "t": round(float(obs["t"]) - float(overlay_start), 4),
            "x": (cx[i] * width + gap_x * ratio) / width,
            "y": cy[i] + gap_y * ratio,
        }
        if follow_size:
            sample["scale"] = scale0 * ratio
        samples.append(sample)
    tolerances = {"x": POSITION_TOLERANCE / width,
                  "y": POSITION_TOLERANCE}
    if follow_size:
        tolerances["scale"] = SCALE_TOLERANCE * scale0
    return thin(samples, tolerances)
