"""Subject segmentation: which pixels are THE SUBJECT, which the scene.

The shared ingredient of every masked effect (aura around a person,
blurred or moving background, selective colour): a per-frame soft mask
of the salient subject. The model is class-free on purpose - it cuts
out "the thing in evidence", be it a person, an animal or an object,
which is exactly the promise of the Effects panel.

Model: U²-Net small (``u2netp``, ~4.6 MB, Apache-2.0; ONNX conversion
by rembg, MIT), catalogued in ive/ai/model_registry.py and downloaded
on explicit request like every model. Runs on ONNX Runtime; providers
are chosen at runtime - DirectML when the wheel offers it (measured on
the dev machine: 34 ms a frame vs 446 on CPU), plain CPU otherwise.

The engine never imports this package: the graph builder attaches a
mask closure (Fase B), the same arrangement sprites have. This module
is Qt-free.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

from ive.ai.model_registry import is_installed, model_dir

log = logging.getLogger(__name__)

__all__ = ["SubjectSegmenter", "availability", "MODEL_ID",
           "mask_provider", "shared_segmenter", "warm_up"]

#: The one catalogued segmentation model (universal, class-free).
MODEL_ID = "u2netp"

#: The network's fixed input side (u2netp is exported at 320x320).
_INPUT_SIDE = 320

#: ImageNet statistics the network was trained against.
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def availability(model_id: str = MODEL_ID) -> str:
    """"ready" | "model_missing" | "backend_missing".

    A missing model is a STATE, never an error (docs/AI_FEATURES.md):
    the caller shows an invitation to download, not a traceback.
    """
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return "backend_missing"
    return "ready" if is_installed(model_id) else "model_missing"


def _resize(image: np.ndarray, width: int, height: int,
            *, shrinking: bool) -> np.ndarray:
    """cv2 when present (SIMD, area/linear), nearest-gather otherwise."""
    try:
        import cv2
        interp = cv2.INTER_AREA if shrinking else cv2.INTER_LINEAR
        return cv2.resize(image, (width, height), interpolation=interp)
    except ImportError:
        ih, iw = image.shape[:2]
        ys = (np.arange(height) * ih // height).clip(0, ih - 1)
        xs = (np.arange(width) * iw // width).clip(0, iw - 1)
        return image[ys][:, xs]


class SubjectSegmenter:
    """One loaded model, many masks.

    The session is created lazily on first use and kept; creation is
    locked, ``run`` itself is thread-safe by ONNX Runtime's own
    contract, so one instance can serve whoever asks. Keep ONE
    instance per process (sessions are expensive); the app owns it the
    way it owns the ProxyManager.
    """

    def __init__(self, model_id: str = MODEL_ID) -> None:
        self._model_id = str(model_id)
        self._session = None
        self._input_name = ""
        self._provider = ""
        self._lock = threading.Lock()

    @property
    def provider(self) -> str:
        """The execution provider actually in use ("" until first run)."""
        return self._provider

    def _ensure_session(self):
        with self._lock:
            if self._session is not None:
                return self._session
            state = availability(self._model_id)
            if state != "ready":
                raise RuntimeError(f"Segmentation not available: {state}")
            import onnxruntime as ort

            path = model_dir(self._model_id) / "u2netp.onnx"
            preferred = [p for p in ("DmlExecutionProvider",
                                     "CPUExecutionProvider")
                         if p in ort.get_available_providers()]
            session = ort.InferenceSession(str(path), providers=preferred)
            self._input_name = session.get_inputs()[0].name
            self._provider = session.get_providers()[0]
            log.info("Segmentation model %s loaded (%s)",
                     self._model_id, self._provider)
            self._session = session
            return session

    def mask(self, image: np.ndarray,
             size: tuple[int, int] | None = None) -> np.ndarray:
        """The subject mask of one RGB888 frame.

        Returns uint8, 0 = scene, 255 = subject, soft edges in between.
        ``size`` is the wanted (width, height); None returns the mask
        at the frame's own size. The heavy work always happens at the
        network's fixed 320x320, whatever the frame size.
        """
        session = self._ensure_session()
        if image.ndim != 3 or image.shape[2] < 3:
            raise ValueError(f"Expected an RGB frame, got {image.shape}")

        small = _resize(image[..., :3], _INPUT_SIDE, _INPUT_SIDE,
                        shrinking=True)
        work = (small.astype(np.float32) / 255.0 - _MEAN) / _STD
        batch = work.transpose(2, 0, 1)[None]
        # First output is the fused, finest prediction map.
        raw = session.run(None, {self._input_name: batch})[0][0, 0]
        # Min-max normalisation, the reference U²-Net post-process: the
        # logits' absolute range drifts per image, their ORDER does not.
        low, high = float(raw.min()), float(raw.max())
        raw = (raw - low) / max(1e-6, high - low)
        mask = (raw * 255.0).astype(np.uint8)

        if size is None:
            height, width = image.shape[:2]
        else:
            width, height = int(size[0]), int(size[1])
        if (width, height) != (_INPUT_SIDE, _INPUT_SIDE):
            mask = _resize(mask, width, height,
                           shrinking=width < _INPUT_SIDE)
        return mask

    def close(self) -> None:
        with self._lock:
            self._session = None
            self._provider = ""


#: The one segmenter of the process (sessions are expensive; ONNX
#: Runtime's ``run`` is thread-safe, so sharing is the right shape).
_shared: SubjectSegmenter | None = None
_shared_lock = threading.Lock()


def shared_segmenter() -> SubjectSegmenter:
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = SubjectSegmenter()
        return _shared


def warm_up() -> None:
    """Load the session in the background, so the first real mask does
    not stall the read-ahead for seconds (measured ~3-4 s on DirectML).

    Fire-and-forget: called when a subject effect enters the timeline.
    Not ready (model missing) or already warm both cost nothing.
    """
    if availability() != "ready":
        return

    def load() -> None:
        try:
            shared_segmenter()._ensure_session()
        except Exception:
            log.exception("Segmentation warm-up failed (masks will "
                          "retry on demand)")

    threading.Thread(target=load, name="segmentation-warmup",
                     daemon=True).start()


def mask_provider(cache_size: int = 32):
    """The callable the engine's ``set_mask_provider`` wants.

    ``fn(rgb) -> uint8 mask | None`` - None while the model is not
    installed (checked per call, so a download taken mid-session starts
    answering without a restart). One shared segmenter, created on the
    first ready call.

    A small LRU keyed by a cheap frame fingerprint (the bytes of an 8x8
    average) absorbs the common repeats - the paused frame re-composited
    during a drag, a thumbnail asked twice - without hashing megabytes.
    Uses the process-wide shared segmenter, so a warm_up() call has
    already paid the session load by the time frames arrive.
    """
    cache: dict[bytes, np.ndarray] = {}

    def fingerprint(image: np.ndarray) -> bytes:
        h, w = image.shape[:2]
        ys = (np.arange(8) * h // 8).clip(0, h - 1)
        xs = (np.arange(8) * w // 8).clip(0, w - 1)
        return image[ys][:, xs].tobytes() + bytes([h % 251, w % 251])

    def provide(image: np.ndarray):
        if availability() != "ready":
            return None
        key = fingerprint(image)
        hit = cache.get(key)
        if hit is not None:
            return hit
        mask = shared_segmenter().mask(image)
        if len(cache) >= cache_size:
            cache.clear()
        cache[key] = mask
        return mask

    return provide
