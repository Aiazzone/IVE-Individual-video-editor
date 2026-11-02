"""The state machine behind "Track": run, progress, cancel, land.

The user picks an overlay, draws a box around a target on the preview
and asks for tracking; this service finds the A/V clip under the box's
instant, runs ive/ai/tracking on a worker thread (decode + tracker -
never the GUI thread, CLAUDE.md §4.8), and hands the pins to
ProjectService.apply_tracked_path on the GUI thread: one Command, one
Ctrl+Z. The worker never touches the model.

In-process on purpose: OpenCV's trackers have none of the OpenMP clash
that sent the subtitle worker to its own process.

Model download is not here: the AI Models tab already fetches any
catalogued model (VitTrack is one, ive/ai/model_registry.py). Without
it tracking still works, at the MIL baseline - ``engine`` says which.
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import Property, QObject, Signal, Slot

log = logging.getLogger(__name__)

__all__ = ["TrackingService"]


class TrackingService(QObject):
    """Run one track at a time; land it as keyframes."""

    stateChanged = Signal()
    runChanged = Signal()
    drawChanged = Signal()
    #: Pins landed on the overlay (count); 0 = nothing applied.
    finished = Signal(int)
    #: Worker -> GUI thread hand-off (queued: the service lives on GUI).
    _done = Signal("QVariantMap")
    _ticked = Signal(float)

    def __init__(self, project, playback, settings=None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._project = project
        self._settings = settings
        self._playback = playback
        self._running = False
        self._progress = 0.0
        self._error = ""
        self._last_pins = 0
        self._last_engine = ""
        self._lost_at = -1.0
        self._lost_before = -1.0
        self._drawing_for = ""
        #: Re-track with the clip's stored relation (track_ref) instead
        #: of measuring a new one off the current - maybe drifted - path.
        self._keep_relation = True
        self._reused = False
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._done.connect(self._on_done)
        self._ticked.connect(self._on_tick)

    # ── state ─────────────────────────────────────────────────────────

    @Property(str, notify=stateChanged)
    def state(self) -> str:
        """"ready" | "model_missing" (baseline only) | "backend_missing"."""
        from ive.ai.tracking import availability

        return availability()

    @Property(str, notify=stateChanged)
    def engine(self) -> str:
        """The engine a track would use now: "vit", "mil" or ""."""
        from ive.ai.tracking import best_engine

        return best_engine()

    @Slot()
    def refresh(self) -> None:
        """Re-read the model state (after a download or a removal)."""
        self.stateChanged.emit()

    @Property(bool, notify=runChanged)
    def running(self) -> bool:
        return self._running

    @Property(float, notify=runChanged)
    def progress(self) -> float:
        return self._progress

    @Property(str, notify=runChanged)
    def error(self) -> str:
        """The last refusal's code ("" = none); tracking.err.<code>."""
        return self._error

    @Property(int, notify=runChanged)
    def lastPins(self) -> int:
        return self._last_pins

    @Property(str, notify=runChanged)
    def lastEngine(self) -> str:
        return self._last_engine

    @Property(float, notify=runChanged)
    def lostAt(self) -> float:
        """Timeline second the target was lost at; -1 = followed to the end."""
        return self._lost_at

    @Property(float, notify=runChanged)
    def lostBefore(self) -> float:
        """Going BACKWARDS, the timeline second the target was lost at;
        -1 = followed to the start (or not tracked backwards)."""
        return self._lost_before

    def _direction(self) -> str:
        if self._settings is None:
            return "both"
        value = str(self._settings.get("ai.tracking_direction") or "both")
        return value if value in ("forward", "backward", "both") else "both"

    # ── the "draw the target" mode ────────────────────────────────────

    @Property(str, notify=drawChanged)
    def drawingFor(self) -> str:
        """The overlay waiting for its target box ("" = not drawing).

        Shared state between the panel that arms the mode and the
        preview layer that takes the box - neither owns the other.
        """
        return self._drawing_for

    @Slot(str)
    def begin_draw(self, overlay_id: str) -> None:
        if self._running:
            return
        self._drawing_for = str(overlay_id or "")
        self._error = ""
        self.drawChanged.emit()
        self.runChanged.emit()

    @Property(bool, notify=drawChanged)
    def keepRelation(self) -> bool:
        """A re-track keeps the overlay where it sat relative to the
        target (the clip's stored relation)."""
        return self._keep_relation

    @Slot(bool)
    def set_keep_relation(self, keep: bool) -> None:
        self._keep_relation = bool(keep)
        self.drawChanged.emit()

    @Property(bool, notify=runChanged)
    def lastReusedRelation(self) -> bool:
        """The last run laid the path with the stored relation."""
        return self._reused

    @Slot()
    def end_draw(self) -> None:
        if self._drawing_for:
            self._drawing_for = ""
            self.drawChanged.emit()

    # ── run ───────────────────────────────────────────────────────────

    def _clips(self) -> list[dict]:
        return list(self._project.timelineClips or [])

    def _fail(self, code: str) -> bool:
        self._error = code
        self.runChanged.emit()
        return False

    @Slot(str, "QVariantMap", float, result=bool)
    def track(self, overlay_id: str, box, at: float,
              follow_size: bool = True, direction: str = "",
              keep_relation: bool | None = None) -> bool:
        """Start following ``box`` (canvas fractions, top-left + size)
        drawn at timeline second ``at``; ``overlay_id`` follows it.
        ``direction`` "" = the ai.tracking_direction setting."""
        if self._running:
            return False
        self.end_draw()
        box = box.toVariant() if hasattr(box, "toVariant") else dict(box or {})
        clips = self._clips()
        overlay = next((c for c in clips if c.get("id") == overlay_id), None)
        if overlay is None or int(overlay.get("track") or 0) == 0 \
                or not (overlay.get("stickerId") or overlay.get("text")):
            return self._fail("not_overlay")
        at = float(at)
        av = next((c for c in clips
                   if int(c.get("track") or 0) == 0 and c.get("hasVideo")
                   and float(c["start"]) <= at
                   < float(c["start"]) + float(c["duration"])), None)
        if av is None:
            return self._fail("no_video")
        try:
            job = {"av": av, "overlay": overlay,
                   "box": {k: float(box[k]) for k in ("x", "y", "w", "h")},
                   "at": at,
                   "canvas_aspect": float(self._playback.canvas_aspect()),
                   "fit": str(self._playback.canvas_fit()),
                   "follow_size": bool(follow_size),
                   "direction": str(direction or self._direction()),
                   "relation": (dict(overlay.get("trackRef") or {})
                                if (self._keep_relation
                                    if keep_relation is None
                                    else keep_relation) else {})}
        except (KeyError, TypeError, ValueError):
            return self._fail("bad_box")

        self._cancel.clear()
        self._running = True
        self._progress = 0.0
        self._error = ""
        self._last_pins = 0
        self._lost_at = -1.0
        self._lost_before = -1.0
        self.runChanged.emit()
        self._thread = threading.Thread(target=self._run, args=(job,),
                                        name="ai-tracking", daemon=True)
        self._thread.start()
        return True

    def _run(self, job: dict) -> None:
        from ive.ai.tracking import (TrackingCancelled, TrackingError,
                                     track_overlay)

        outcome: dict = {}
        try:
            outcome = {"result": track_overlay(
                job["av"], job["overlay"], job["box"], job["at"],
                canvas_aspect=job["canvas_aspect"], fit=job["fit"],
                follow_size=job["follow_size"],
                direction=job["direction"],
                relation=job["relation"] or None,
                progress=self._ticked.emit,
                cancelled=self._cancel.is_set)}
        except TrackingCancelled:
            log.info("Tracking cancelled")
            outcome = {"error": "cancelled"}
        except TrackingError as exc:
            log.info("Tracking refused: %s", exc.code)
            outcome = {"error": exc.code}
        except Exception:
            log.error("Tracking failed", exc_info=True)
            outcome = {"error": "failed"}
        self._done.emit(outcome)

    def _on_tick(self, fraction: float) -> None:
        if fraction - self._progress >= 0.01 or fraction >= 1.0:
            self._progress = fraction
            self.runChanged.emit()

    def _on_done(self, outcome: dict) -> None:
        self._running = False
        self._thread = None
        result = outcome.get("result")
        landed = 0
        if result:
            self._last_engine = str(result.get("engine") or "")
            lost = result.get("lost_at")
            self._lost_at = float(lost) if lost is not None else -1.0
            lost = result.get("lost_before")
            self._lost_before = float(lost) if lost is not None else -1.0
            params = ("x", "y", "scale") if result.get("follows_size") \
                else ("x", "y")
            self._reused = bool(result.get("reused_relation"))
            if self._project.apply_tracked_path(
                    result["clip_id"], result["samples"],
                    float(result["t0"]), float(result["t1"]), params,
                    result.get("relation")):
                landed = len(result["samples"])
            elif any(c.get("id") == result["clip_id"] for c in self._clips()):
                # The clip is there and the path came out IDENTICAL (the
                # same box re-tracked): nothing to change, not a failure,
                # and no empty undo step.
                landed = len(result["samples"])
            else:
                self._error = "not_applied"
        else:
            self._error = str(outcome.get("error") or "failed")
        self._last_pins = landed
        self._progress = 1.0 if landed else 0.0
        self.runChanged.emit()
        self.finished.emit(landed)

    @Slot()
    def cancel(self) -> None:
        if self._running:
            self._cancel.set()

    def shutdown(self) -> None:
        """Stop a running track before the app tears down."""
        self._cancel.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=3.0)
