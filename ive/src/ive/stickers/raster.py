"""Sticker rasterization: from a file to RGBA pixels at a given size.

This is the ONE place that turns sticker sources into arrays the engine
can composite - QtSvg for vectors, QImage for rasters, rlottie for Lottie
animations. The engine itself stays free of Qt: it receives closures
("give me your straight-RGBA pixels for this canvas at this local time")
built here by :func:`attach_sprites`.

Caching: static sprites are rendered once per (size, rotation) and kept;
animated ones keep their decoded frames per (size, frame index) so a
looping sticker costs one rlottie render per DISTINCT frame, then reads
from memory. rlottie renders premultiplied BGRA - converted to straight
RGBA here, once, so the blend in the engine is a single formula.

Thread-safety: sprite closures are called by whoever pulls the graph
(read-ahead thread in preview, export worker) - one puller at a time by
the engine's own rule, so plain dict caches are enough.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

__all__ = ["attach_sprites", "render_static", "render_lottie_frame",
           "lottie_info", "sprite_aspect"]

#: Height cap for a rendered sprite: a sticker never needs to be taller
#: than a 4K frame.
_MAX_HEIGHT = 2160


def render_static(path: str, height_px: int,
                  rotation: float = 0.0) -> np.ndarray | None:
    """An SVG or raster file as a straight-RGBA array, ``height_px`` tall.

    Rotation is baked into the raster (the bounding box grows to fit), so
    the compositor only ever pastes an axis-aligned rectangle.
    """
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter, QTransform
    from PySide6.QtSvg import QSvgRenderer

    height_px = max(2, min(_MAX_HEIGHT, int(height_px)))
    suffix = Path(path).suffix.lower()
    if suffix == ".svg":
        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            log.warning("Unrenderable SVG sticker: %s", path)
            return None
        base = renderer.defaultSize()
        aspect = (base.width() / base.height()) if base.height() else 1.0
        width_px = max(2, int(round(height_px * aspect)))
        image = QImage(width_px, height_px, QImage.Format.Format_RGBA8888)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, width_px, height_px))
        painter.end()
    else:
        image = QImage(str(path))
        if image.isNull():
            log.warning("Unreadable sticker image: %s", path)
            return None
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        image = image.scaledToHeight(
            height_px, Qt.TransformationMode.SmoothTransformation)

    if abs(float(rotation)) > 0.01:
        image = image.transformed(
            QTransform().rotate(float(rotation)),
            Qt.TransformationMode.SmoothTransformation)
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)

    width, height = image.width(), image.height()
    data = image.constBits().tobytes()
    return np.frombuffer(data, dtype=np.uint8).reshape(
        height, image.bytesPerLine() // 4, 4)[:, :width].copy()


# ── Lottie ───────────────────────────────────────────────────────────

#: Open animations by path; each also caches its rendered frames.
_animations: dict[str, object] = {}


def _animation(path: str):
    entry = _animations.get(path)
    if entry is None:
        from rlottie_python import LottieAnimation

        anim = LottieAnimation.from_file(str(path))
        total = int(anim.lottie_animation_get_totalframe() or 1)
        fps = float(anim.lottie_animation_get_framerate() or 30.0)
        size = anim.lottie_animation_get_size()
        aspect = (size[0] / size[1]) if size and size[1] else 1.0
        entry = {"anim": anim, "total": total, "fps": fps,
                 "aspect": aspect, "frames": {}}
        _animations[path] = entry
    return entry


def lottie_info(path: str) -> dict | None:
    """``{total, fps, aspect}`` of an animation, or None when unreadable."""
    try:
        entry = _animation(path)
    except Exception:
        log.exception("Unreadable Lottie sticker: %s", path)
        return None
    return {"total": entry["total"], "fps": entry["fps"],
            "aspect": entry["aspect"]}


def render_lottie_frame(path: str, height_px: int,
                        frame_index: int) -> np.ndarray | None:
    """One animation frame as straight RGBA, cached per (size, index)."""
    try:
        entry = _animation(path)
    except Exception:
        log.exception("Unreadable Lottie sticker: %s", path)
        return None
    height_px = max(2, min(_MAX_HEIGHT, int(height_px)))
    frame_index = int(frame_index) % max(1, entry["total"])
    key = (height_px, frame_index)
    cached = entry["frames"].get(key)
    if cached is not None:
        return cached

    width_px = max(2, int(round(height_px * entry["aspect"])))
    buffer = entry["anim"].lottie_animation_render(
        frame_num=frame_index, width=width_px, height=height_px)
    bgra = np.frombuffer(buffer, dtype=np.uint8).reshape(
        height_px, width_px, 4).astype(np.float32)
    # rlottie hands back PREMULTIPLIED BGRA; the compositor wants straight
    # RGBA. Un-premultiply once here, cached forever.
    alpha = bgra[..., 3:4]
    scale = np.divide(255.0, alpha, out=np.zeros_like(alpha),
                      where=alpha > 0)
    rgba = np.empty((height_px, width_px, 4), dtype=np.uint8)
    rgba[..., 0] = np.clip(bgra[..., 2] * scale[..., 0], 0, 255)
    rgba[..., 1] = np.clip(bgra[..., 1] * scale[..., 0], 0, 255)
    rgba[..., 2] = np.clip(bgra[..., 0] * scale[..., 0], 0, 255)
    rgba[..., 3] = alpha[..., 0]

    entry["frames"][key] = rgba
    # A runaway zoom session must not hoard hundreds of megabytes.
    if len(entry["frames"]) > 512:
        entry["frames"].clear()
    return rgba


def _rotate_rgba(rgba: np.ndarray, rotation: float) -> np.ndarray:
    """Rotate a straight-RGBA array; the bounding box grows to fit.

    Used for ANIMATED sprites, whose frames are cached unrotated (caching
    every angle a rotation drag passes through would hoard memory for
    variants never shown again). ~0.5 ms at sticker sizes.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QTransform

    h, w = rgba.shape[:2]
    image = QImage(rgba.tobytes(), w, h, w * 4,
                   QImage.Format.Format_RGBA8888)
    image = image.transformed(QTransform().rotate(float(rotation)),
                              Qt.TransformationMode.SmoothTransformation)
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = image.width(), image.height()
    data = image.constBits().tobytes()
    return np.frombuffer(data, dtype=np.uint8).reshape(
        height, image.bytesPerLine() // 4, 4)[:, :width].copy()


def sprite_aspect(path: str, kind: str = "static") -> float:
    """Width / height of a sticker's graphic, for the on-video handles."""
    if kind == "animated":
        info = lottie_info(path)
        return float(info["aspect"]) if info else 1.0
    from PySide6.QtGui import QImage
    from PySide6.QtSvg import QSvgRenderer

    if Path(path).suffix.lower() == ".svg":
        renderer = QSvgRenderer(str(path))
        size = renderer.defaultSize() if renderer.isValid() else None
        if size is not None and size.height() > 0:
            return size.width() / size.height()
        return 1.0
    image = QImage(str(path))
    if image.isNull() or image.height() == 0:
        return 1.0
    return image.width() / image.height()


# ── the bridge to the engine ─────────────────────────────────────────

def attach_sprites(spans: list[dict]) -> list[dict]:
    """Give each sticker span its ``sprite`` closure, IN PLACE.

    A span is ``{path, kind, scale, rotation, ...}`` (times untouched).
    The closure signature the engine's Overlays filter calls is
    ``sprite(canvas_h_px, local_seconds) -> RGBA array | None``.

    The closure reads ``scale`` and ``rotation`` from the span dict at
    CALL time, and the sprite is attached on the caller's own dict, not
    a copy: that is what lets the transport mutate a span while the user
    drags a handle on the preview and have the very next pulled frame
    composite at the new place - no graph rebuild, no undo entry. The
    committed action still rebuilds; this is only the live path.
    Returns the usable spans (a span whose file is gone is dropped).
    """
    out = []
    for span in spans or []:
        path = str(span.get("path") or "")
        kind = str(span.get("kind") or "static")
        if not path or not Path(path).is_file():
            log.warning("Sticker span without a usable file skipped (%s)", path)
            continue

        if kind == "animated":
            def sprite(canvas_h, seconds, _path=path, _span=span):
                info = lottie_info(_path)
                if info is None:
                    return None
                index = int(seconds * info["fps"])
                scale = float(_span.get("scale") or 0.3)
                arr = render_lottie_frame(
                    _path, int(round(canvas_h * scale)), index)
                rotation = float(_span.get("rotation") or 0.0)
                if arr is not None and abs(rotation) > 0.01:
                    arr = _rotate_rgba(arr, rotation)
                return arr
        else:
            cache: dict = {}

            def sprite(canvas_h, seconds, _path=path, _span=span,
                       _cache=cache):
                scale = float(_span.get("scale") or 0.3)
                rotation = round(float(_span.get("rotation") or 0.0), 1)
                height = int(round(canvas_h * scale))
                key = (height, rotation)
                arr = _cache.get(key)
                if arr is None:
                    arr = render_static(_path, height, rotation)
                    _cache[key] = arr
                    # A rotation drag sweeps hundreds of angles; keep the
                    # cache from hoarding every one it passed through.
                    if len(_cache) > 64:
                        _cache.clear()
                        _cache[key] = arr
                return arr

        span["sprite"] = sprite
        out.append(span)
    return out
