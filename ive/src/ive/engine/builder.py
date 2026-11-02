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
from pathlib import Path

from ive.engine.cutout import Cutout
from ive.engine.filters import AudioEffect, AudioRamp, Gain, Placement
from ive.engine.frame import AudioFormat, Timebase
from ive.engine.playlist import Entry, Playlist
from ive.engine.producer import (ClipProducer, ColourProducer, Producer,
                                 SpeedProducer)
from ive.engine.tractor import Track, Tractor
from ive.utils.timecode import parse_rate

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
        #: fit / fill / blur: how a picture meets the canvas (Tractor).
        self.canvas_fit = "fit"
        #: An ALPHA export: the black track becomes "nothing" and every
        #: stage that changes coverage computes it. Never for the preview.
        self.with_alpha = False

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

    def _span(self, clip: dict) -> tuple[int, int]:
        """(first frame, frame count) of a ``start``/``duration`` dict."""
        start_s = float(clip.get("start") or 0.0)
        first = self.timebase.seconds_to_frames(start_s)
        last = self.timebase.seconds_to_frames(
            start_s + float(clip.get("duration") or 0.0))
        return first, last - first

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
        source = str(path)
        proxy = None
        if self.use_proxies and self.proxies is not None:
            resolved = self.proxies.resolve(source)
            if resolved != source:
                proxy = resolved
        existing = self._producers.get(key)
        if existing is not None:
            # The proxy decision is baked into the producer at open time,
            # so reuse is only valid while that decision stands. A changed
            # working resolution, a flipped enable switch or a build that
            # just finished all resolve to a different file - without this
            # check the rebuild returned the old producer and the preview
            # kept reading yesterday's resolution until the next restart.
            if getattr(existing, "proxy_path", "") == (proxy or ""):
                return existing
            log.info("Proxy for %s changed: reopening the producer",
                     Path(source).name)
            self._producers.pop(key).close()
        if not Path(source).is_file():
            log.warning("Media missing, skipped: %s", path)
            return None

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
              transition_spans: list[dict] | None = None,
              music_spans: list[dict] | None = None) -> Tractor:
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
        tractor.set_fit_mode(self.canvas_fit)

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
            # EDGES to frames, the length is what lies between: rounding
            # start and duration separately left a one-frame gap (or
            # overlap) between clips that touch whenever both rounded the
            # same way at a boundary that sits between two frames.
            start, length = self._span(clip)
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
            # Speed: the shared producer gets a cheap per-entry wrapper
            # that plays it at another pace. In the wrapper's timeline a
            # media second sits at second/speed, so the head offset is
            # scaled the same way.
            speed = float(clip.get("speed") or 1.0)
            source_in_seconds = float(clip.get("sourceIn") or 0.0)
            if abs(speed - 1.0) > 1e-3:
                producer = SpeedProducer(producer, speed)
                source_in_seconds = source_in_seconds / speed
            entry = Entry(
                producer=producer,
                source_in=self.timebase.seconds_to_frames(source_in_seconds),
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
            # The clip's audio recipe, then its own fades - the recipe
            # shapes the sound, the fades scale what comes out of it.
            audio_ops = clip.get("audioOps")
            if audio_ops:
                entry.filters.append(AudioEffect(list(audio_ops)))
            fade_in = self.timebase.seconds_to_frames(
                float(clip.get("fadeIn") or 0.0))
            if fade_in > 0:
                entry.filters.append(AudioRamp(
                    start, start + min(fade_in, length), rising=True))
            fade_out = self.timebase.seconds_to_frames(
                float(clip.get("fadeOut") or 0.0))
            if fade_out > 0:
                entry.filters.append(AudioRamp(
                    start + max(0, length - fade_out), start + length,
                    rising=False))
            # Background removal FIRST: the new backdrop belongs to the
            # clip's picture, so placement and crop then move it along.
            if (clip.get("cutout") or {}).get("mode"):
                entry.filters.append(Cutout(clip))
            # The clip's canvas dressing - placement, crop, opacity and
            # their keyframes: the filter reads the CLIP DICT at process
            # time, so the transport's live handle drag mutates this
            # very object and the next frame follows the hand. Attached
            # whenever any of the keys exists - untouched clips pass
            # through at zero cost.
            if any(k in clip for k in ("placed", "crop", "opacity",
                                       "keyframes")):
                entry.filters.append(Placement(
                    clip, self.width, self.height,
                    "blur" if self.canvas_fit == "blur" else "black",
                    start_frame=start,
                    fps=float(self.timebase.fps)))
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

        # The Music lane: audio-only playlists UNDER the cut, mixed by the
        # tractor with everything else. Clips are laid freely, so two
        # that overlap go to alternate playlists (M1, M2, ...); a clip is
        # clamped to the sequence length - music never stretches the cut.
        music_rolls: list[Playlist] = []
        music_ends: list[int] = []
        guide = None   # one level detector shared by every ducked bed
        for span in sorted(music_spans or [],
                           key=lambda m: float(m.get("start") or 0.0)):
            path = str(span.get("path") or "")
            if not path or not Path(path).is_file():
                continue
            m_start, m_length = self._span(span)
            m_length = min(m_length, max(0, total - m_start))
            if m_length <= 0:
                continue
            slot = next((i for i, end in enumerate(music_ends)
                         if end <= m_start), None)
            if slot is None:
                music_rolls.append(Playlist(self.timebase, self.audio_format,
                                            name=f"M{len(music_rolls) + 1}"))
                music_ends.append(0)
                slot = len(music_rolls) - 1
            roll = music_rolls[slot]
            producer = self.producer_for(path, f"m{slot}")
            if producer is None:
                continue
            used_keys.add(f"m{slot}|{path}")
            entry = Entry(
                producer=producer,
                source_in=self.timebase.seconds_to_frames(
                    float(span.get("sourceIn") or 0.0)),
                length=m_length,
                clip_id=str(span.get("id") or ""),
            )
            if m_start > music_ends[slot]:
                roll.append_blank(m_start - music_ends[slot])
            m_volume = float(span.get("volume", 1.0)
                             if span.get("volume") is not None else 1.0)
            if abs(m_volume - 1.0) > 1e-6:
                entry.filters.append(Gain(m_volume))
            m_ops = span.get("audioOps")
            if m_ops:
                entry.filters.append(AudioEffect(list(m_ops)))
            if span.get("duck") and float(span.get("duckDb") or 0.0) > 0.0:
                # The guide is the cut itself: both A/V rolls, whose
                # audio this position's mix will pull anyway.
                from ive.audio.ducking import Ducker, GuideLevel

                if guide is None:
                    guide = GuideLevel([roll_a, roll_b],
                                       str(span.get("duckMode") or "simple"))
                entry.filters.append(Ducker(guide,
                                            float(span.get("duckDb"))))
            m_in = self.timebase.seconds_to_frames(
                float(span.get("fadeIn") or 0.0))
            if m_in > 0:
                entry.filters.append(AudioRamp(
                    m_start, m_start + min(m_in, m_length), rising=True))
            m_out = self.timebase.seconds_to_frames(
                float(span.get("fadeOut") or 0.0))
            if m_out > 0:
                entry.filters.append(AudioRamp(
                    m_start + max(0, m_length - m_out), m_start + m_length,
                    rising=False))
            roll.append(entry)
            music_ends[slot] = m_start + m_length
        for roll in music_rolls:
            if roll.length:
                tractor.add_track(Track(roll, video=False, audio=True,
                                        name=roll.name))

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
             "ops": s.get("ops") or [],
             # Insertion order decides who rules an overlap (TimedColor
             # applies only the latest); list position is the fallback.
             "order": int(s.get("order", index))}
            for index, s in enumerate(color_spans or []) if s.get("ops")
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

        if self.with_alpha:
            _enable_alpha(tractor)
        log.info("Graph built: %d clip(s), %d colour span(s), %d overlay "
                 "span(s), %d frames at %s%s",
                 len(usable), len(graded), len(overlays), tractor.length,
                 self.timebase, " with alpha" if self.with_alpha else "")
        self.release_unused(used_keys)
        return tractor


def _enable_alpha(tractor: Tractor) -> None:
    """Turn coverage on along the whole graph, after it is built: the
    bottom colour track goes see-through, the tractor composes alpha,
    every filter that changes coverage (placement, overlays) computes
    it. Filters that do not touch coverage forward it untouched."""
    tractor.with_alpha = True
    for track in tractor.tracks:
        producer = track.producer
        if isinstance(producer, ColourProducer):
            producer.transparent = True
        for entry in getattr(producer, "entries", ()):
            for filt in entry.filters:
                if hasattr(filt, "with_alpha"):
                    filt.with_alpha = True
    for filt in tractor.filters:
        if hasattr(filt, "with_alpha"):
            filt.with_alpha = True


def build_from_project(clips: list[dict], *, fps=25.0,
                       width: int = DEFAULT_WIDTH,
                       height: int = DEFAULT_HEIGHT,
                       proxies=None, use_proxies: bool = True,
                       color_spans: list[dict] | None = None,
                       sticker_spans: list[dict] | None = None,
                       text_spans: list[dict] | None = None,
                       transition_spans: list[dict] | None = None,
                       music_spans: list[dict] | None = None,
                       canvas_fit: str = "fit",
                       alpha: bool = False) -> Tractor:
    """One-shot build, for tests, scripts and the export.

    ``fps`` takes any spelling of a rate (``"30000/1001"``, a Fraction,
    ``29.97``); it is made exact before it becomes the timebase.
    """
    builder = GraphBuilder(Timebase(parse_rate(fps)),
                           AudioFormat(), width, height, proxies, use_proxies)
    builder.canvas_fit = canvas_fit
    builder.with_alpha = bool(alpha)
    return builder.build(clips, color_spans, sticker_spans, text_spans,
                         transition_spans, music_spans=music_spans)
