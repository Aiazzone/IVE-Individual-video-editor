"""One box, followed frame after frame: the OpenCV trackers behind a
single small interface.

Two engines, chosen at runtime:

* ``vit``  - OpenCV's TrackerVit with the VitTrack weights (~0.7 MB,
  Apache-2.0, ive/ai/model_registry.py). Follows position AND size,
  reports a confidence score, ~16 ms a frame on CPU (measured on the
  dev machine, 640x360). The quality level.
* ``mil``  - OpenCV's TrackerMIL: classic, no weights, always there.
  Position only (its box never changes size) and no score - it is the
  baseline docs/AI_FEATURES.md §7 asks for, so tracking works before
  any download. CSRT/KCF would be better baselines but live in
  opencv-contrib, which the project does not ship.

Boxes are ``(x, y, w, h)`` in the pixels of the frames handed in. The
caller decides the frame size; the tracker never resizes.
"""

from __future__ import annotations

import logging

import numpy as np

from ive.ai.model_registry import is_installed, model_dir

log = logging.getLogger(__name__)

__all__ = ["ObjectTracker", "availability", "best_engine", "MODEL_ID",
           "ENGINES"]

#: The catalogued tracking model.
MODEL_ID = "vittrack"
_MODEL_FILE = "object_tracking_vittrack_2023sep.onnx"

ENGINES = ("vit", "mil")

#: Below this ViT score the frame is a doubt; LOST_FRAMES doubts in a
#: row and the target is gone. One blurred frame must not end a track,
#: a second of nonsense must.
LOST_SCORE = 0.30
LOST_FRAMES = 4


def availability(model_id: str = MODEL_ID) -> str:
    """"ready" | "model_missing" | "backend_missing" for the ViT level.

    The MIL baseline only needs OpenCV itself, so "model_missing" still
    means tracking WORKS - at baseline quality.
    """
    try:
        import cv2
    except ImportError:
        return "backend_missing"
    if not hasattr(cv2, "TrackerVit_create"):
        return "backend_missing"
    return "ready" if is_installed(model_id) else "model_missing"


def best_engine() -> str:
    """The best engine available right now ("" = none at all)."""
    if availability() == "ready":
        return "vit"
    try:
        import cv2
    except ImportError:
        return ""
    return "mil" if hasattr(cv2, "TrackerMIL_create") else ""


class ObjectTracker:
    """A tracker for ONE target. Make a new one per track."""

    def __init__(self, engine: str = "") -> None:
        import cv2

        engine = str(engine or best_engine())
        if engine == "vit" and availability() != "ready":
            log.info("VitTrack not installed: tracking at MIL baseline")
            engine = "mil"
        if engine not in ENGINES:
            raise RuntimeError("No tracking engine available")
        if engine == "vit":
            params = cv2.TrackerVit_Params()
            params.net = str(model_dir(MODEL_ID) / _MODEL_FILE)
            self._tracker = cv2.TrackerVit_create(params)
        else:
            self._tracker = cv2.TrackerMIL_create()
        self.engine = engine
        self._doubts = 0
        #: Last frame's confidence, 0..1 (MIL: 1 while it reports ok).
        self.score = 1.0

    @property
    def follows_size(self) -> bool:
        """True when the box can grow and shrink with the target."""
        return self.engine == "vit"

    def start(self, image: np.ndarray, box: tuple) -> None:
        """Lock on ``box`` in ``image`` (RGB uint8)."""
        x, y, w, h = (int(round(v)) for v in box)
        ih, iw = image.shape[:2]
        x = max(0, min(iw - 2, x))
        y = max(0, min(ih - 2, y))
        w = max(2, min(iw - x, w))
        h = max(2, min(ih - y, h))
        self._tracker.init(_bgr(image), (x, y, w, h))
        self._doubts = 0
        self.score = 1.0

    def step(self, image: np.ndarray) -> tuple[str, tuple]:
        """Follow into the next frame.

        Returns ``(state, box)``: state "ok", "doubt" (this frame is
        unreliable - keep going, but do not trust the box) or "lost"
        (LOST_FRAMES doubts in a row: stop here).
        """
        ok, box = self._tracker.update(_bgr(image))
        if self.engine == "vit":
            self.score = float(self._tracker.getTrackingScore())
            ok = ok and self.score >= LOST_SCORE
        else:
            self.score = 1.0 if ok else 0.0
        if ok:
            self._doubts = 0
            return "ok", tuple(float(v) for v in box)
        self._doubts += 1
        state = "lost" if self._doubts >= LOST_FRAMES else "doubt"
        return state, tuple(float(v) for v in box)


def _bgr(image: np.ndarray) -> np.ndarray:
    """The decoder hands RGB; the OpenCV trackers were trained on BGR."""
    return np.ascontiguousarray(image[:, :, 2::-1])
