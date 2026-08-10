"""Turns the project model into a graph.

**One direction only.** The graph is built FROM the model and is never edited
on its own. This is the rule from docs/ENGINE.md §3, and it exists because
Kdenlive's first generation let effect parameters live in two places: the UI
showed one value and the renderer used another, and the resulting instability
took a rewrite to fix.

So: change the model, rebuild the graph. Never reach into the graph to change
something and hope the model catches up.
"""

from __future__ import annotations

import logging
from fractions import Fraction
from pathlib import Path

from ive.engine.filters import Gain
from ive.engine.frame import AudioFormat, Timebase
from ive.engine.playlist import Entry, Playlist
from ive.engine.producer import ClipProducer, ColourProducer, Producer
from ive.engine.tractor import Track, Tractor

log = logging.getLogger(__name__)

__all__ = ["GraphBuilder", "build_from_project"]

DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080


class GraphBuilder:
    """Builds a tractor from a project, reusing producers between rebuilds.

    Reuse matters: the timeline is rebuilt on every edit, and reopening every
    container each time would make dragging a clip feel like opening a file.
    """

    def __init__(self, timebase: Timebase | None = None,
                 audio_format: AudioFormat | None = None,
                 width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT,
                 proxies=None, use_proxies: bool = True) -> None:
        """``use_proxies`` must be **False for export**.

        Rendering a delivery from stand-in files is wasted work the user only
        discovers afterwards. The choice lives here, in one visible place,
        rather than inside a producer where it could be forgotten.
        """
        self._producers: dict[str, Producer] = {}
        self._timebase = timebase or Timebase()
        self.audio_format = audio_format or AudioFormat()
        self.width = width
        self.height = height
        self.proxies = proxies
        self.use_proxies = use_proxies

    @property
    def timebase(self) -> Timebase:
        return self._timebase

    @timebase.setter
    def timebase(self, value: Timebase | None) -> None:
        value = value or Timebase()
        changed = value.fps != self._timebase.fps
        self._timebase = value
        if changed and self._producers:
            # A ClipProducer freezes its timebase at construction: reusing
            # one built at the old rate maps positions to the wrong source
            # frames (video visibly fast or slow) once the sequence rate
            # changes, e.g. after deleting the first clip. Reopening the
            # containers is the cost of staying correct.
            log.info("Sequence timebase changed to %s: reopening %d producer(s)",
                     value, len(self._producers))
            self.close()

    # ── producers ─────────────────────────────────────────────────────

    def producer_for(self, path: str) -> Producer | None:
        """Open a file once and keep it for later rebuilds."""
        key = str(path)
        existing = self._producers.get(key)
        if existing is not None:
            return existing
        if not Path(key).is_file():
            log.warning("Media missing, skipped: %s", key)
            return None

        proxy = None
        if self.use_proxies and self.proxies is not None:
            resolved = self.proxies.resolve(key)
            if resolved != key:
                proxy = resolved
        try:
            producer = ClipProducer(key, self.timebase, self.audio_format, proxy,
                                    canvas=(self.width, self.height))
        except Exception:
            log.exception("Could not build a producer for %s", Path(key).name)
            return None
        self._producers[key] = producer
        return producer

    def release_unused(self, keep: set[str]) -> None:
        """Close producers no longer referenced by the project."""
        for key in list(self._producers):
            if key not in keep:
                log.debug("Releasing producer %s", Path(key).name)
                self._producers.pop(key).close()

    def close(self) -> None:
        for producer in self._producers.values():
            producer.close()
        self._producers.clear()

    # ── the graph ─────────────────────────────────────────────────────

    def build(self, clips: list[dict],
              color_spans: list[dict] | None = None) -> Tractor:
        """Build a tractor from timeline clips.

        Each clip is ``{path, start, duration}`` in **seconds**, as the project
        model still stores them. Converting here, in one place, is what makes
        the eventual move of the model to frames a local change.

        ``color_spans`` is the Color lane: ``{start, end, ops}`` in seconds,
        applied over the finished composite as a TimedColor tractor filter -
        so preview and export grade identically, because they pull the same
        graph.
        """
        tractor = Tractor(self.timebase, self.audio_format,
                          self.width, self.height, name="sequence")

        usable = []
        for clip in clips or []:
            path = str(clip.get("path") or "")
            producer = self.producer_for(path) if path else None
            if producer is None:
                continue
            usable.append((clip, producer))

        total = 0
        for clip, _ in usable:
            end = float(clip.get("start") or 0.0) + float(clip.get("duration") or 0.0)
            total = max(total, self.timebase.seconds_to_frames(end))

        # The black track, exactly as Kdenlive does it: with something always
        # underneath, compositing never has to special-case an empty stack.
        tractor.add_track(Track(
            ColourProducer(self.width, self.height, max(1, total),
                           self.timebase, (0, 0, 0), self.audio_format, "black"),
            video=True, audio=False, name="black",
        ))

        video_track = Playlist(self.timebase, self.audio_format, name="V1")
        cursor = 0
        for clip, producer in usable:
            start = self.timebase.seconds_to_frames(float(clip.get("start") or 0.0))
            length = self.timebase.seconds_to_frames(float(clip.get("duration") or 0.0))
            if length <= 0:
                continue
            if start > cursor:
                video_track.append_blank(start - cursor)
                cursor = start
            volume = float(clip.get("volume", 1.0) if clip.get("volume")
                           is not None else 1.0)
            entry = Entry(
                producer=producer,
                source_in=self.timebase.seconds_to_frames(
                    float(clip.get("sourceIn") or 0.0)),
                length=length,
                clip_id=str(clip.get("id") or ""),
            )
            # Per ENTRY, not per producer: two clips cut from the same file
            # share the producer but each keeps its own loudness.
            if abs(volume - 1.0) > 1e-6:
                entry.filters.append(Gain(volume))
            video_track.append(entry)
            cursor += length

        if video_track.length:
            tractor.add_track(Track(video_track, video=True, audio=True, name="V1"))

        graded = [
            {"start": self.timebase.seconds_to_frames(float(s.get("start") or 0.0)),
             "end": self.timebase.seconds_to_frames(float(s.get("end") or 0.0)),
             "ops": s.get("ops") or []}
            for s in (color_spans or []) if s.get("ops")
        ]
        if graded:
            from ive.engine.filters import TimedColor

            tractor.filters.append(TimedColor(graded))

        log.info("Graph built: %d clip(s), %d colour span(s), %d frames at %s",
                 len(usable), len(graded), tractor.length, self.timebase)
        self.release_unused({str(c.get("path") or "") for c in (clips or [])})
        return tractor


def build_from_project(clips: list[dict], *, fps: float = 25.0,
                       width: int = DEFAULT_WIDTH,
                       height: int = DEFAULT_HEIGHT,
                       proxies=None, use_proxies: bool = True,
                       color_spans: list[dict] | None = None) -> Tractor:
    """One-shot build, for tests and scripts."""
    builder = GraphBuilder(Timebase(Fraction(fps).limit_denominator(1001)),
                           AudioFormat(), width, height, proxies, use_proxies)
    return builder.build(clips, color_spans)
