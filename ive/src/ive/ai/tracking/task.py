"""Track a box through an A/V clip and turn it into an overlay's path.

The whole job, Qt-free, on plain dicts (the clip dicts ProjectService
hands QML): the caller says which overlay should follow, the box the
user drew ON THE CANVAS at an instant, and the canvas the sequence
composites at. The task

1. clamps the window to where overlay and A/V clip overlap, from the
   box's instant forward (a cut is a new shot: tracking stops there);
2. decodes EVERY source frame of that stretch in order, small (480p is
   plenty for a tracker and keeps the decode cheap) - sequential reads
   never seek;
3. follows the box, stopping when the target is lost instead of
   producing garbage (docs/AI_FEATURES.md §7);
4. maps each trusted box to the canvas through the clip's crop and fit
   or placement (mapping.py), then to the overlay's pins (path.py).

It returns the pins; it never touches the project. Laying them down is
ProjectService.apply_tracked_path - one Command, one Ctrl+Z.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from ive.ai.tracking.mapping import CanvasMap
from ive.ai.tracking.path import overlay_samples
from ive.ai.tracking.tracker import ObjectTracker

log = logging.getLogger(__name__)

__all__ = ["track_overlay", "TrackingError", "TrackingCancelled",
           "ANALYSIS_HEIGHT"]

#: Frames are analysed at this height (never upscaled).
ANALYSIS_HEIGHT = 480

#: A box smaller than this, in analysis pixels, has nothing to follow.
_MIN_BOX_PX = 8


class TrackingError(RuntimeError):
    """A refusal with a ``code`` the UI translates:
    ``no_overlap`` / ``too_short`` / ``box_outside`` / ``box_too_small``
    / ``no_engine`` / ``media`` / ``lost_at_start``."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


class TrackingCancelled(RuntimeError):
    """The user stopped the job; nothing is applied."""


def _values(clip: dict, local: float, defaults: dict) -> dict:
    keys = clip.get("keyframes") or []
    if not keys:
        return dict(defaults)
    from ive.utils.keyframes import evaluate

    return evaluate(keys, local, defaults)


def _clip_map(av: dict, local: float, source_aspect: float,
              canvas_aspect: float, fit: str) -> CanvasMap:
    values = _values(av, local, {
        "x": float(av.get("x", 0.5)), "y": float(av.get("y", 0.5)),
        "scale": float(av.get("scale", 1.0) or 1.0),
        "rotation": float(av.get("rotation", 0.0))})
    return CanvasMap(source_aspect, canvas_aspect, fit,
                     crop=av.get("crop") or {},
                     placed=bool(av.get("placed")),
                     x=values["x"], y=values["y"],
                     scale=values["scale"], rotation=values["rotation"])


def track_overlay(av: dict, overlay: dict, box: dict, at: float, *,
                  canvas_aspect: float, fit: str = "fit",
                  until: float | None = None, follow_size: bool = True,
                  engine: str = "",
                  progress: Callable[[float], None] | None = None,
                  cancelled: Callable[[], bool] | None = None) -> dict:
    """Follow ``box`` from timeline second ``at``; return the pins.

    ``box`` is ``{"x", "y", "w", "h"}`` in canvas fractions, (x, y) the
    TOP-LEFT corner, drawn at ``at``. Result::

        {"clip_id", "samples", "t0", "t1" (clip-local window to
         rewrite), "engine", "follows_size", "frames", "lost_at"
         (timeline s or None), "seconds"}
    """
    from ive.media.decoder import VideoDecoder

    began = time.perf_counter()
    av_start = float(av.get("start", 0.0))
    av_end = av_start + float(av.get("duration", 0.0))
    ov_start = float(overlay.get("start", 0.0))
    ov_end = ov_start + float(overlay.get("duration", 0.0))
    lo = max(float(at), av_start, ov_start)
    hi = min(av_end, ov_end)
    if until is not None:
        hi = min(hi, float(until))
    if not hi > lo:
        raise TrackingError("no_overlap")

    speed = float(av.get("speed", 1.0) or 1.0)
    source_in = float(av.get("sourceIn", 0.0))
    path = str(av.get("path") or "")
    log.info("Tracking %s for overlay %s: %.2f-%.2fs of %s",
             av.get("id"), overlay.get("id"), lo, hi, path)
    try:
        decoder = VideoDecoder(path)
    except Exception as exc:
        log.error("Tracking: cannot open %s", path, exc_info=True)
        raise TrackingError("media", str(exc)) from exc

    try:
        # TRUNCATED frame numbers, the transport's convention: the frame
        # shown at an instant is the one that started at or before it.
        fps = decoder.fps
        first = int((source_in + (lo - av_start) * speed) * fps + 1e-6)
        last = int((source_in + (hi - av_start) * speed) * fps + 1e-6)
        last = min(last, decoder.frame_count - 1)
        if last - first < 1:
            raise TrackingError("too_short")

        width, height = decoder.video.display_size
        if height > ANALYSIS_HEIGHT and not decoder.video.rotation:
            decoder.set_output_size(
                int(round(ANALYSIS_HEIGHT * width / height)) & ~1,
                ANALYSIS_HEIGHT)

        def timeline_time(index: int) -> float:
            return av_start + (decoder.frame_to_time(index)
                               - source_in) / speed

        frame = decoder.frame_at(first)
        if frame is None:
            raise TrackingError("media", "no frame at the start")
        ih, iw = frame.array.shape[:2]
        aspect = iw / max(1, ih)
        static_map = None if av.get("keyframes") else _clip_map(
            av, 0.0, aspect, canvas_aspect, fit)

        def map_at(t: float) -> CanvasMap:
            return static_map or _clip_map(av, t - av_start, aspect,
                                           canvas_aspect, fit)

        # The drawn box, canvas -> source pixels (axis-aligned in the
        # source; a rotated placement is approximated by its centre).
        mapping = map_at(timeline_time(first))
        bx, by = float(box["x"]), float(box["y"])
        bw, bh = float(box["w"]), float(box["h"])
        u, v = mapping.to_source(bx + bw / 2.0, by + bh / 2.0)
        su = mapping.width_to_source(bw)
        sv = mapping.height_to_source(bh)
        if not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0):
            raise TrackingError("box_outside")
        px_w, px_h = su * iw, sv * ih
        if min(px_w, px_h) < _MIN_BOX_PX:
            raise TrackingError("box_too_small")

        try:
            tracker = ObjectTracker(engine)
        except Exception as exc:
            raise TrackingError("no_engine", str(exc)) from exc
        tracker.start(frame.array, (u * iw - px_w / 2.0,
                                    v * ih - px_h / 2.0, px_w, px_h))
        follows = bool(follow_size and tracker.follows_size)

        def observe(index: int, b: tuple) -> dict:
            t = timeline_time(index)
            m = map_at(t)
            cx, cy = m.to_canvas((b[0] + b[2] / 2.0) / iw,
                                 (b[1] + b[3] / 2.0) / ih)
            return {"t": t, "cx": cx, "cy": cy,
                    "h": m.height_to_canvas(b[3] / ih)}

        observations = [observe(first, (u * iw - px_w / 2.0,
                                        v * ih - px_h / 2.0, px_w, px_h))]
        lost_at = None
        total = last - first
        for index in range(first + 1, last + 1):
            if cancelled is not None and cancelled():
                raise TrackingCancelled()
            frame = decoder.frame_at(index)
            if frame is None:
                break
            state, b = tracker.step(frame.array)
            if state == "lost":
                lost_at = timeline_time(index)
                break
            if state == "ok":
                observations.append(observe(index, b))
            if progress is not None:
                progress((index - first) / total)
    finally:
        decoder.close()

    if len(observations) < 2:
        raise TrackingError("lost_at_start")
    anchor_local = observations[0]["t"] - ov_start
    anchor = _values(overlay, anchor_local, {
        "x": float(overlay.get("x", 0.5)), "y": float(overlay.get("y", 0.5)),
        "scale": float(overlay.get("scale", 0.3))})
    samples = overlay_samples(observations, anchor, canvas_aspect,
                              ov_start, follow_size=follows)
    seconds = time.perf_counter() - began
    log.info("Tracking done (%s): %d frames, %d pins, %.1fs%s",
             tracker.engine, len(observations), len(samples), seconds,
             f", target lost at {lost_at:.2f}s" if lost_at else "")
    return {
        "clip_id": str(overlay.get("id") or ""),
        "samples": samples,
        "t0": round(anchor_local, 4),
        "t1": round(observations[-1]["t"] - ov_start, 4),
        "engine": tracker.engine,
        "follows_size": follows,
        "frames": len(observations),
        "lost_at": lost_at,
        "seconds": seconds,
    }
