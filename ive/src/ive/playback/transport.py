"""Playback transport: position, play/pause and frame delivery.

Plays either a **single file** (preview a pool item) or a **sequence** (the
project timeline, clip after clip). Both are the same object because the
transport controls, the timeline and the readout should not care which one is
loaded.

Four decisions worth keeping:

* **when audio plays, audio is the clock.** The sound card consumes samples at
  its own crystal's rate, and video timed by anything else slides against it -
  lip sync gone within minutes. The playhead follows how much sound the device
  has processed (see playback/audio_output.py); QElapsedTimer remains only as
  the fallback for machines with no audio device;
* the fallback clock is **elapsed time**, never a tick count. A QTimer never
  fires exactly on schedule, and counting ticks makes playback drift away from
  the timecode within seconds;
* every frame comes from the **render graph**, never from a decoder this
  class opened itself. That is the rule in docs/ENGINE.md 3: the graph is
  derived from the model, and preview and export pull the same one. It is also
  what gives playback the proxies for free - the graph resolves them, this
  class does not know they exist;
* frames are produced **ahead of the clock**, in sequence, and the clock takes
  whatever is ready. Asking at the clock instead measured 2.1 fps against 30 -
  see tests/test_playback_pacing.py and the note in media/reader.py. Audio
  rides the same buffer: the read-ahead thread is the only one allowed to pull
  on the graph, so it evaluates both stacks and the tick collects the sound
  with `take_audio` ahead of taking the pictures.
"""

from __future__ import annotations

import logging
from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QElapsedTimer,
    QObject,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage

from ive.engine.builder import GraphBuilder
from ive.engine.frame import AudioFormat, Timebase
from ive.media.reader import VideoReader
from ive.playback.audio_output import AudioOutput

log = logging.getLogger(__name__)

__all__ = ["PlaybackService"]


@dataclass
class _Segment:
    """One clip as the transport sees it: where it sits, and what it plays."""

    path: str
    start: float          # seconds on the timeline
    duration: float
    fps: float
    #: Offset into the source file. Split and trim set this.
    source_in: float = 0.0
    #: Display aspect of the source, for shaping the view around this clip.
    aspect: float = 16.0 / 9.0
    #: Audio gain of this clip: 0 silent, 1 as recorded, up to 2.
    volume: float = 1.0

    @property
    def end(self) -> float:
        return self.start + self.duration


class PlaybackService(QObject):
    """What the transport controls and the timeline talk to."""

    stateChanged = Signal()
    mediaChanged = Signal()
    positionChanged = Signal()
    frameImage = Signal(QImage)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None, *,
                 proxies=None, settings=None) -> None:
        super().__init__(parent)
        #: Resolves a source path to its proxy. The graph asks; we do not.
        self._proxies = proxies
        self._settings = settings
        self._builder: GraphBuilder | None = None
        self._graph = None
        #: Identifies the current graph to the read-ahead, so frames produced
        #: for a graph that has since been rebuilt are never shown.
        self._graph_key = ""
        self._graph_serial = 0
        self._preview_size = (0, 0)
        self._reader = VideoReader(self)
        self._reader.frameReady.connect(self._on_frame)
        self._reader.failed.connect(self._on_failed)

        self._segments: list[_Segment] = []
        self._starts: list[float] = []          # for bisect
        #: Colour-effect stretches (seconds + resolved ops) from the
        #: Color lane; rebuilt with the sequence.
        self._color_spans: list[dict] = []
        #: Sticker stretches (seconds + file/kind/transform) from the
        #: Sticker lane; pure data - sprites attach at graph build.
        self._sticker_spans: list[dict] = []
        self._playing = False
        self._position = 0.0                    # seconds on the timeline
        self._duration = 0.0                    # seconds
        self._fps = 25.0
        self._name = ""
        self._aspect = 16.0 / 9.0
        self._is_sequence = False
        #: Path the reader is currently decoding ahead on. "" when paused.
        self._streaming: str = ""
        #: True while waiting for the read-ahead to produce its first frame.
        self._priming = False
        #: True when the producer is running only to show one paused frame.
        self._scrubbing = False

        self._clock = QElapsedTimer()
        self._anchor = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)

        #: The sound and, when it runs, the clock (see the module docstring).
        self._audio = AudioOutput(self)
        # Pay the backend's ~0.5 s first-touch cost now, in the background,
        # instead of inside the first play() where it delays the first frame.
        AudioOutput.warm_up()
        self._audio_tried = False           # configure() attempted once
        self._audio_ready = False           # a device accepted our format
        #: Stall detection: consecutive ticks with the audio clock frozen.
        self._audio_last_elapsed = -1.0
        self._audio_stalled_ticks = 0

    # ── properties for QML ────────────────────────────────────────────

    @Property(bool, notify=mediaChanged)
    def hasMedia(self) -> bool:
        return self._duration > 0 and bool(self._segments)

    @Property(bool, notify=mediaChanged)
    def isSequence(self) -> bool:
        """True when playing the project timeline rather than a single file."""
        return self._is_sequence

    @Property(str, notify=mediaChanged)
    def name(self) -> str:
        return self._name

    @Property(int, notify=mediaChanged)
    def clipCount(self) -> int:
        return len(self._segments)

    @Property(float, notify=mediaChanged)
    def aspect(self) -> float:
        """The canvas aspect: what the sequence composites at."""
        return self.canvas_aspect()

    @Property(float, notify=positionChanged)
    def viewAspect(self) -> float:
        """What the video ITEM should be shaped like, at this playhead.

        With an EXPLICIT canvas this is the canvas, bars and all: the user
        chose the frame, and hiding it would lie about the export. On "auto"
        there is no chosen frame, so the view hugs the CURRENT clip instead:
        the item takes the clip's ratio and the composited canvas is
        centre-cropped to it (PreviewItem fillMode "cover"), which removes
        exactly the bars the compositor baked in - the clip is fitted and
        centred in the canvas, so nothing of the picture is lost. That lets
        the ambient backdrop fill the sides of a 9:16 clip in a 16:9 timeline
        instead of showing the canvas' own black pillars (reported on a real
        project: "black background as tall as the video" while playing).

        Notify is positionChanged: the value changes when the playhead
        crosses into a clip of a different shape.
        """
        if self._canvas_name() in self.CANVASES:
            return self.canvas_aspect()
        segment = self._segment_at(self._position)
        return segment.aspect if segment else self.canvas_aspect()

    @Property(float, notify=mediaChanged)
    def fps(self) -> float:
        return self._fps

    @Property(int, notify=mediaChanged)
    def duration(self) -> int:
        """Length in frames, at the sequence frame rate."""
        return int(round(self._duration * self._fps))

    @Property(float, notify=mediaChanged)
    def durationSeconds(self) -> float:
        return self._duration

    @Property(bool, notify=stateChanged)
    def playing(self) -> bool:
        return self._playing

    @Property(int, notify=positionChanged)
    def position(self) -> int:
        return int(round(self._position * self._fps))

    @Property(float, notify=positionChanged)
    def positionSeconds(self) -> float:
        return self._position

    @Property(str, notify=positionChanged)
    def timecode(self) -> str:
        return self.format_timecode(self.position)

    @Property(str, notify=positionChanged)
    def currentClipName(self) -> str:
        segment = self._segment_at(self._position)
        return Path(segment.path).name if segment else ""

    # ── loading ───────────────────────────────────────────────────────

    def open(self, path: str | Path) -> bool:
        """Load one file as the whole timeline.

        Audio-only files load too: their picture is a hole the black track
        fills, and the sound plays like any clip's.
        """
        info = self._reader.describe(path)
        if info is None or not (info.has_video or info.has_audio):
            self.error.emit(f"Cannot preview {Path(str(path)).name}")
            return False
        video = info.primary_video
        fps = (float(video.fps) or 25.0) if video is not None else 25.0
        segment = _Segment(str(path), 0.0, info.duration or 1.0, fps,
                           aspect=self._aspect_of(video))
        self._color_spans = []      # a bare file has no Color lane
        self._sticker_spans = []
        self._apply_segments([segment], sequence=False,
                             name=Path(str(path)).name)
        return True

    @staticmethod
    def _aspect_of(video) -> float:
        if video is None:
            return 16.0 / 9.0
        width, height = video.display_size
        return (width / height) if height else 16.0 / 9.0

    @Slot("QVariantList", result=bool)
    def open_sequence(self, clips: list) -> bool:
        """Load the project timeline: a list of ``{path, start, duration}``.

        Called again whenever the timeline changes; the playhead keeps its
        position so editing does not throw the user back to zero.
        """
        segments: list[_Segment] = []
        spans: list[dict] = []
        sticker_spans: list[dict] = []
        for entry in clips or []:
            sticker_id = str(entry.get("stickerId") or "")
            if sticker_id:
                # A Sticker-lane clip: not a segment, an overlaid stretch.
                # File and kind are resolved HERE so the graph (and the
                # export, which shares it) never knows the catalogue.
                from ive.stickers.library import sticker_by_id

                sticker = sticker_by_id(sticker_id)
                if sticker is None:
                    log.warning("Unknown sticker %r skipped", sticker_id)
                    continue
                sticker_spans.append({
                    "id": str(entry.get("id") or ""),
                    "start": float(entry.get("start") or 0.0),
                    "end": float(entry.get("end") or 0.0),
                    "path": sticker["path"],
                    "kind": sticker["kind"],
                    "x": float(entry.get("x", 0.5)),
                    "y": float(entry.get("y", 0.5)),
                    "scale": float(entry.get("scale", 0.3)),
                    "rotation": float(entry.get("rotation", 0.0)),
                })
                continue
            effect_id = str(entry.get("effectId") or "")
            if effect_id:
                # A Color-lane clip: not a segment, a graded stretch. The
                # recipe is resolved HERE so the graph (and the export,
                # which shares it) never has to know the catalogue.
                from ive.color.library import ops_for

                spans.append({
                    "start": float(entry.get("start") or 0.0),
                    "end": float(entry.get("end") or 0.0),
                    "ops": ops_for(effect_id),
                })
                continue
            path = str(entry.get("path") or "")
            if not path or not Path(path).is_file():
                continue
            info = self._reader.describe(path)
            # Audio-only clips (music under the cut) belong in the sequence:
            # their picture is a hole, their sound is the point.
            if info is None or not (info.has_video or info.has_audio):
                continue
            video = info.primary_video
            segments.append(_Segment(
                path=path,
                start=float(entry.get("start") or 0.0),
                duration=float(entry.get("duration") or info.duration or 1.0),
                fps=(float(video.fps) or 25.0) if video is not None else 25.0,
                source_in=float(entry.get("sourceIn") or 0.0),
                aspect=self._aspect_of(video),
                # Removed or muted audio is volume 0 as far as the graph
                # cares; the stored volume survives in the project for the
                # restore/unmute.
                volume=0.0 if (entry.get("audioEnabled") is False
                               or entry.get("muted") is True)
                       else float(entry.get("volume", 1.0)
                                  if entry.get("volume") is not None else 1.0),
            ))
        segments.sort(key=lambda s: s.start)

        if not segments:
            self.close()
            return False
        self._color_spans = spans
        self._sticker_spans = sticker_spans
        self._apply_segments(segments, sequence=True, name="")
        return True

    def sequence_color_spans(self) -> list[dict]:
        """The Color-lane stretches, resolved to recipes, for the export."""
        return [dict(span) for span in self._color_spans]

    def sequence_sticker_spans(self) -> list[dict]:
        """The Sticker-lane stretches, resolved to files, for the export.

        Pure data on purpose: the export options cross a thread boundary
        as a QVariantMap, which would drop callables - the worker attaches
        the sprite closures itself (stickers/raster.attach_sprites). The
        preview attaches its own closures IN PLACE on these dicts, so the
        copy strips them explicitly."""
        return [{k: v for k, v in span.items() if k != "sprite"}
                for span in self._sticker_spans]

    @Slot(str, float, float, float, float)
    def set_sticker_live(self, clip_id: str, x: float, y: float,
                         scale: float, rotation: float) -> None:
        """Move a sticker on the canvas WHILE a handle is being dragged.

        This is the live half of the gesture: it mutates the very span
        dicts the graph's Overlays filter (and the sprite closures) read
        at process time - same clamps as the model - and re-requests the
        paused frame, so the sticker follows the hand without a graph
        rebuild and without touching the undo stack. The release commits
        the real ``timeline.set_clip_transform`` action, which rebuilds
        from the model and records ONE undo step for the whole drag.
        """
        for span in self._sticker_spans:
            if span.get("id") != clip_id:
                continue
            span["x"] = min(1.0, max(0.0, float(x)))
            span["y"] = min(1.0, max(0.0, float(y)))
            span["scale"] = min(2.0, max(0.02, float(scale)))
            span["rotation"] = float(rotation)
            if not self._playing:
                self._request_at(self._position)
            return

    def _apply_segments(self, segments: list[_Segment], *, sequence: bool,
                        name: str) -> None:
        was_playing = self._playing
        keep = self._position if sequence and self._segments else 0.0

        self._segments = segments
        self._starts = [s.start for s in segments]
        self._is_sequence = sequence
        self._duration = max((s.end for s in segments), default=0.0)
        # The sequence runs at the first clip's rate. A real sequence timebase
        # comes with the project settings; until then this keeps the timecode
        # meaningful instead of inventing a number.
        self._fps = segments[0].fps if segments else 25.0
        self._name = name or (Path(segments[0].path).name if segments else "")

        info = self._reader.describe(segments[0].path) if segments else None
        if info is not None and info.primary_video is not None:
            width, height = info.primary_video.display_size
            self._aspect = (width / height) if height else 16.0 / 9.0

        self._position = min(keep, max(0.0, self._duration - 1e-3))
        self._rebuild_graph()
        log.info("Loaded %s: %d clip(s), %.2fs @ %.3f fps",
                 "sequence" if sequence else "single file",
                 len(segments), self._duration, self._fps)

        self.mediaChanged.emit()
        self.positionChanged.emit()
        self._request_at(self._position)
        if was_playing and sequence:
            self._anchor = self._position
            self._clock.restart()
            # The timeline changed under a running playhead: the read-ahead is
            # decoding a clip that may no longer be there.
            self._start_stream_at(self._position)
        elif was_playing:
            self.pause()

    def sequence_clips(self) -> list[dict]:
        """The timeline as clip dicts, for anyone building the same graph.

        Export uses this so it renders the SEQUENCE from the same model the
        preview does, instead of reopening one file and calling it the
        project. See docs/ENGINE.md 3.
        """
        return [
            {"path": segment.path, "start": segment.start,
             "duration": segment.duration, "sourceIn": segment.source_in,
             "volume": segment.volume, "id": str(index)}
            for index, segment in enumerate(self._segments)
        ]

    # -- the graph ----------------------------------------------------

    #: Named canvases, as ratios. "auto" is resolved from the first clip.
    CANVASES = {
        "16:9": 16 / 9, "9:16": 9 / 16, "4:3": 4 / 3,
        "1:1": 1.0, "21:9": 21 / 9,
    }

    def _canvas_name(self) -> str:
        name = "auto"
        if self._settings is not None:
            try:
                # get() takes only the key (the schema supplies the default);
                # a second argument is a TypeError this except would swallow.
                name = str(self._settings.get("project.canvas"))
            except Exception:
                pass
        return name

    def canvas_aspect(self) -> float:
        """The aspect the SEQUENCE composites at.

        Not the first clip's, unless the project says "auto". A canvas that
        follows whichever clip happens to be first changes under the user when
        the timeline is reordered, and silently reframes everything else.
        """
        return self.CANVASES.get(self._canvas_name(), self._aspect)

    def _preview_canvas(self) -> tuple[int, int]:
        """The size the sequence composites at.

        Not the source size. Compositing a 540p proxy onto a 4K canvas scales
        it straight back up, which measured 250 ms a frame and made the proxy
        slower than the original it was meant to replace.
        """
        height = 720
        if self._settings is not None:
            try:
                height = int(self._settings.get("media.preview_height"))
            except Exception:
                pass
        height = max(360, min(2160, height)) & ~1
        width = max(2, int(round(height * self.canvas_aspect())) & ~1)
        return width, height

    def _rebuild_graph(self) -> None:
        """Derive the graph from the segments. Never edited on its own."""
        # Nothing may pull on the graph while it is replaced.
        if not self._reader.suspend_stream():
            # The producer did not park: replacing the graph now would close
            # decoders under a thread still decoding on them - an access
            # violation inside FFmpeg, not an exception. Keeping the old
            # graph for one more edit is the lesser evil; the next edit
            # tries again.
            log.error("Graph rebuild skipped: the producer did not park")
            return

        if not self._segments:
            if self._builder is not None:
                self._builder.close()
            self._builder = None
            self._graph = None
            self._graph_key = ""
            return

        width, height = self._preview_canvas()
        timebase = Timebase(Fraction(self._fps).limit_denominator(1001))
        if self._builder is None or self._preview_size != (width, height):
            if self._builder is not None:
                self._builder.close()
            self._builder = GraphBuilder(timebase, AudioFormat(), width, height,
                                         self._proxies, use_proxies=True)
            self._preview_size = (width, height)
        else:
            self._builder.timebase = timebase

        clips = [
            {"path": segment.path, "start": segment.start,
             "duration": segment.duration, "sourceIn": segment.source_in,
             "volume": segment.volume, "id": str(index)}
            for index, segment in enumerate(self._segments)
        ]
        sticker_spans = self._sticker_spans
        if sticker_spans:
            from ive.stickers.raster import attach_sprites

            sticker_spans = attach_sprites(sticker_spans)
        self._graph = self._builder.build(clips, self._color_spans,
                                          sticker_spans)
        self._graph_serial += 1
        self._graph_key = f"graph-{self._graph_serial}"
        log.info("Preview graph rebuilt at %dx%d: %d frames",
                 width, height, self._graph.length)

    def _produce(self, index: int):
        """Pull one frame out of the graph. Runs on the read-ahead thread.

        Both stacks are evaluated HERE, on the one thread allowed to pull on
        the graph: decoding sound on the GUI thread would stall the interface,
        and a second thread pulling for audio alone is the `generator already
        executing` crash the suspend protocol exists to prevent.
        """
        graph = self._graph
        if graph is None:
            return None
        frame = graph.frame_at(index)
        if frame is None:
            return None
        image = frame.image()
        audio = frame.audio()
        if image is None and audio is None:
            return None
        return (index / self._fps if self._fps else 0.0, image, audio)

    @Slot()
    def close(self) -> None:
        self.pause()
        parked = self._reader.suspend_stream(timeout=5.0)
        if self._builder is not None:
            if parked:
                self._builder.close()
            else:
                # Closing decoders under a thread still pulling on them is a
                # native crash. Dropping the references instead leaks a few
                # decoder handles once, which the OS reclaims at exit.
                log.error("Producer did not park; leaking the old graph "
                          "instead of closing it underneath the reader")
        self._builder = None
        self._graph = None
        self._graph_key = ""
        self._reader.close()
        self._segments = []
        self._starts = []
        self._color_spans = []
        self._sticker_spans = []
        self._duration = 0.0
        self._position = 0.0
        self._name = ""
        self._is_sequence = False
        self.mediaChanged.emit()
        self.positionChanged.emit()

    # ── transport ─────────────────────────────────────────────────────

    @Slot()
    def play(self) -> None:
        if self._playing or not self.hasMedia:
            return
        if self._position >= self._duration - 1e-3:
            self._position = 0.0
        if not self._audio_tried:
            # One attempt per session: a machine without a device stays
            # silent on the timer clock, and asking again every play would
            # just log the same warning forever.
            self._audio_tried = True
            self._audio_ready = self._audio.configure(AudioFormat())
        self._playing = True
        # A paused view may still be waiting for its single frame. Leaving the
        # flag set makes the first tick of playback deliver that frame and then
        # stop the producer, so playback dies one frame in - and only when the
        # user presses play quickly enough to beat the scrub.
        self._scrubbing = False
        self._anchor = self._position
        self._clock.restart()
        self._start_stream_at(self._position)
        # Slightly faster than the frame rate, so scheduler jitter does not
        # cost whole frames.
        self._timer.start(max(4, int(1000 / (self._fps * 1.5))))
        log.info("Playback started at %.2fs", self._position)
        self.stateChanged.emit()

    @Slot()
    def pause(self) -> None:
        if not self._playing:
            return
        self._playing = False
        self._timer.stop()
        self._reader.stop_stream()
        self._audio.stop()
        self._streaming = ""
        log.info("Playback paused at %.2fs", self._position)
        self.stateChanged.emit()

    @Slot()
    def toggle(self) -> None:
        self.pause() if self._playing else self.play()

    @Slot(int)
    def seek(self, frame: int) -> None:
        self.seek_seconds(float(frame) / self._fps if self._fps else 0.0)

    @Slot(float)
    def seek_seconds(self, seconds: float) -> None:
        target = max(0.0, min(float(seconds), max(0.0, self._duration - 1e-3)))
        if abs(target - self._position) < 1e-6:
            return
        self._position = target
        if self._playing:
            # Re-anchor, or the next tick undoes the seek.
            self._anchor = target
            self._clock.restart()
            # Everything decoded ahead belongs to where the user just was.
            self._start_stream_at(target)
            self.positionChanged.emit()
            # No direct request here. It would share the decoder with the
            # read-ahead and move its cursor, so the very next sequential read
            # would no longer be cursor + 1 and would seek - the cost this
            # whole path exists to avoid. The buffer fills in a few ms anyway.
            return
        self.positionChanged.emit()
        self._request_at(target)

    @Slot(int)
    def step(self, delta: int) -> None:
        self.pause()
        self.seek_seconds(self._position + delta / self._fps)

    @Slot()
    def go_to_start(self) -> None:
        self.seek_seconds(0.0)

    @Slot()
    def go_to_end(self) -> None:
        self.seek_seconds(self._duration - 1.0 / self._fps)

    @Slot(int, result=str)
    def format_timecode(self, frame: int) -> str:
        """``HH:MM:SS:FF`` at the sequence frame rate."""
        fps = int(round(self._fps)) or 25
        frame = max(0, int(frame))
        total_seconds = frame // fps
        return (
            f"{total_seconds // 3600:02d}:"
            f"{(total_seconds // 60) % 60:02d}:"
            f"{total_seconds % 60:02d}:"
            f"{frame % fps:02d}"
        )

    # ── internals ─────────────────────────────────────────────────────

    def _segment_at(self, seconds: float) -> _Segment | None:
        """Which clip covers this point on the timeline."""
        if not self._segments:
            return None
        index = bisect_right(self._starts, seconds) - 1
        if index < 0:
            return self._segments[0]
        segment = self._segments[index]
        if seconds >= segment.end and index + 1 < len(self._segments):
            return self._segments[index + 1]
        return segment

    def _request_at(self, seconds: float) -> None:
        """Show the frame at this point while paused - scrubbing, stepping.

        This goes through the SAME graph as playback rather than opening the
        source directly. It has to: the graph is what applies the canvas, the
        letterboxing and the proxies, so a frame fetched around it would not be
        the frame the user is about to play.

        It reuses the read-ahead rather than pulling on the graph from here.
        Only one thread may touch the graph, and pulling a 4K frame on the GUI
        thread would freeze the window for as long as it took.
        """
        if self._graph is None or self._playing:
            return
        self._start_stream_at(seconds)
        self._scrubbing = True
        self._timer.start(16)

    @staticmethod
    def _index_at(seconds: float, segment: _Segment) -> int:
        """Which frame of the source belongs at this point on the timeline.

        Truncated, never rounded, and used by every caller. `_tick` decides
        that the frame changed by comparing truncated frame numbers, so an
        index computed with round() drifts half a frame away from that
        decision: some ticks then ask twice for the same index and find
        nothing new, others skip one and throw a decoded frame away. It
        measured as 30 frames a second leaving the buffer and only 20 reaching
        the screen.
        """
        local = max(0.0, seconds - segment.start) + segment.source_in
        return int(local * segment.fps)

    def _sequence_index(self, seconds: float) -> int:
        """Frame number on the SEQUENCE timeline.

        Truncated, never rounded, and used by every caller. `_tick` decides
        that the frame changed by comparing truncated frame numbers, so an
        index computed with round() drifts half a frame away from that
        decision: some ticks then ask twice for the same index and find
        nothing new, others skip one and throw a produced frame away. It
        measured as 30 frames a second leaving the buffer and 20 reaching the
        screen.
        """
        return max(0, int(max(0.0, seconds) * self._fps))

    def _start_stream_at(self, seconds: float) -> None:
        """Point the read-ahead at this position and let it run."""
        if self._graph is None:
            return
        index = self._sequence_index(seconds)
        end = max(0, self._graph.length - 1)
        # The clamp matters: `seconds_to_frames` rounds while the seek clamp
        # above truncates, so a seek to the extreme end can compute an index
        # of `length` - one PAST `end`. The producer would then park at once
        # with an empty buffer and priming would wait forever for a frame
        # nobody will ever make.
        index = min(index, end)
        if self._playing and self._audio_ready:
            # Everything queued at the sink belongs to the position the user
            # just left; restart discards it and zeroes the audio clock so
            # the priming tick can anchor it to the new position.
            self._audio.restart()
            self._audio_last_elapsed = -1.0
            self._audio_stalled_ticks = 0
        width, height = self._preview_size
        # Hold the clock until the first frame is ready. Starting it straight
        # away means the buffer fills while time is already running, and those
        # frames are late before they exist: measured as a 3 fps loss at every
        # start and every seek. MLT prefills its consumer for the same reason.
        self._priming = True
        self._streaming = self._graph_key
        self._reader.start_stream(self._produce, self._graph_key, index, end,
                                  self._reader.read_ahead_depth(width, height))

    def _tick(self) -> None:
        if self._priming:
            if self._graph is None:
                self._priming = False
            else:
                index = self._sequence_index(self._position)
                taken = self._reader.take_frame(self._graph_key, index)
                if taken is None:
                    # Keep the clock pinned to now: no time passes while we
                    # wait, so nothing arrives late.
                    self._anchor = self._position
                    self._clock.restart()
                    return
                self._priming = False
                self._anchor = self._position
                self._clock.restart()
                if self._playing:
                    # Fill the sink BEFORE time starts running: the buffered
                    # sound is what the clock will advance on, and starting
                    # empty would stall the first ticks on an idle sink.
                    self._pump_audio()
                if taken[2] is not None:
                    self.frameImage.emit(taken[2])
                if self._scrubbing:
                    # A paused view needed exactly one frame. Leaving the
                    # producer running would decode a whole buffer nobody is
                    # going to look at.
                    self._scrubbing = False
                    self._timer.stop()
                    self._reader.stop_stream()
                return

        if not self._playing:
            self._scrubbing = False
            self._timer.stop()
            return

        self._pump_audio()
        # Never backwards: the first audio reading lands a few tens of ms
        # behind the timer that covered the start, and a playhead that steps
        # back - however little - re-shows a frame the user already saw.
        target = max(self._position,
                     self._anchor + self._elapsed_since_anchor())

        if target >= self._duration:
            self.seek_seconds(self._duration - 1.0 / self._fps)
            self.pause()
            return

        # Only look for a new frame when the frame number actually changed;
        # the timer runs faster than the frame rate on purpose.
        before = int(self._position * self._fps)
        after = int(target * self._fps)
        self._position = target
        self.positionChanged.emit()
        if after == before:
            return

        # No special case at a cut any more: the graph is one continuous
        # producer, so the read-ahead crosses a clip boundary without being
        # repointed and without reopening anything.
        index = self._sequence_index(target)
        taken = self._reader.take_frame(self._graph_key, index)
        if taken is not None and taken[2] is not None:
            self.frameImage.emit(taken[2])
        # Nothing ready means the graph is behind: the previous frame stays on
        # screen and the clock keeps running. Playback must lose frames, never
        # time, or it drifts away from the timecode and never returns.

    def _pump_audio(self) -> None:
        """Move ready sound from the read-ahead buffer into the sink."""
        if not (self._audio_ready and self._audio.running):
            return
        room = self._audio.room_samples()
        if room > 0:
            for block in self._reader.take_audio(self._graph_key, room):
                self._audio.push(block)
        self._audio.pump()

    def _elapsed_since_anchor(self) -> float:
        """Seconds since the last anchor, from whichever clock is alive.

        The audio clock rules once the device has processed anything; before
        that (the couple of ticks after a start) and on machines without a
        device, the elapsed timer stands in. If the device stops consuming
        mid-play - unplugged, grabbed exclusively - the playhead would freeze
        with it, so a clock that stands still across a second of ticks is
        abandoned for the timer, re-anchored at the current position.
        """
        timer = self._clock.elapsed() / 1000.0
        if not (self._audio_ready and self._audio.running):
            return timer
        elapsed = self._audio.elapsed_seconds()
        if elapsed <= 0.0:
            return timer
        if elapsed == self._audio_last_elapsed:
            self._audio_stalled_ticks += 1
            if self._audio_stalled_ticks > 45:
                log.warning("Audio clock stalled at %.2fs; falling back to "
                            "the timer clock", elapsed)
                self._audio.stop()
                self._anchor = self._position
                self._clock.restart()
                return 0.0
        else:
            self._audio_last_elapsed = elapsed
            self._audio_stalled_ticks = 0
        return elapsed

    def _on_frame(self, _path: str, _index: int, _time: float, image: QImage) -> None:
        self.frameImage.emit(image)

    def _on_failed(self, message: str) -> None:
        log.warning("Playback error: %s", message)
        self.pause()
        self.error.emit(message)

    def shutdown(self) -> None:
        self.pause()
        self._audio.stop()
        self._reader.shutdown()
