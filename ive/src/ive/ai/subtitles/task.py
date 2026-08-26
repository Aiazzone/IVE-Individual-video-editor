"""Speech-to-text over the timeline's footage, on the CPU, cancellable.

The transcription runs PER SOURCE SPAN, not on the mixed output: each
A/V clip's own audio is decoded (``[sourceIn, sourceIn + duration)`` of
its file), transcribed in MEDIA time, and the words are shifted onto
the timeline with the clip's placement. That way trims and moves are
respected exactly, and the Music lane never pollutes the words - the
bed is simply not part of what is read.

faster-whisper (CTranslate2, MIT - registered in docs/LICENSING.md)
does the recognition with word timestamps and its own VAD in front, so
silence and music inside the footage cost nothing and produce nothing.
Everything here is Qt-free and runs on whatever worker thread calls it;
CTranslate2 releases the GIL while it computes.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

import numpy as np

from ive.ai.model_registry import is_installed, model_dir
from ive.ai.subtitles.segment import SubtitleLine, segment_words

log = logging.getLogger(__name__)

__all__ = ["SubtitleTask", "TranscribeError"]

#: Whisper's native input rate; the extractor resamples to this.
_RATE = 16000


class TranscribeError(RuntimeError):
    """Transcription failed in a way the caller must surface."""


def _extract_audio(path: str, offset: float, duration: float
                   ) -> np.ndarray:
    """Mono float32 at 16 kHz for ``[offset, offset + duration)`` seconds.

    MEDIA time: ``offset`` counts from the file's own zero, which is why
    the stream's ``start_time`` is added back when seeking and
    subtracted from the frame timestamps - the MPEG-TS lesson of
    2026-08-24 (docs/MEDIA_FORMATS.md §8) applies here too.
    """
    import av

    pieces: list[np.ndarray] = []
    with av.open(str(path)) as container:
        streams = [s for s in container.streams if s.type == "audio"]
        if not streams:
            return np.zeros(0, dtype=np.float32)
        stream = streams[0]
        start_pts = int(stream.start_time or 0)
        resampler = av.AudioResampler(format="flt", layout="mono",
                                      rate=_RATE)
        seek_to = start_pts + int(offset / stream.time_base)
        try:
            container.seek(seek_to, stream=stream, backward=True,
                           any_frame=False)
        except Exception:
            log.debug("Audio seek failed in %s; reading from the top",
                      Path(path).name, exc_info=True)

        done = 0
        target = int(round(duration * _RATE))
        skip = None    # samples to drop from the first frame, set below
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                array = out.to_ndarray().reshape(-1).astype(np.float32)
                if skip is None:
                    if out.pts is not None:
                        t = float(out.pts / out.sample_rate) \
                            - float(start_pts * stream.time_base)
                    else:
                        t = 0.0
                    skip = max(0, int(round((offset - t) * _RATE)))
                if skip:
                    if skip >= len(array):
                        skip -= len(array)
                        continue
                    array = array[skip:]
                    skip = 0
                pieces.append(array)
                done += len(array)
            if done >= target:
                break
        # Flush whatever the resampler still holds.
        for out in resampler.resample(None):
            if done >= target:
                break
            array = out.to_ndarray().reshape(-1).astype(np.float32)
            pieces.append(array)
            done += len(array)

    if not pieces:
        return np.zeros(0, dtype=np.float32)
    audio = np.concatenate(pieces)
    return audio[:int(round(duration * _RATE))]


class SubtitleTask:
    """One transcription engine around one installed model.

    The model loads lazily on first use and stays loaded for the next
    run; ``unload()`` frees it (docs/AI_FEATURES.md §10: models resident
    forever exhaust the RAM).
    """

    def __init__(self, model_id: str) -> None:
        self.model_id = str(model_id)
        self._model = None
        #: ISO code of the last language the model detected ("" before
        #: any run). The translation step uses it as the source when
        #: the user has not pinned one.
        self.last_language = ""

    # -- availability ---------------------------------------------------

    def availability(self) -> str:
        """"ready" | "model_missing" | "backend_missing".

        Checked WITHOUT importing the backend: importing ctranslate2
        loads its own OpenMP runtime, and in an environment where
        another copy is already resident (torch, Intel runtimes) that
        aborts the whole process with OMP Error #15. The app process
        must never load it - inference lives in the worker process
        (ive/ai/subtitles/worker.py), where the duplicate-runtime
        workaround is confined.
        """
        from importlib.util import find_spec

        try:
            if find_spec("faster_whisper") is None:
                return "backend_missing"
        except (ImportError, ValueError):
            return "backend_missing"
        return "ready" if is_installed(self.model_id) else "model_missing"

    def unload(self) -> None:
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            folder = model_dir(self.model_id)
            log.info("Loading %s from %s (CPU, int8)", self.model_id, folder)
            t0 = time.perf_counter()
            self._model = WhisperModel(str(folder), device="cpu",
                                       compute_type="int8")
            log.info("Model %s loaded in %.1fs", self.model_id,
                     time.perf_counter() - t0)
        return self._model

    # -- transcription --------------------------------------------------

    def transcribe_span(self, path: str, offset: float, duration: float,
                        *, language: str = "",
                        progress: Callable[[float], None] | None = None,
                        cancelled: Callable[[], bool] | None = None
                        ) -> list[dict]:
        """Words spoken in ``[offset, offset + duration)`` of one file.

        Returns ``[{"start", "end", "text"}, ...]`` in MEDIA time.
        ``progress`` receives 0..1 within this span; ``cancelled`` is
        polled between segments and stops cleanly with what was read
        so far discarded.
        """
        audio = _extract_audio(path, max(0.0, float(offset)),
                               max(0.05, float(duration)))
        if not len(audio) or float(np.abs(audio).max()) < 1e-4:
            return []          # silence in, nothing out - not an error
        model = self._ensure_model()
        try:
            segments, info = model.transcribe(
                audio,
                language=language or None,
                word_timestamps=True,
                vad_filter=True,
                condition_on_previous_text=False)
        except Exception as exc:
            raise TranscribeError(str(exc)) from exc

        detected = str(getattr(info, "language", "") or "")
        if detected:
            self.last_language = detected
        words: list[dict] = []
        span = max(0.05, float(duration))
        for segment in segments:
            if cancelled is not None and cancelled():
                return []
            for word in segment.words or []:
                words.append({"start": float(offset) + float(word.start),
                              "end": float(offset) + float(word.end),
                              "text": str(word.word)})
            if progress is not None:
                progress(min(1.0, float(segment.end) / span))
        log.info("Transcribed %.1fs of %s: %d words (language %s)",
                 duration, Path(path).name, len(words),
                 getattr(info, "language", "?"))
        return words

    def run_on_clips(self, clips: list[dict], *, language: str = "",
                     progress: Callable[[float], None] | None = None,
                     cancelled: Callable[[], bool] | None = None
                     ) -> list[SubtitleLine]:
        """Subtitle lines for a whole cut, in TIMELINE time.

        ``clips`` is ``[{"path", "start", "sourceIn", "duration"}, ...]``
        - the A/V clips of the sequence, in timeline order. Progress is
        weighted by duration across all of them.
        """
        total = sum(max(0.05, float(c["duration"])) for c in clips) or 1.0
        elapsed = 0.0
        words: list[dict] = []
        for clip in clips:
            if cancelled is not None and cancelled():
                return []
            span = max(0.05, float(clip["duration"]))
            base = elapsed

            def span_progress(fraction: float) -> None:
                if progress is not None:
                    progress(min(1.0, (base + fraction * span) / total))

            media_words = self.transcribe_span(
                str(clip["path"]), float(clip["sourceIn"]), span,
                language=language, progress=span_progress,
                cancelled=cancelled)
            shift = float(clip["start"]) - float(clip["sourceIn"])
            end_limit = float(clip["start"]) + span
            for word in media_words:
                start = word["start"] + shift
                if start >= end_limit:
                    continue       # spoken past the trimmed tail
                words.append({"start": start,
                              "end": min(end_limit, word["end"] + shift),
                              "text": word["text"]})
            elapsed += span
        if cancelled is not None and cancelled():
            return []
        words.sort(key=lambda w: w["start"])
        return segment_words(words)
