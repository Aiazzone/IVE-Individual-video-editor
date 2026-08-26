"""HDR to SDR: what makes a phone clip look right on an SDR canvas.

Phones record PQ (SMPTE 2084) or HLG (ARIB STD-B67) in BT.2020. Decoded
naively, that signal lands on an SDR timeline washed out and desaturated
- the classic "why is my iPhone video grey" (docs/MEDIA_FORMATS.md §8,
Fase A). This module turns one decoded BT.2020 HDR frame (RGB, 16-bit,
the matrix already applied by swscale from the frame's own tag) into
honest BT.709 SDR:

    PQ/HLG EOTF -> linear light in nits -> highlight knee around the
    HDR reference white (203 nits = SDR 100%, BT.2408) -> BT.2020 to
    BT.709 gamut matrix -> BT.709 OETF -> 8 bit.

Design choices, deliberate:

* the EOTF is a 65 536-entry LUT indexed by the raw uint16 - one gather
  per channel, no per-pixel transcendentals;
* mid-tones are LEFT ALONE (everything below ~152 nits maps linearly):
  tone mapping must compress highlights, not dim the whole picture,
  which is what a plain Reinhard curve does;
* the knee is applied per channel: cheap, monotonic, and the desaturation
  it causes on extreme highlights reads as "bright" - the same trade
  ffmpeg's tonemap makes by default;
* pure numpy + cv2, no Qt: callable from the decoder and from the proxy
  worker alike.

Everything here is SDR *output*: the app manages HDR material, it does
not produce HDR (MEDIA_FORMATS.md - promising HDR and delivering a tone
map would be worse than not promising it).
"""

from __future__ import annotations

import logging

import numpy as np

try:
    import cv2
except ImportError:                                   # pragma: no cover
    cv2 = None

log = logging.getLogger(__name__)

__all__ = ["is_hdr_transfer", "tonemap_to_sdr", "TRANSFER_PQ",
           "TRANSFER_HLG"]

TRANSFER_PQ = 16      # AVCOL_TRC_SMPTE2084
TRANSFER_HLG = 18     # AVCOL_TRC_ARIB_STD_B67

#: SDR reference white in nits (BT.2408): an HDR pixel at 203 nits is
#: "plain white paper" and must land at SDR 100%.
_REF_WHITE = 203.0
#: Brightest input the knee reaches 1.0 at. Phone HDR masters around
#: 1000 nits; anything above clips there, which is what displays do too.
_PEAK = 1000.0
#: Below this fraction of SDR white the mapping is IDENTITY: mid-tones
#: are already right, only highlights need compressing.
_KNEE = 0.75

#: BT.2020 -> BT.709 primaries, linear light (derived from the standard
#: primaries; rows sum to 1 so white stays white).
_GAMUT_2020_TO_709 = np.array([
    [1.6605, -0.5876, -0.0728],
    [-0.1246, 1.1329, -0.0083],
    [-0.0182, -0.1006, 1.1187],
], dtype=np.float32)

#: Fixed-point scale for linear light between the two LUTs: SDR white
#: (1.0) sits at 13 bits, so the knee's ceiling (peak/ref ≈ 4.93) still
#: fits a uint16 with room to spare.
_FIX = 8192.0

_luts: dict[int, np.ndarray] = {}
_oetf_lut: np.ndarray | None = None


def is_hdr_transfer(transfer: int) -> bool:
    return int(transfer) in (TRANSFER_PQ, TRANSFER_HLG)


def _pq_eotf(signal: np.ndarray) -> np.ndarray:
    """PQ code value 0..1 -> display light in nits (SMPTE 2084)."""
    m1 = 2610.0 / 16384.0
    m2 = 2523.0 / 4096.0 * 128.0
    c1 = 3424.0 / 4096.0
    c2 = 2413.0 / 4096.0 * 32.0
    c3 = 2392.0 / 4096.0 * 32.0
    e = np.power(np.clip(signal, 0.0, 1.0), 1.0 / m2)
    return 10000.0 * np.power(np.maximum(e - c1, 0.0) / (c2 - c3 * e),
                              1.0 / m1)


def _hlg_eotf(signal: np.ndarray) -> np.ndarray:
    """HLG signal 0..1 -> display light in nits, 1000-nit display.

    Inverse OETF to scene light, then the system gamma (1.2) of the
    OOTF - applied per channel here, the same simplification the knee
    makes; on real footage the difference hides inside the highlights.
    """
    a, b, c = 0.17883277, 0.28466892, 0.55991073
    s = np.clip(signal, 0.0, 1.0)
    scene = np.where(s <= 0.5, (s * s) / 3.0,
                     (np.exp((s - c) / a) + b) / 12.0)
    return 1000.0 * np.power(np.clip(scene, 0.0, 1.0), 1.2)


def _knee(linear: np.ndarray) -> np.ndarray:
    """Identity below the knee, a smooth squeeze to 1.0 at the peak."""
    peak = _PEAK / _REF_WHITE
    span = peak - _KNEE
    t = np.clip((linear - _KNEE) / span, 0.0, 1.0)
    compressed = _KNEE + (1.0 - _KNEE) * t * (2.0 - t)
    return np.where(linear <= _KNEE, linear, compressed)


def _lut_for(transfer: int) -> np.ndarray:
    """uint16 code value -> EOTF + knee, as fixed-point linear light.

    The whole per-channel front half of the pipeline collapses into one
    65 536-entry table: the frame pays a single gather per channel
    instead of transcendentals per pixel (naive numpy measured 520 ms a
    1080p frame; the LUT pipeline ~60).
    """
    lut = _luts.get(int(transfer))
    if lut is None:
        signal = np.arange(65536, dtype=np.float64) / 65535.0
        nits = (_pq_eotf(signal) if int(transfer) == TRANSFER_PQ
                else _hlg_eotf(signal))
        lut = np.round(_knee(nits / _REF_WHITE) * _FIX) \
            .clip(0, 65535).astype(np.uint16)
        _luts[int(transfer)] = lut
    return lut


def _oetf() -> np.ndarray:
    """Fixed-point linear light -> BT.709 OETF -> uint8, as a table."""
    global _oetf_lut
    if _oetf_lut is None:
        linear = np.clip(np.arange(65536, dtype=np.float64) / _FIX,
                         0.0, 1.0)
        low = linear * 4.5
        high = 1.099 * np.power(np.maximum(linear, 1e-6), 0.45) - 0.099
        signal = np.where(linear < 0.018, low, high)
        _oetf_lut = np.clip(signal * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return _oetf_lut


def tonemap_to_sdr(rgb48: np.ndarray, transfer: int) -> np.ndarray:
    """One BT.2020 HDR frame (RGB uint16, matrix already applied) ->
    BT.709 SDR RGB uint8, same size.

    Three SIMD-friendly steps: gather (EOTF + knee fused), 3x3 gamut
    matrix in saturating uint16, gather (OETF + quantise fused).
    """
    linear = _lut_for(transfer)[rgb48]               # HxWx3 uint16 fixed
    if cv2 is not None:
        mixed = cv2.transform(linear, _GAMUT_2020_TO_709)
    else:
        mixed = np.clip(
            linear.astype(np.float32) @ _GAMUT_2020_TO_709.T,
            0.0, 65535.0).astype(np.uint16)
    return _oetf()[mixed]
