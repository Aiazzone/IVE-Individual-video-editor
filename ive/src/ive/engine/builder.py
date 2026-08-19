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

from ive.engine.filters import AudioRamp, Gain
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
              color_spans: list[dict] | None = None,
              sticker_spans: list[dict] | None = None,
              text_spans: list[dict] | None = None,
              transition_spans: list[dict] | None = None) -> Tractor:
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

        # Transition windows, in sequence frames, resolved to blenders by
        # ive/transitions/loader.py (the engine reads no files).
        pending_windows: list[tuple] = []
        for span in (transition_spans or []):
            blender = span.get("blender")
            if blender is None:
                continue
            start_f = self.timebase.seconds_to_frames(
                float(span.get("start") or 0.0))
            end_f = self.timebase.seconds_to_frames(
                float(span.get("end") or 0.0))
            if end_f > start_f:
                pending_windows.append(
                    (start_f, end_f, blender,
                     str(span.get("easing") or "smooth")))

        # Two video playlists, A/B roll: clips stay on one until a
        # transition makes two of them overlap - then the incoming clip
        # goes to the OTHER playlist, and the window on the upper track
        # blends them. Without transitions everything lands on V1 and the
        # graph is exactly what it always was.
        roll_a = Playlist(self.timebase, self.audio_format, name="V1")
        roll_b = Playlist(self.timebase, self.audio_format, name="V1b")
        cursors = {id(roll_a): 0, id(roll_b): 0}
        current = roll_a
        windows: list[tuple] = []
        prev_entry: Entry | None = None
        prev_end = None
        for clip, producer in usable:
            start = self.timebase.seconds_to_frames(float(clip.get("start") or 0.0))
            length = self.timebase.seconds_to_frames(float(clip.get("duration") or 0.0))
            if length <= 0:
                continue
            entry = Entry(
                producer=producer,
                source_in=self.timebase.seconds_to_frames(
                    float(clip.get("sourceIn") or 0.0)),
                length=length,
                clip_id=str(clip.get("id") or ""),
            )
            overlap_end = min(prev_end, start + length) \
                if (prev_end is not None and start < prev_end) else None
            if overlap_end is not None:
                # The OLD clip sits on `current`; roles flip when that is
                # the UPPER track (a push must know which side is leaving).
                flipped = current is roll_b
                current = roll_b if current is roll_a else roll_a
                window = next(
                    (w for w in pending_windows
                     if abs(w[0] - start) <= 1 and abs(w[1] - overlap_end) <= 1),
                    None)
                if window is not None:
                    windows.append((start, overlap_end,
                                    window[2], window[3], flipped))
                    # Equal-power crossfade: the outgoing entry fades out,
                    # the incoming fades in, over the same frames.
                    if prev_entry is not None:
                        prev_entry.filters.append(AudioRamp(
                            start, overlap_end, rising=False))
                    entry.filters.append(AudioRamp(
                        start, overlap_end, rising=True))
                # No window (recipe deleted, file gone): the tracks still
                # alternate so nothing overlaps on one playlist, and the
                # cut plays plain - the incoming clip simply covers.
            cursor = cursors[id(current)]
            if start > cursor:
                current.append_blank(start - cursor)
            volume = float(clip.get("volume", 1.0) if clip.get("volume")
                           is not None else 1.0)
            # Per ENTRY, not per producer: two clips cut from the same file
            # share the producer but each keeps its own loudness.
            if abs(volume - 1.0) > 1e-6:
                entry.filters.append(Gain(volume))
            current.append(entry)
            cursors[id(current)] = start + length
            prev_entry = entry
            prev_end = start + length

        if roll_a.length:
            tractor.add_track(Track(roll_a, video=True, audio=True, name="V1"))
        if roll_b.length:
            from ive.engine.transitions import TimedBlend

            tractor.add_track(Track(roll_b, video=True, audio=True,
                                    transition=TimedBlend(windows),
                                    name="V1b"))

        graded = [
            {"start": self.timebase.seconds_to_frames(float(s.get("start") or 0.0)),
             "end": self.timebase.seconds_to_frames(float(s.get("end") or 0.0)),
             "ops": s.get("ops") or []}
            for s in (color_spans or []) if s.get("ops")
        ]
        if graded:
            from ive.engine.filters import TimedColor

            tractor.filters.append(TimedColor(graded))

        # The Sticker and Text lanes, composited AFTER the grade: an overlay
        # keeps its own colours, whatever look sits under it. Spans arrive in
        # seconds with their `sprite` closures already attached (stickers/
        # raster.py and text/raster.py do that, so the engine never imports
        # Qt). The ORIGINAL dicts are handed over, not copies: Overlays reads
        # x/y at process time, which is what lets the transport move an
        # overlay live while the user drags a handle on the preview. Text
        # comes AFTER stickers in the list, so titles draw above them.
        overlays = [
            s for s in list(sticker_spans or []) + list(text_spans or [])
            if callable(s.get("sprite"))
        ]
        if overlays:
            from ive.engine.filters import Overlays

            tractor.filters.append(Overlays(overlays, self.timebase))

        log.info("Graph built: %d clip(s), %d colour span(s), %d overlay "
                 "span(s), %d frames at %s",
                 len(usable), len(graded), len(overlays), tractor.length,
                 self.timebase)
        self.release_unused({str(c.get("path") or "") for c in (clips or [])})
        return tractor


def build_from_project(clips: list[dict], *, fps: float = 25.0,
                       width: int = DEFAULT_WIDTH,
                       height: int = DEFAULT_HEIGHT,
                       proxies=None, use_proxies: bool = True,
                       color_spans: list[dict] | None = None,
                       sticker_spans: list[dict] | None = None,
                       text_spans: list[dict] | None = None,
                       transition_spans: list[dict] | None = None) -> Tractor:
    """One-shot build, for tests and scripts."""
    builder = GraphBuilder(Timebase(Fraction(fps).limit_denominator(1001)),
                           AudioFormat(), width, height, proxies, use_proxies)
    return builder.build(clips, color_spans, sticker_spans, text_spans,
                         transition_spans)
