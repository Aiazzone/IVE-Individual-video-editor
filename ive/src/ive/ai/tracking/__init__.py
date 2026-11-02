"""Motion tracking: an overlay follows something in the video.

The user draws a box around a target on the preview; the target is
followed through the A/V clip underneath and the path lands on the
overlay (sticker or title) as ordinary keyframes - editable, re-
trackable over a stretch, one Ctrl+Z (docs/AI_FEATURES.md §7).

Engines (tracker.py): VitTrack, the quality level (follows size too,
reports confidence; ~0.7 MB, downloaded on request like every model),
and OpenCV's MIL as the always-present baseline (position only). A
missing model is a STATE: tracking still works, at baseline.

Qt-free. The engine never imports this package; ive/ui/tracking_service
runs the task on a worker thread and hands the result to the project.
"""

from ive.ai.tracking.mapping import CanvasMap
from ive.ai.tracking.task import (TrackingCancelled, TrackingError,
                                  track_overlay)
from ive.ai.tracking.tracker import (MODEL_ID, ObjectTracker, availability,
                                     best_engine)

__all__ = ["track_overlay", "TrackingError", "TrackingCancelled",
           "ObjectTracker", "CanvasMap", "availability", "best_engine",
           "MODEL_ID"]
