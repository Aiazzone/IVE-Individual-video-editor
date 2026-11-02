"""Where a source pixel lands on the canvas, and back.

The tracker sees the SOURCE picture of an A/V clip; the overlay that
follows lives in CANVAS fractions. Between the two sit the clip's crop
and either the project's canvas fit or the clip's free placement - the
same arithmetic the engine applies (engine/filters.Placement crops
first, then engine/tractor fits, or Placement floats the box). It is
redone here as pure geometry rather than by pushing pixels through the
graph, because the graph would also draw the overlay being tracked.

Units: canvas HEIGHT is 1, canvas width is the aspect. Source points
are fractions (u, v) of the decoded frame; canvas points come out as
the fractions overlays store (x of the width, y of the height). Pixel
rounding inside the engine (at most half a pixel) is ignored.
"""

from __future__ import annotations

import math

__all__ = ["CanvasMap"]


class CanvasMap:
    """One A/V clip's source -> canvas transform at one instant."""

    def __init__(self, source_aspect: float, canvas_aspect: float,
                 fit: str = "fit", crop: dict | None = None,
                 placed: bool = False, x: float = 0.5, y: float = 0.5,
                 scale: float = 1.0, rotation: float = 0.0) -> None:
        crop = crop or {}

        def inset(edge: str) -> float:
            return min(0.45, max(0.0, float(crop.get(edge, 0.0) or 0.0)))

        self._left, self._right = inset("left"), inset("right")
        self._top, self._bottom = inset("top"), inset("bottom")
        span_u = max(1e-6, 1.0 - self._left - self._right)
        span_v = max(1e-6, 1.0 - self._top - self._bottom)
        self._span_u, self._span_v = span_u, span_v
        aspect = max(1e-6, float(source_aspect)) * span_u / span_v
        self._width = max(1e-6, float(canvas_aspect))
        if placed:
            pic_h = min(2.0, max(0.02, float(scale)))
            self._centre = (float(x) * self._width, float(y))
            self._angle = math.radians(float(rotation))
        else:
            ratio = self._width / aspect
            pic_h = max(1.0, ratio) if fit == "fill" else min(1.0, ratio)
            self._centre = (self._width / 2.0, 0.5)
            self._angle = 0.0
        self._pic = (pic_h * aspect, pic_h)

    @property
    def picture_height(self) -> float:
        """The cropped picture's height in canvas heights."""
        return self._pic[1]

    def to_canvas(self, u: float, v: float) -> tuple[float, float]:
        """Source fractions -> canvas fractions (x of width, y of height)."""
        cu = (float(u) - self._left) / self._span_u - 0.5
        cv = (float(v) - self._top) / self._span_v - 0.5
        dx, dy = cu * self._pic[0], cv * self._pic[1]
        cos, sin = math.cos(self._angle), math.sin(self._angle)
        # Clockwise on screen (y grows downwards), as Placement draws it.
        px = self._centre[0] + dx * cos - dy * sin
        py = self._centre[1] + dx * sin + dy * cos
        return px / self._width, py

    def to_source(self, x: float, y: float) -> tuple[float, float]:
        """Canvas fractions -> source fractions (may fall outside 0..1)."""
        px = float(x) * self._width - self._centre[0]
        py = float(y) - self._centre[1]
        cos, sin = math.cos(self._angle), math.sin(self._angle)
        dx = px * cos + py * sin
        dy = -px * sin + py * cos
        cu = dx / self._pic[0] + 0.5
        cv = dy / self._pic[1] + 0.5
        return (self._left + cu * self._span_u,
                self._top + cv * self._span_v)

    def height_to_canvas(self, h: float) -> float:
        """A source height fraction -> canvas heights."""
        return float(h) / self._span_v * self._pic[1]

    def height_to_source(self, h: float) -> float:
        """Canvas heights -> a source height fraction."""
        return float(h) / self._pic[1] * self._span_v

    def width_to_source(self, w: float) -> float:
        """A canvas WIDTH fraction -> a source width fraction."""
        return float(w) * self._width / self._pic[0] * self._span_u
