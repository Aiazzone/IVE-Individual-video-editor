"""Filters and transitions: pure functions over frames.

The rules come from docs/ENGINE.md and frame.py: a filter never learns where
the frame sits on the timeline or who asked for it, it returns a NEW frame
rather than mutating its input, and it must not force either lazy stack -
scaling the sound of a frame whose picture is never looked at must not
decode that picture. Every filter here wraps the source frame's callables,
so evaluation stays exactly as lazy as it was.

A `Transition` combines exactly two pictures; the tractor calls its
``blend`` with the composite so far, the track's picture, and the track
opacity as the mix position.
"""

from __future__ import annotations

import logging

import numpy as np

from ive.engine.frame import Frame

log = logging.getLogger(__name__)

__all__ = ["Filter", "Transition", "Gain", "Grayscale", "Opacity", "Dissolve",
           "ColorGrade", "TimedColor", "apply_colour_ops", "bake_lut"]

#: Rec.601 luma weights, shared by every op that needs "how bright is this".
_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)


def apply_colour_ops(array: np.ndarray, ops: list[dict],
                     vignette_cache: dict | None = None) -> np.ndarray:
    """Run a declarative colour recipe over one RGB888 frame.

    The recipe is DATA (a list of ``{"op": name, ...}`` dicts straight from
    an effect's JSON), which is what makes effects shareable files instead
    of code. Everything is vectorised numpy on a float32 working copy in
    [0, 1]; one clip conversion at the end.

    Supported ops - the primitive vocabulary recipes are written in:
      brightness(amount)   add, -1..1
      contrast(amount)     1 = untouched, pivot at mid grey
      saturation(amount)   0 = grayscale, 1 = untouched, >1 = more
      gamma(value)         exponent; <1 brightens the mids
      temperature(amount)  -1..1, warm positive (red up, blue down)
      tint(amount)         -1..1, magenta positive (green down)
      fade(amount)         lifts the blacks - the "old print" look
      vignette(strength)   darkened corners, mask cached per frame size
      matrix(m, offset?)   3x3 colour matrix + optional per-channel offset
    Unknown ops are skipped with a warning: a recipe written by a NEWER
    version must degrade, not blow up the timeline.
    """
    work = array.astype(np.float32) / 255.0
    for entry in ops or []:
        op = str(entry.get("op") or "")
        if op == "brightness":
            work += np.float32(entry.get("amount", 0.0))
        elif op == "contrast":
            amount = np.float32(entry.get("amount", 1.0))
            work = (work - 0.5) * amount + 0.5
        elif op == "saturation":
            amount = np.float32(entry.get("amount", 1.0))
            luma = (work @ _LUMA)[..., None]
            work = luma + (work - luma) * amount
        elif op == "gamma":
            value = float(entry.get("value", 1.0))
            if value > 0:
                np.clip(work, 0.0, 1.0, out=work)
                work = work ** np.float32(value)
        elif op == "temperature":
            amount = float(entry.get("amount", 0.0))
            work[..., 0] *= np.float32(1.0 + 0.25 * amount)
            work[..., 2] *= np.float32(1.0 - 0.25 * amount)
        elif op == "tint":
            amount = float(entry.get("amount", 0.0))
            work[..., 1] *= np.float32(1.0 - 0.2 * amount)
        elif op == "fade":
            amount = np.float32(entry.get("amount", 0.0))
            work = work + amount * 0.18 * (1.0 - work)
        elif op == "vignette":
            strength = float(entry.get("strength", 0.5))
            height, width = work.shape[:2]
            key = (width, height, round(strength, 3))
            mask = (vignette_cache or {}).get(key)
            if mask is None:
                ys = np.linspace(-1.0, 1.0, height, dtype=np.float32)[:, None]
                xs = np.linspace(-1.0, 1.0, width, dtype=np.float32)[None, :]
                distance = np.sqrt(xs * xs + ys * ys) / np.sqrt(2.0)
                mask = (1.0 - strength * distance ** 2)[..., None]
                if vignette_cache is not None:
                    vignette_cache[key] = mask
            work *= mask
        elif op == "matrix":
            m = np.array(entry.get("m") or np.eye(3), dtype=np.float32)
            offset = np.array(entry.get("offset") or (0, 0, 0), dtype=np.float32)
            work = work @ m.T + offset
        else:
            log.warning("Unknown colour op %r skipped", op)
        # EVERY op sees clipped input. This is the uint8-pipeline semantic
        # the accelerated paths (per-step cv2, baked LUT) implement by
        # construction; without it the three ways of running the same
        # recipe disagreed exactly on the brightest pixels.
        np.clip(work, 0.0, 1.0, out=work)
    return (work * 255.0).astype(np.uint8)


class Filter:
    """Base of every filter: ``process(frame) -> frame``, pure.

    The base class passes the frame through, so a subclass only overrides
    what it changes - usually via `_wrap`, which keeps both stacks lazy.
    """

    def process(self, frame: Frame) -> Frame:
        return frame

    @staticmethod
    def _wrap(frame: Frame, image_fn=None, audio_fn=None) -> Frame:
        """A new frame over ``frame`` with one stack transformed.

        The untouched stack is forwarded as the ORIGINAL callable, so
        asking for it later still evaluates the source lazily, once.
        """
        out = Frame(frame.position, frame.timebase, frame.audio_format,
                    image_fn=image_fn or frame.image,
                    audio_fn=audio_fn or frame.audio)
        out.properties = dict(frame.properties)
        return out


class Transition:
    """Combines exactly two pictures at mix position ``t`` in [0, 1]."""

    def blend(self, base: np.ndarray, top: np.ndarray, t: float) -> np.ndarray:
        raise NotImplementedError

    def process(self, a: Frame, b: Frame, t: float) -> Frame:
        """Frame-level convenience over ``blend``, lazily evaluated."""
        out = Frame(a.position, a.timebase, a.audio_format,
                    image_fn=lambda: self._blend_frames(a, b, t),
                    audio_fn=a.audio)
        out.properties = dict(a.properties)
        return out

    def _blend_frames(self, a: Frame, b: Frame, t: float):
        base, top = a.image(), b.image()
        if base is None:
            return top
        if top is None:
            return base
        return self.blend(base, top, t)


class Gain(Filter):
    """Scales a frame's audio. 0 mutes, 1 passes through, 2 doubles.

    The graph builder attaches one to a playlist entry when the clip's
    volume is not 1 - per ENTRY, not per producer: two clips cut from the
    same file share a producer but each keeps its own loudness.
    """

    def __init__(self, gain: float) -> None:
        self.gain = float(gain)

    def process(self, frame: Frame) -> Frame:
        gain = self.gain
        if abs(gain - 1.0) < 1e-6:
            return frame

        def scaled():
            if gain <= 0.0:
                # Muted is not "decode, then multiply by zero": the sound
                # never needs decoding at all.
                return frame.silence()
            audio = frame.audio()
            if audio is None:
                return None
            # float32 * python float promotes to float64; multiplying by a
            # numpy scalar keeps the engine format.
            return audio * np.float32(gain)

        return self._wrap(frame, audio_fn=scaled)


class Grayscale(Filter):
    """Rec.601 luma, kept as three channels so nothing downstream changes."""

    def process(self, frame: Frame) -> Frame:
        def gray():
            image = frame.image()
            if image is None:
                return None
            luma = (image[..., 0] * 0.299 + image[..., 1] * 0.587
                    + image[..., 2] * 0.114).astype(np.uint8)
            return np.repeat(luma[..., None], 3, axis=2)

        return self._wrap(frame, image_fn=gray)


class Opacity(Filter):
    """Fades the picture towards black by ``alpha`` in [0, 1]."""

    def __init__(self, alpha: float) -> None:
        self.alpha = min(1.0, max(0.0, float(alpha)))

    def process(self, frame: Frame) -> Frame:
        alpha = self.alpha
        if alpha >= 1.0:
            return frame

        def faded():
            image = frame.image()
            if image is None:
                return None
            return (image.astype(np.float32) * alpha).astype(np.uint8)

        return self._wrap(frame, image_fn=faded)


class Dissolve(Transition):
    """The plain crossfade: linear mix of the two pictures."""

    def blend(self, base: np.ndarray, top: np.ndarray, t: float) -> np.ndarray:
        if t <= 0.0:
            return base
        if t >= 1.0:
            return top
        return (base.astype(np.float32) * (1.0 - t)
                + top.astype(np.float32) * t).astype(np.uint8)


#: Lattice size of the baked 3D LUT. 65 points per axis keeps the nearest-
#: neighbour quantisation error at most 2/255 per channel - invisible - and
#: the table at 65^3 x 3 bytes = 800 KB.
_LUT_SIZE = 65


def bake_lut(ops: list[dict], size: int = _LUT_SIZE) -> np.ndarray:
    """Bake a colour recipe into a 3D LUT.

    Running the op chain per frame is float math over two million pixels
    several times over - which is exactly the stutter it produced. The
    standard trick (FFmpeg's lut3d, every grading tool): evaluate the chain
    ONCE over a small lattice of colours, then each frame is a single
    vectorised table lookup. Spatial ops (vignette) cannot live in a LUT
    and are applied separately.
    """
    ramp = np.linspace(0, 255, size).round().astype(np.uint8)
    r, g, b = np.meshgrid(ramp, ramp, ramp, indexing="ij")
    lattice = np.stack([r, g, b], axis=-1).reshape(size * size, size, 3)
    colour_only = [op for op in ops or [] if op.get("op") != "vignette"]
    graded = apply_colour_ops(lattice, colour_only, None)
    return np.ascontiguousarray(graded.reshape(size, size, size, 3))


#: Ops whose output channel depends only on the SAME input channel; a run
#: of them collapses into one 256-entry curve per channel.
_PER_CHANNEL_OPS = frozenset(
    {"brightness", "contrast", "gamma", "temperature", "tint", "fade"})


class ColorGrade(Filter):
    """A declarative colour recipe over the picture, lazily as ever.

    On first use the recipe is COMPILED: runs of per-channel ops fuse into
    one ``cv2.LUT`` curve, colour matrices (saturation included - it IS a
    matrix towards luma) compose into one ``cv2.transform``, and a vignette
    becomes one masked multiply. A typical look runs in a handful of C
    calls per frame - the numpy op chain took over 100 ms at 720p, which
    is the stutter this replaces. Without OpenCV the fallback is a baked
    3D LUT, still several times faster than the chain.
    """

    def __init__(self, ops: list[dict]) -> None:
        self.ops = list(ops or [])
        self._vignette_strengths = [
            float(op.get("strength", 0.5))
            for op in self.ops if op.get("op") == "vignette"
        ]
        self._has_colour = any(op.get("op") != "vignette" for op in self.ops)
        #: Compiled cv2 step list; None = not compiled yet, False = no cv2.
        self._cv2 = None
        self._steps: list | None | bool = None
        #: Fallback: LUT flattened to (N^3, 3) plus three 256-entry stride
        #: tables - three tiny gathers, two adds, one flat gather.
        self._flat_lut: np.ndarray | None = None
        self._stride_r: np.ndarray | None = None
        self._stride_g: np.ndarray | None = None
        self._stride_b: np.ndarray | None = None
        #: Fixed-point (x256) radial masks, cached per frame size.
        self._masks: dict = {}
        #: cv2 vignette masks (uint8, 255-based), cached per frame size.
        self._masks_u8: dict = {}

    # ── the cv2 compiler ──────────────────────────────────────────────

    def _compile(self) -> None:
        try:
            import cv2
        except ImportError:
            self._steps = False
            return
        self._cv2 = cv2

        steps: list = []
        pending: list[dict] = []
        matrix: tuple[np.ndarray, np.ndarray] | None = None

        def flush_pending() -> None:
            nonlocal pending
            if not pending:
                return
            # Evaluate the per-channel run ONCE over a ramp; because these
            # ops never mix channels, the ramp image r=g=b=v yields each
            # channel's own curve.
            ramp = np.arange(256, dtype=np.uint8)
            image = np.stack([ramp, ramp, ramp], axis=-1).reshape(1, 256, 3)
            steps.append(("lut", apply_colour_ops(image, pending, None)))
            pending = []

        def flush_matrix() -> None:
            nonlocal matrix
            if matrix is None:
                return
            m, offset = matrix
            steps.append(("matrix",
                          np.hstack([m, offset[:, None]]).astype(np.float32)))
            matrix = None

        for op in self.ops:
            name = str(op.get("op") or "")
            if name in _PER_CHANNEL_OPS:
                flush_matrix()
                pending.append(op)
            elif name in ("saturation", "matrix"):
                flush_pending()
                if name == "saturation":
                    s = float(op.get("amount", 1.0))
                    m = s * np.eye(3) + (1.0 - s) * np.tile(_LUMA, (3, 1))
                    offset = np.zeros(3)
                else:
                    m = np.array(op.get("m") or np.eye(3), dtype=np.float64)
                    offset = np.array(op.get("offset") or (0, 0, 0),
                                      dtype=np.float64) * 255.0
                if matrix is None:
                    matrix = (m, offset)
                else:
                    m0, o0 = matrix
                    matrix = (m @ m0, m @ o0 + offset)
            elif name == "vignette":
                flush_pending()
                flush_matrix()
                steps.append(("vignette", float(op.get("strength", 0.5))))
            else:
                log.warning("Unknown colour op %r skipped", name)
        flush_pending()
        flush_matrix()
        self._steps = steps

    def _mask_u8(self, width: int, height: int, strength: float) -> np.ndarray:
        key = (width, height, round(strength, 3))
        mask = self._masks_u8.get(key)
        if mask is None:
            ys = np.linspace(-1.0, 1.0, height, dtype=np.float32)[:, None]
            xs = np.linspace(-1.0, 1.0, width, dtype=np.float32)[None, :]
            distance = np.sqrt(xs * xs + ys * ys) / np.sqrt(2.0)
            falloff = np.clip(1.0 - strength * distance ** 2, 0.0, 1.0)
            mask = np.repeat((falloff * 255.0).astype(np.uint8)[..., None],
                             3, axis=2)
            self._masks_u8[key] = mask
        return mask

    def _mask(self, width: int, height: int, strength: float) -> np.ndarray:
        key = (width, height, round(strength, 3))
        mask = self._masks.get(key)
        if mask is None:
            ys = np.linspace(-1.0, 1.0, height, dtype=np.float32)[:, None]
            xs = np.linspace(-1.0, 1.0, width, dtype=np.float32)[None, :]
            distance = np.sqrt(xs * xs + ys * ys) / np.sqrt(2.0)
            falloff = np.clip(1.0 - strength * distance ** 2, 0.0, 1.0)
            mask = (falloff * 256.0).astype(np.uint16)[..., None]
            self._masks[key] = mask
        return mask

    def _bake(self) -> None:
        lut = bake_lut(self.ops)
        self._flat_lut = lut.reshape(-1, 3)
        index = ((np.arange(256) * (_LUT_SIZE - 1) + 127) // 255).astype(np.int32)
        self._stride_r = index * (_LUT_SIZE * _LUT_SIZE)
        self._stride_g = index * _LUT_SIZE
        self._stride_b = index

    def apply(self, image: np.ndarray) -> np.ndarray:
        """The fast path, exposed for thumbnails and tests."""
        if self._steps is None:
            self._compile()
        if self._steps is not False:
            cv2 = self._cv2
            out = image
            for kind, payload in self._steps:
                if kind == "matrix":
                    out = cv2.transform(out, payload)
                elif kind == "lut":
                    out = cv2.LUT(out, payload)
                else:
                    height, width = out.shape[:2]
                    out = cv2.multiply(out, self._mask_u8(width, height, payload),
                                       scale=1.0 / 255.0)
            return out
        return self._apply_numpy(image)

    def _apply_numpy(self, image: np.ndarray) -> np.ndarray:
        """No-OpenCV fallback: one baked-LUT gather plus the vignette."""
        out = image
        if self._has_colour:
            if self._flat_lut is None:
                self._bake()
            flat = (self._stride_r[out[..., 0]]
                    + self._stride_g[out[..., 1]]
                    + self._stride_b[out[..., 2]])
            out = self._flat_lut[flat]
        for strength in self._vignette_strengths:
            height, width = out.shape[:2]
            mask = self._mask(width, height, strength)
            out = ((out.astype(np.uint16) * mask) >> 8).astype(np.uint8)
        return out

    def process(self, frame: Frame) -> Frame:
        if not self.ops:
            return frame

        def graded():
            image = frame.image()
            if image is None:
                return None
            return self.apply(image)

        return self._wrap(frame, image_fn=graded)


class TimedColor(Filter):
    """Colour clips as a filter over the composite.

    ``spans`` is ``[{"start": frame, "end": frame, "ops": [...]}, ...]`` in
    SEQUENCE frames. A frame inside a span is graded, one outside passes
    untouched - which is how a pink rectangle on the Color lane colours
    exactly the stretch of timeline it covers, in preview and in export,
    because both pull the same graph.
    """

    def __init__(self, spans: list[dict]) -> None:
        self._spans = [
            (int(span.get("start", 0)), int(span.get("end", 0)),
             ColorGrade(span.get("ops") or []))
            for span in spans or []
        ]

    def process(self, frame: Frame) -> Frame:
        for start, end, grade in self._spans:
            if start <= frame.position < end:
                frame = grade.process(frame)
        return frame
