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

    def producer_for(self, path: str, bucket: str = "a") -> Producer | None:
        """Open a file once PER BUCKET and keep it for later rebuilds.

        The bucket is the A/B roll the entry lands on. Sharing one
        decoder across both rolls was correct while pulls were strictly
        sequential, but a transition between two cuts OF THE SAME FILE
        pulls two different source positions on every frame of the
        window - the shared decoder seeked back and forth each time,
        measured at 229 ms/frame against ~15 outside. Two decoders,
        each reading forward, is the whole fix.
        """
        key = f"{bucket}|{path}"
        existing = self._producers.get(key)
        if existing is not None:
            return existing
        if not Path(str(path)).is_file():
            log.warning("Media missing, skipped: %s", path)
            return None

        source = str(path)
        proxy = None
        if self.use_proxies and self.proxies is not None:
            resolved = self.proxies.resolve(source)
            if resolved != source:
                proxy = resolved
        try:
            producer = ClipProducer(source, self.timebase, self.audio_format,
                                    proxy, canvas=(self.width, self.height))
        except Exception:
            log.exception("Could not build a producer for %s",
                          Path(source).name)
            return None
        self._producers[key] = producer
        return producer

    def release_unused(self, keep: set[str]) -> None:
        """Close producers (by bucket|path key) the build no longer uses."""
        for key in list(self._producers):
            if key not in keep:
                log.debug("Releasing producer %s", key)
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
            if not path or not Path(path).is_file():
                if path:
                    log.warning("Media missing, skipped: %s", path)
                continue
            usable.append(clip)

        total = 0
        for clip in usable:
            end = float(clip.get("start") or 0.0) + float(clip.get("duration") or 0.0)
            total = max(total, self.timebase.seconds_to_frames(end))

        # The black track, exactly as Kdenlive does it: with something always
        # underneath, compositing never has to special-case an empty stack.
        tractor.add_track(Track(
            ColourProducer(self.width, self.height, max(1, total),
                           self.timebase, (0, 0, 0), self.audio_format, "black"),
            video=True, audio=False, name="black",
        ))

        # Two video playlists, A/B roll: clips stay on one until an
        # overlap (a junction transition pulled the next clip back) makes
        # two of them share frames - then the incoming clip goes to the
        # OTHER playlist. Without transitions everything lands on V1 and
        # the graph is exactly what it always was.
        roll_a = Playlist(self.timebase, self.audio_format, name="V1")
        roll_b = Playlist(self.timebase, self.audio_format, name="V1b")
        cursors = {id(roll_a): 0, id(roll_b): 0}
        current = roll_a
        #: (entry, roll, start_f, end_f) of every placed clip, for the
        #: window pass below.
        placed: list[tuple] = []
        used_keys: set[str] = set()
        prev_end = None
        for clip in usable:
            start = self.timebase.seconds_to_frames(float(clip.get("start") or 0.0))
            length = self.timebase.seconds_to_frames(float(clip.get("duration") or 0.0))
            if length <= 0:
                continue
            if prev_end is not None and start < prev_end:
                # Alternate REGARDLESS of a usable recipe: two clips must
                # never overlap on one playlist. With no blender the cut
                # simply plays plain - the incoming clip covers.
                current = roll_b if current is roll_a else roll_a
            # The producer is resolved PER ROLL: two cuts of the same
            # file on opposite sides of a transition each get their own
            # decoder (see producer_for for why sharing one was a seek
            # storm).
            bucket = "a" if current is roll_a else "b"
            path = str(clip.get("path") or "")
            producer = self.producer_for(path, bucket)
            if producer is None:
                continue
            used_keys.add(f"{bucket}|{path}")
            entry = Entry(
                producer=producer,
                source_in=self.timebase.seconds_to_frames(
                    float(clip.get("sourceIn") or 0.0)),
                length=length,
                clip_id=str(clip.get("id") or ""),
            )
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
            placed.append((entry, current, start, start + length))
            prev_end = start + length

        # The windows: junction blends live on the UPPER roll (one of the
        # two overlapping clips is always there, by construction), intro
        # and outro blends against the black track live on their own
        # clip's roll. `flipped` marks windows where the OUTGOING picture
        # is the one on the track carrying the blend.
        windows: dict[int, list] = {id(roll_a): [], id(roll_b): []}
        for span in (transition_spans or []):
            blender = span.get("blender")
            if blender is None:
                continue
            start_f = self.timebase.seconds_to_frames(
                float(span.get("start") or 0.0))
            end_f = self.timebase.seconds_to_frames(
                float(span.get("end") or 0.0))
            if end_f <= start_f:
                continue
            easing = str(span.get("easing") or "smooth")
            edge = str(span.get("edge") or "cut")
            if edge == "in":
                hit = next((p for p in placed if abs(p[2] - start_f) <= 1),
                           None)
                if hit is not None:
                    windows[id(hit[1])].append(
                        (start_f, end_f, blender, easing, False))
                    hit[0].filters.append(AudioRamp(start_f, end_f,
                                                    rising=True))
            elif edge == "out":
                hit = next((p for p in placed if abs(p[3] - end_f) <= 1),
                           None)
                if hit is not None:
                    windows[id(hit[1])].append(
                        (start_f, end_f, blender, easing, True))
                    hit[0].filters.append(AudioRamp(start_f, end_f,
                                                    rising=False))
            else:
                incoming = next(
                    (p for p in placed if abs(p[2] - start_f) <= 1), None)
                outgoing = next(
                    (p for p in placed if abs(p[3] - end_f) <= 1), None)
                if incoming is None or outgoing is None \
                        or incoming[1] is outgoing[1]:
                    continue
                upper = incoming[1] if incoming[1] is roll_b else outgoing[1]
                windows[id(upper)].append(
                    (start_f, end_f, blender, easing,
                     outgoing[1] is roll_b))
                # Equal-power crossfade: the outgoing entry fades out,
                # the incoming fades in, over the same frames.
                outgoing[0].filters.append(AudioRamp(start_f, end_f,
                                                     rising=False))
                incoming[0].filters.append(AudioRamp(start_f, end_f,
                                                     rising=True))

        from ive.engine.transitions import TimedBlend

        if roll_a.length:
            tractor.add_track(Track(
                roll_a, video=True, audio=True,
                transition=(TimedBlend(windows[id(roll_a)])
                            if windows[id(roll_a)] else None),
                name="V1"))
        if roll_b.length:
            tractor.add_track(Track(
                roll_b, video=True, audio=True,
                transition=TimedBlend(windows[id(roll_b)]),
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
        self.release_unused(used_keys)
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
