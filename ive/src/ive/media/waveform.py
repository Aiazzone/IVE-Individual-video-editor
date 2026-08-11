"""Audio peak extraction: the real shape of a file's sound.

Pure decoding and numpy, no Qt: the timeline paints these peaks, but the
same function serves any future consumer (audio scrubbing display, beat
detection preprocessing). One pass over the audio stream, downmixed to
mono, reduced to per-column maxima.

The column count adapts to the duration (about 100 columns per second,
capped) so a whole file fits one GPU texture; the painter stretches it to
whatever width the clip occupies at the current zoom - stretching peaks
is visually honest, re-decoding per zoom level would not be worth it.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

__all__ = ["extract_peaks", "columns_for"]

#: Peak columns per second of audio, before the texture cap.
COLUMNS_PER_SECOND = 100
#: The whole strip must load as ONE texture; 8192 is safe on every GPU
#: this app targets (Qt falls back to CPU atlasing above the limit).
MAX_COLUMNS = 8192
MIN_COLUMNS = 64


def columns_for(duration: float) -> int:
    """How many peak columns a file of ``duration`` seconds gets."""
    return int(min(MAX_COLUMNS,
                   max(MIN_COLUMNS, round(duration * COLUMNS_PER_SECOND))))


def extract_peaks(path: str | Path, columns: int | None = None):
    """Per-column peak amplitudes of the file's audio, in [0, 1].

    Returns a float32 array of ``columns`` entries, or ``None`` when the
    file has no audio stream or cannot be read. Amplitude 1.0 is digital
    full scale: a quiet recording draws small, as it should.
    """
    import av

    path = str(path)
    chunks: list[np.ndarray] = []
    try:
        with av.open(path) as container:
            streams = container.streams.audio
            if not streams:
                return None
            stream = streams[0]
            duration = 0.0
            if container.duration:
                duration = container.duration / av.time_base
            for frame in container.decode(stream):
                chunks.append(_mono_abs(frame))
    except Exception:
        log.exception("Could not read audio peaks from %s", Path(path).name)
        return None
    if not chunks:
        return None

    mono = np.concatenate(chunks)
    if columns is None:
        columns = columns_for(duration or (mono.size / 48000.0))
    if mono.size < columns * 2:
        # Too short to bucket honestly: stretch what there is.
        columns = max(1, min(columns, mono.size))
    # reduceat over integer bucket boundaries: exact, no drift, one pass.
    bounds = (np.arange(columns, dtype=np.int64) * mono.size) // columns
    peaks = np.maximum.reduceat(mono, bounds).astype(np.float32)
    np.clip(peaks, 0.0, 1.0, out=peaks)
    return peaks


def _mono_abs(frame) -> np.ndarray:
    """One decoded frame as absolute mono float32 samples."""
    array = frame.to_ndarray()
    if np.issubdtype(array.dtype, np.integer):
        array = array.astype(np.float32) / float(np.iinfo(array.dtype).max)
    else:
        array = array.astype(np.float32, copy=False)
    channels = len(frame.layout.channels)
    if array.shape[0] == 1 and channels > 1:
        # Packed (1, n*ch) -> (n, ch) -> per-sample loudest channel.
        array = np.abs(array.reshape(-1, channels)).max(axis=1)
    else:
        # Planar (ch, n) or mono.
        array = np.abs(array).max(axis=0)
    return array
