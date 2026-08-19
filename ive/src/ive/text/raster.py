"""Text rasterization: from a title's words and style to RGBA pixels.

The twin of ive/stickers/raster.py, for the Text lane. The engine never
sees text or fonts: it receives the same ``sprite(canvas_h_px,
local_seconds)`` closures the stickers use, built here, and composites
them with the same Overlays filter - so a title behaves exactly like a
sticker on the video (same handles, same live drag, same undo shape).

The text is drawn as a QPainterPath - stroke first, fill on top - so the
outline hugs every glyph. It is drawn at a REFERENCE size and scaled to
the requested height: metrics stay consistent across sizes, and the
scale is what the transform handles change. ``scale`` on a text clip is
therefore the whole BLOCK's height as a canvas fraction: more lines mean
smaller letters, which is the predictable behaviour (the box the user
dragged stays the box they dragged).

Thread-safety: closures are called by whoever pulls the graph - one
puller at a time by the engine's own rule - so plain dict caches are
enough, exactly as in stickers/raster.py.
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

__all__ = ["attach_text_sprites", "render_text", "text_aspect"]

#: Glyphs are laid out at this pixel size, then scaled: layout at the
#: target size instead would make line breaks and metrics drift as the
#: user scales the title.
_REF_SIZE = 128.0
#: Outline stroke, as a fraction of the font size.
_STROKE = 0.08
_MAX_HEIGHT = 2160


def _build_path(text: str, font_family: str, bold: bool, italic: bool):
    """The glyph outlines, centred per line, plus the padded bounds."""
    from PySide6.QtGui import QFont, QFontMetricsF, QPainterPath

    font = QFont(font_family) if font_family else QFont()
    font.setPixelSize(int(_REF_SIZE))
    font.setBold(bool(bold))
    font.setItalic(bool(italic))

    metrics = QFontMetricsF(font)
    lines = str(text).split("\n")
    widths = [metrics.horizontalAdvance(line) for line in lines]
    block_width = max(widths) if widths else 0.0

    path = QPainterPath()
    for index, line in enumerate(lines):
        if not line:
            continue
        path.addText((block_width - widths[index]) / 2.0,
                     metrics.ascent() + index * metrics.height(),
                     font, line)
    pad = _REF_SIZE * _STROKE / 2.0 + 2.0
    bounds = path.boundingRect().adjusted(-pad, -pad, pad, pad)
    return path, bounds


def text_aspect(text: str, font: str = "", bold: bool = True,
                italic: bool = False) -> float:
    """Width / height of the rendered block, for the on-video handles."""
    try:
        _path, bounds = _build_path(text, font, bold, italic)
    except Exception:
        log.exception("Could not measure text")
        return 4.0
    if bounds.height() <= 0:
        return 4.0
    return max(0.05, bounds.width() / bounds.height())


def render_text(text: str, height_px: int, *, font: str = "",
                color: str = "#FFFFFF", outline: str = "#000000",
                bold: bool = True, italic: bool = False,
                rotation: float = 0.0) -> np.ndarray | None:
    """The title as a straight-RGBA array, ``height_px`` tall.

    ``outline`` empty means no outline. Rotation is baked into the
    raster like the static stickers', so the compositor only ever
    pastes an axis-aligned rectangle.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import (QColor, QImage, QPainter, QPen, QTransform)

    try:
        path, bounds = _build_path(text, font, bold, italic)
    except Exception:
        log.exception("Could not lay out text")
        return None
    if path.isEmpty() or bounds.height() <= 0:
        return None

    height_px = max(2, min(_MAX_HEIGHT, int(height_px)))
    scale = height_px / bounds.height()
    width_px = max(2, int(round(bounds.width() * scale)))

    image = QImage(width_px, height_px, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(scale, scale)
    painter.translate(-bounds.x(), -bounds.y())
    if outline:
        pen = QPen(QColor(outline), _REF_SIZE * _STROKE,
                   Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(path, pen)
    painter.fillPath(path, QColor(color))
    painter.end()

    if abs(float(rotation)) > 0.01:
        image = image.transformed(
            QTransform().rotate(float(rotation)),
            Qt.TransformationMode.SmoothTransformation)
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)

    width, height = image.width(), image.height()
    data = image.constBits().tobytes()
    return np.frombuffer(data, dtype=np.uint8).reshape(
        height, image.bytesPerLine() // 4, 4)[:, :width].copy()


def attach_text_sprites(spans: list[dict]) -> list[dict]:
    """Give each text span its ``sprite`` closure, IN PLACE.

    Same contract as stickers/raster.attach_sprites: the closure reads
    words, style, scale and rotation from the span dict at CALL time,
    and attaches on the caller's own dict - so both the transform
    handles AND live text editing in the panel reach the very next
    pulled frame without a graph rebuild. Returns the usable spans.
    """
    out = []
    for span in spans or []:
        if not str(span.get("text") or "").strip():
            continue
        cache: dict = {}

        def sprite(canvas_h, seconds, _span=span, _cache=cache):
            key = (
                str(_span.get("text") or ""),
                str(_span.get("font") or ""),
                str(_span.get("color") or "#FFFFFF"),
                str(_span.get("outline") or ""),
                bool(_span.get("bold", True)),
                bool(_span.get("italic", False)),
                int(round(canvas_h * float(_span.get("scale") or 0.1))),
                round(float(_span.get("rotation") or 0.0), 1),
            )
            arr = _cache.get(key)
            if arr is None:
                arr = render_text(key[0], key[6], font=key[1], color=key[2],
                                  outline=key[3], bold=key[4], italic=key[5],
                                  rotation=key[7])
                _cache[key] = arr
                # A scale or rotation drag sweeps many sizes and angles;
                # keep the cache from hoarding all of them.
                if len(_cache) > 64:
                    _cache.clear()
                    _cache[key] = arr
            return arr

        span["sprite"] = sprite
        out.append(span)
    return out
