"""From a transition recipe to an engine blender, luma files included.

This is the ONE place that reads a luma PNG from disk (with QImage, so
the engine never imports Qt) and turns a recipe payload into an
:class:`ive.engine.transitions.Blender`. Same division of labour as the
sticker sprites: the transport and the export worker call
:func:`attach_blenders` on PURE-DATA spans - a blender is not
serialisable and must never cross a thread boundary.

Loaded maps are cached per (path, mtime): a wipe used on ten cuts reads
its PNG once.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

__all__ = ["attach_blenders", "load_luma"]

_maps: dict[tuple[str, int], np.ndarray] = {}


def load_luma(path: str) -> np.ndarray | None:
    """A greyscale map from an image file, cached per (path, mtime)."""
    try:
        mtime = int(os.path.getmtime(path))
    except OSError:
        log.warning("Luma map missing: %s", path)
        return None
    key = (str(path), mtime)
    cached = _maps.get(key)
    if cached is not None:
        return cached

    from PySide6.QtGui import QImage

    image = QImage(str(path))
    if image.isNull():
        log.warning("Unreadable luma map: %s", path)
        return None
    image = image.convertToFormat(QImage.Format.Format_Grayscale8)
    width, height = image.width(), image.height()
    data = image.constBits().tobytes()
    array = np.frombuffer(data, dtype=np.uint8).reshape(
        height, image.bytesPerLine())[:, :width].copy()
    _maps[key] = array
    if len(_maps) > 64:
        _maps.clear()
        _maps[key] = array
    return array


def attach_blenders(spans: list[dict]) -> list[dict]:
    """Give each transition span its ``blender``, IN PLACE.

    A span is ``{start, end, payload: {kind, ...}, easing}`` in seconds.
    Returns the usable spans; one whose map cannot be loaded (or whose
    kind is unknown) is dropped with a warning and its cut plays plain -
    a deleted user file must never break playback.
    """
    from ive.engine.transitions import make_blender

    out = []
    for span in spans or []:
        payload = dict(span.get("payload") or {})
        if payload.get("kind") == "luma":
            map_u8 = load_luma(str(payload.get("file") or ""))
            if map_u8 is None:
                continue
            payload["map"] = map_u8
        blender = make_blender(payload)
        if blender is None:
            continue
        span["blender"] = blender
        out.append(span)
    return out
