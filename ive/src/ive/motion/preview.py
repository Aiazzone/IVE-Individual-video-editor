"""Hover film strips for motion presets.

A preset card previews THIS overlay (a sticker, a title) moved by THAT
recipe: a row of square cells across the preset's duration, each the
overlay's own still transformed by the evaluated values. The rendering
of the still is the caller's business (``still(height_px, rotation)``
returns a straight-RGBA array or None); this module only knows how to
lay the frames out, so stickers and titles share one compositor.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np

log = logging.getLogger(__name__)

__all__ = ["compose_strip", "STRIP_SIDE", "STRIP_FRAMES"]

STRIP_SIDE = 120
STRIP_FRAMES = 14
#: The overlay's resting height as a fraction of the cell side.
_REST_HEIGHT = 0.55


def compose_strip(still: Callable[[int, float], np.ndarray | None],
                  recipe: dict[str, Any], *, side: int = STRIP_SIDE,
                  count: int = STRIP_FRAMES,
                  rest_height: float = _REST_HEIGHT) -> np.ndarray | None:
    """``count`` cells side by side, ``side`` px square each, RGBA.

    The recipe is evaluated at evenly spaced moments over its duration
    (one period for a loop, the whole entrance/exit otherwise). Returns
    None when the recipe does not evaluate - never raises for a bad
    preset, the card simply stays still.
    """
    from ive.motion.runtime import make_motion

    motion = make_motion(recipe)
    if motion is None:
        return None
    duration = float(recipe.get("duration") or 0.8)
    count = max(2, int(count))
    cells = []
    for index in range(count):
        t = index / (count - 1) * duration
        values = motion(t, duration)
        cell = np.zeros((side, side, 4), dtype=np.uint8)
        opacity = max(0.0, min(1.0, values.get("opacity", 1.0)))
        height = int(round(side * rest_height * values.get("scale", 1.0)))
        if opacity > 0.0 and height >= 2:
            rgba = still(height, values.get("rotation", 0.0))
            if rgba is not None:
                if opacity < 1.0:
                    rgba = rgba.copy()
                    rgba[..., 3] = (rgba[..., 3] * opacity).astype(np.uint8)
                h, w = rgba.shape[:2]
                cx = side / 2 + values.get("dx", 0.0) * side
                cy = side / 2 + values.get("dy", 0.0) * side
                x0 = int(round(cx - w / 2))
                y0 = int(round(cy - h / 2))
                sx0, sy0 = max(0, -x0), max(0, -y0)
                dx0, dy0 = max(0, x0), max(0, y0)
                cw = min(side - dx0, w - sx0)
                ch = min(side - dy0, h - sy0)
                if cw > 0 and ch > 0:
                    cell[dy0:dy0 + ch, dx0:dx0 + cw] = \
                        rgba[sy0:sy0 + ch, sx0:sx0 + cw]
        cells.append(cell)
    return np.ascontiguousarray(np.hstack(cells))
