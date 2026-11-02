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
import math
import time
from typing import Callable

from ive.ai.tracking.mapping import CanvasMap
from ive.ai.tracking.path import overlay_samples
from ive.ai.tracking.tracker import ObjectTracker

log = logging.getLogger(__name__)

__all__ = ["track_overlay", "TrackingError", "TrackingCancelled",
           "ANALYSIS_HEIGHT", "DIRECTIONS"]

#: Frames are analysed at this height (never upscaled).
ANALYSIS_HEIGHT = 480

#: "forward" to the end of the shot, "backward" to its start, or both.
DIRECTIONS = ("forward", "backward", "both")

#: Frames decoded per seek when reading backwards (see _backward).
BACK_CHUNK = 64

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


def _backward(decoder, start: int, stop: int, chunk: int = 0):
    """Frames ``start, start-1, ..., stop`` (descending), cheaply.

    A decoder reads forwards; one frame back costs a seek plus a decode
    from the previous keyframe. So the stretch is read in CHUNKS: one
    seek per chunk, a forward decode of it into memory, handed out in
    reverse. Memory is bounded by the chunk (480p: ~60 MB for 64).
    """
    chunk = int(chunk or BACK_CHUNK)
    end = start
    while end >= stop:
        begin = max(stop, end - chunk + 1)
        frames = []
        for index in range(begin, end + 1):
            frame = decoder.frame_at(index)
            if frame is None:
                break
            frames.append((index, frame.array))
        for index, array in reversed(frames):
            yield index, array
        end = begin - 1


def track_overlay(av: dict, overlay: dict, box: dict, at: float, *,
                  canvas_aspect: float, fit: str = "fit",
                  direction: str = "forward",
                  since: float | None = None, until: float | None = None,
                  follow_size: bool = True, engine: str = "",
                  progress: Callable[[float], None] | None = None,
                  cancelled: Callable[[], bool] | None = None) -> dict:
    """Follow ``box`` drawn at timeline second ``at``; return the pins.

    ``box`` is ``{"x", "y", "w", "h"}`` in canvas fractions, (x, y) the
    TOP-LEFT corner. ``direction`` is "forward" (to the end of the
    shot), "backward" (to its start) or "both"; ``since``/``until``
    narrow the window (a partial re-track). Each direction runs its own
    tracker from the box and stops on its own when the target is lost.
    The overlay keeps the relation to the target it has AT ``at``.
    Result::

        {"clip_id", "samples", "t0", "t1" (clip-local window to
         rewrite), "engine", "follows_size", "frames", "lost_at" /
         "lost_before" (timeline s where each direction lost the
         target, or None), "seconds"}
    """
    from ive.media.decoder import VideoDecoder

    direction = direction if direction in DIRECTIONS else "forward"
    forward = direction in ("forward", "both")
    backward = direction in ("backward", "both")
    began = time.perf_counter()
    av_start = float(av.get("start", 0.0))
    av_end = av_start + float(av.get("duration", 0.0))
    ov_start = float(overlay.get("start", 0.0))
    ov_end = ov_start + float(overlay.get("duration", 0.0))
    lo = max(av_start, ov_start)
    hi = min(av_end, ov_end)
    if since is not None:
        lo = max(lo, float(since))
    if until is not None:
        hi = min(hi, float(until))
    at = max(float(at), lo)
    if not (hi > lo and lo <= at < hi):
        raise TrackingError("no_overlap")

    speed = float(av.get("speed", 1.0) or 1.0)
    source_in = float(av.get("sourceIn", 0.0))
    path = str(av.get("path") or "")
    log.info("Tracking %s for overlay %s %s from %.2fs (%.2f-%.2fs) of %s",
             av.get("id"), overlay.get("id"), direction, at, lo, hi, path)
    try:
        decoder = VideoDecoder(path)
    except Exception as exc:
        log.error("Tracking: cannot open %s", path, exc_info=True)
        raise TrackingError("media", str(exc)) from exc

    try:
        # TRUNCATED frame numbers, the transport's convention: the frame
        # shown at an instant is the one that started at or before it.
        # The window's FIRST frame rounds up instead, so the backward
        # pass never steps before the clip's own head.
        fps = decoder.fps

        def source_frame(t: float) -> float:
            return (source_in + (t - av_start) * speed) * fps

        anchor = int(source_frame(at) + 1e-6)
        first = max(0, math.ceil(source_frame(lo) - 1e-6))
        last = min(int(source_frame(hi) + 1e-6), decoder.frame_count - 1)
        n_fwd = max(0, last - anchor) if forward else 0
        n_back = max(0, anchor - first) if backward else 0
        if n_fwd + n_back < 1:
            raise TrackingError("too_short")

        width, height = decoder.video.display_size
        if height > ANALYSIS_HEIGHT and not decoder.video.rotation:
            decoder.set_output_size(
                int(round(ANALYSIS_HEIGHT * width / height)) & ~1,
                ANALYSIS_HEIGHT)

        def timeline_time(index: int) -> float:
            return av_start + (decoder.frame_to_time(index)
                               - source_in) / speed

        frame = decoder.frame_at(anchor)
        if frame is None:
            raise TrackingError("media", "no frame at the box")
        start_image = frame.array
        ih, iw = start_image.shape[:2]
        aspect = iw / max(1, ih)
        static_map = None if av.get("keyframes") else _clip_map(
            av, 0.0, aspect, canvas_aspect, fit)

        def map_at(t: float) -> CanvasMap:
            return static_map or _clip_map(av, t - av_start, aspect,
                                           canvas_aspect, fit)

        # The drawn box, canvas -> source pixels (axis-aligned in the
        # source; a rotated placement is approximated by its centre).
        mapping = map_at(timeline_time(anchor))
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
        start_box = (u * iw - px_w / 2.0, v * ih - px_h / 2.0, px_w, px_h)

        def new_tracker() -> ObjectTracker:
            try:
                tracker = ObjectTracker(engine)
            except Exception as exc:
                raise TrackingError("no_engine", str(exc)) from exc
            tracker.start(start_image, start_box)
            return tracker

        def observe(index: int, b: tuple) -> dict:
            t = timeline_time(index)
            m = map_at(t)
            cx, cy = m.to_canvas((b[0] + b[2] / 2.0) / iw,
                                 (b[1] + b[3] / 2.0) / ih)
            return {"t": t, "cx": cx, "cy": cy,
                    "h": m.height_to_canvas(b[3] / ih)}

        total = n_fwd + n_back
        done = 0

        def follow(frames):
            """One direction: its own tracker, its own loss."""
            nonlocal done
            tracker = new_tracker()
            seen = []
            for index, image in frames:
                if cancelled is not None and cancelled():
                    raise TrackingCancelled()
                state, b = tracker.step(image)
                if state == "lost":
                    return seen, timeline_time(index), tracker
                if state == "ok":
                    seen.append(observe(index, b))
                done += 1
                if progress is not None:
                    progress(done / total)
            return seen, None, tracker

        def forward_frames():
            for index in range(anchor + 1, anchor + n_fwd + 1):
                f = decoder.frame_at(index)
                if f is None:
                    return
                yield index, f.array

        ahead, lost_at, tracker = [], None, None
        behind, lost_before = [], None
        if n_fwd:
            ahead, lost_at, tracker = follow(forward_frames())
        if n_back:
            behind, lost_before, back_tracker = follow(
                _backward(decoder, anchor - 1, anchor - n_back))
            tracker = tracker or back_tracker
        follows = bool(follow_size and tracker.follows_size)
        origin = observe(anchor, start_box)
    finally:
        decoder.close()

    if not ahead and not behind:
        raise TrackingError("lost_at_start")
    observations = list(reversed(behind)) + [origin] + ahead
    anchor_local = origin["t"] - ov_start
    values = _values(overlay, anchor_local, {
        "x": float(overlay.get("x", 0.5)), "y": float(overlay.get("y", 0.5)),
        "scale": float(overlay.get("scale", 0.3))})
    samples = overlay_samples(observations, values, canvas_aspect,
                              ov_start, follow_size=follows,
                              anchor_index=len(behind))
    seconds = time.perf_counter() - began
    log.info("Tracking done (%s, %s): %d frames, %d pins, %.1fs%s%s",
             tracker.engine, direction, len(observations), len(samples),
             seconds,
             f", lost at {lost_at:.2f}s" if lost_at else "",
             f", lost before {lost_before:.2f}s" if lost_before else "")
    return {
        "clip_id": str(overlay.get("id") or ""),
        "samples": samples,
        "t0": round(observations[0]["t"] - ov_start, 4),
        "t1": round(observations[-1]["t"] - ov_start, 4),
        "engine": tracker.engine,
        "follows_size": follows,
        "frames": len(observations),
        "lost_at": lost_at,
        "lost_before": lost_before,
        "seconds": seconds,
    }
