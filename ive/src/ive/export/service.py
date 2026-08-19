"""Export: turns the timeline into a file, on a worker thread.

The export pulls the SAME graph the preview plays (docs/ENGINE.md 6.2):
video AND audio come out of the tractor frame by frame, with clip volumes,
mutes and the Color lane already applied. The muxer here only writes what
the graph hands it - per-frame RGB arrays and per-frame float32 audio
blocks - so what you watched is what you get.

What is already right and worth keeping: the encoder is chosen from the
machine's capabilities rather than named in the preset, the output is written
to a temporary file and renamed only on success, and cancelling leaves no
half-file behind.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Qt, QThread, Signal, Slot

from ive.engine.builder import build_from_project
from ive.engine.consumer import SequenceWalker
from ive.media.decoder import VideoDecoder

log = logging.getLogger(__name__)

__all__ = ["ExportService"]

#: Logical codec -> encoders to try, best first. Hardware encoders are quick;
#: the software ones are the fallback that always exists.
#: Container id -> FFmpeg muxer name. Needed because the file is written as
#: "<name>.mp4.part" and FFmpeg cannot infer a format from ".part".
_MUXERS: dict[str, str] = {
    "mp4": "mp4", "mov": "mov", "mkv": "matroska", "webm": "webm", "avi": "avi",
}

_ENCODERS: dict[str, tuple[str, ...]] = {
    "h264": ("h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox", "libx264"),
    "h265": ("hevc_nvenc", "hevc_qsv", "hevc_amf", "hevc_videotoolbox", "libx265"),
    "av1": ("av1_nvenc", "libsvtav1", "libaom-av1"),
    "vp9": ("libvpx-vp9",),
    "prores": ("prores_ks", "prores"),
    "mpeg4": ("mpeg4",),
}

#: Logical audio codec -> FFmpeg encoders to try, best first. All of these
#: ship in the PyAV wheels, so the fallback chain is short. PyAV 17 encodes
#: audio from arbitrary-sized frames: it buffers to the encoder's frame_size
#: and converts the sample format internally (verified: aac, libmp3lame,
#: libopus, flac and pcm_s16le all accept our packed-float 1601/1602-sample
#: blocks as-is).
_AUDIO_ENCODERS: dict[str, tuple[str, ...]] = {
    "aac": ("aac",),
    "mp3": ("libmp3lame", "mp3"),
    "opus": ("libopus",),
    "flac": ("flac",),
    "pcm": ("pcm_s16le",),
}

#: Lossless codecs ignore a bitrate; setting one anyway is at best noise.
_LOSSY_AUDIO = {"aac", "mp3", "opus"}


#: Results of the capability probe, which is slow enough to be worth caching.
_encoder_cache: dict[str, str | None] = {}


def _can_open(name: str) -> bool:
    """Whether ``name`` can actually encode on this machine.

    Existing in the FFmpeg build is not enough. ``h264_nvenc`` is present in
    every stock Windows build and fails to open on any machine without a
    usable NVIDIA encode session - no GPU, wrong driver, or all sessions in
    use. The only reliable test is to open a real encoder context.
    """
    from fractions import Fraction

    import av

    # yuv420p first because almost everything takes it, then whatever the
    # codec declares. ProRes only accepts 10-bit 4:2:2, so probing it with
    # yuv420p alone would wrongly report it as unavailable.
    formats = ["yuv420p"]
    try:
        codec = av.codec.Codec(name, "w")
        formats += [str(f.name) for f in (codec.video_formats or ())][:4]
    except Exception:
        pass

    for pix_fmt in formats:
        try:
            context = av.codec.CodecContext.create(name, "w")
            context.width = 64
            context.height = 64
            context.pix_fmt = pix_fmt
            context.framerate = Fraction(25, 1)
            context.open()
            return True
        except Exception as exc:
            last = exc
    log.debug("Encoder %s unusable: %s", name, last)
    return False
    # Note: PyAV 17 has no CodecContext.close(). Calling it raises
    # AttributeError, which an over-broad except reads as "encoder unusable" -
    # that rejected every encoder on the machine until it was found.


def _opens_at(name: str, width: int, height: int, pix_fmt: str, fps: float) -> bool:
    """Whether ``name`` opens with the settings the export will really use."""
    from fractions import Fraction

    import av

    try:
        context = av.codec.CodecContext.create(name, "w")
        context.width = width
        context.height = height
        context.pix_fmt = pix_fmt
        context.framerate = Fraction(max(1, round(fps)), 1)
        context.open()
        return True
    except Exception as exc:
        log.info("Encoder %s cannot handle %dx%d %s: %s",
                 name, width, height, pix_fmt, exc)
        return False


def encoder_for(logical: str, width: int, height: int, pix_fmt: str,
                fps: float) -> str | None:
    """Pick an encoder that works **at the real export settings**.

    A small probe is not enough: h264_qsv opens happily at 64x64 and refuses
    1080x1920, and h264_nvenc is present in every Windows build while failing
    to open at all without a usable NVIDIA session. The only trustworthy test
    is the one that uses the settings the export is about to use.
    """
    for name in _ENCODERS.get(logical, ()):
        if _opens_at(name, width, height, pix_fmt, fps):
            log.info("Encoder chosen for %s: %s", logical, name)
            return name
    return None


def available_encoder(logical: str) -> str | None:
    """Best encoder for ``logical`` that this machine can really use."""
    if logical in _encoder_cache:
        return _encoder_cache[logical]

    chosen = None
    for name in _ENCODERS.get(logical, ()):
        if _can_open(name):
            chosen = name
            break
    if chosen is None:
        log.warning("No usable encoder for %s", logical)
    else:
        log.info("Encoder for %s: %s", logical, chosen)
    _encoder_cache[logical] = chosen
    return chosen


class _Worker(QObject):
    progress = Signal(int, int)          # done, total
    finished = Signal(str)               # output path
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._cancel = False

    @Slot()
    def cancel(self) -> None:
        self._cancel = True

    @Slot(str, str, "QVariantMap")
    def run(self, source: str, destination: str, options: dict) -> None:
        import av

        self._cancel = False
        out_path = Path(destination)
        tmp_path = out_path.with_suffix(out_path.suffix + ".part")
        decoder = None
        container = None
        graph = None
        walker = None
        try:
            # A sequence renders through the graph; a bare file still opens
            # a decoder, because previewing a pool item has no timeline.
            clips = list(options.get("clips") or [])
            decoder = VideoDecoder(source)
            width = int(options.get("width") or decoder.video.display_size[0])
            height = int(options.get("height") or decoder.video.display_size[1])
            # Encoders reject odd dimensions with yuv420p.
            width -= width % 2
            height -= height % 2

            logical = str(options.get("video_codec") or "h264")
            fps = decoder.fps
            pix_fmt = "yuv422p10le" if logical == "prores" else "yuv420p"
            encoder = encoder_for(logical, width, height, pix_fmt, fps)
            if encoder is None:
                self.failed.emit(f"no_encoder:{logical}")
                return
            fps = float(fps)
            if clips:
                # Sticker spans arrive as pure data (a QVariantMap crossing
                # the thread boundary would drop callables); the sprite
                # closures attach here, on the worker.
                sticker_spans = list(options.get("sticker_spans") or [])
                if sticker_spans:
                    from ive.stickers.raster import attach_sprites

                    sticker_spans = attach_sprites(sticker_spans)
                text_spans = list(options.get("text_spans") or [])
                if text_spans:
                    from ive.text.raster import attach_text_sprites

                    text_spans = attach_text_sprites(text_spans)
                # use_proxies=False is not a detail: rendering a delivery from
                # stand-in files is wasted work the user only finds afterwards.
                graph = build_from_project(
                    clips, fps=fps, width=width, height=height, proxies=None,
                    use_proxies=False,
                    color_spans=list(options.get("color_spans") or []),
                    sticker_spans=sticker_spans, text_spans=text_spans)
                walker = SequenceWalker(graph, want_image=True,
                                        want_audio=True)
                total = graph.length
                log.info("Export renders the SEQUENCE: %d clip(s), %d frames",
                         len(clips), total)
            else:
                total = decoder.frame_count
            out_path.parent.mkdir(parents=True, exist_ok=True)

            muxer = _MUXERS.get(str(options.get("container") or "mp4"), "mp4")
            container = av.open(str(tmp_path), "w", format=muxer)
            stream = container.add_stream(encoder, rate=round(fps))
            stream.width = width
            stream.height = height
            stream.pix_fmt = pix_fmt
            bitrate = int(options.get("video_bitrate_kbps") or 12000)
            stream.bit_rate = bitrate * 1000

            # Audio only exists when the graph renders: the graph mixes every
            # clip's sound (volume, mute, music tracks) into one stereo
            # stream. The bare-file fallback stays video-only, as before.
            audio_stream = None
            if walker is not None:
                audio_stream = self._add_audio_stream(
                    container, options, graph.audio_format)

            log.info(
                "Export started: %s -> %s (%dx%d, %s via %s, %d kbps, "
                "%d frames, audio=%s)",
                Path(source).name, out_path.name, width, height, logical,
                encoder, bitrate, total,
                audio_stream.codec_context.codec.name if audio_stream else "no",
            )

            import numpy as np
            from fractions import Fraction

            sample_pts = 0
            if audio_stream is not None:
                audio_tb = Fraction(1, graph.audio_format.sample_rate)

            last_array = None
            for index in range(total):
                if self._cancel:
                    log.info("Export cancelled at frame %d", index)
                    self._cleanup(container, tmp_path)
                    self.failed.emit("cancelled")
                    return
                if walker is not None:
                    pulled = walker.pull(index)
                    array = pulled.image() if pulled is not None else None
                else:
                    pulled = decoder.frame_at(index)
                    array = pulled.array if pulled is not None else None
                if array is None:
                    if walker is None:
                        # Mid-file this is a decode error, and encoding what
                        # was read so far as a SUCCESS hands the user half a
                        # video with no warning. Only the very tail may
                        # legitimately come up short: frame_count can be an
                        # estimate from the container duration.
                        if index >= total - 2:
                            break
                        log.error("Decode failed at frame %d of %d", index, total)
                        self._cleanup(container, tmp_path)
                        self.failed.emit(f"decode_failed:{index}")
                        return
                    # A hole in the timeline still occupies time. Skipping it
                    # shifted every later frame earlier and shortened the
                    # file; a held frame (or black) keeps the timing honest.
                    array = last_array if last_array is not None else np.zeros(
                        (height, width, 3), dtype=np.uint8)
                last_array = array
                video_frame = av.VideoFrame.from_ndarray(array, format="rgb24")
                video_frame = video_frame.reformat(width=width, height=height,
                                                   format=stream.pix_fmt)
                for packet in stream.encode(video_frame):
                    container.mux(packet)

                if audio_stream is not None:
                    # The sound of THIS frame, from the same pull as the
                    # picture. A frame with no sound (a hole, a mute) still
                    # occupies its exact sample count - silence keeps every
                    # later sample in sync, skipping would slide the mix.
                    if pulled is not None:
                        samples = pulled.audio()
                        if samples is None:
                            samples = pulled.silence()
                    else:
                        fmt = graph.audio_format
                        _, count = fmt.sample_bounds(index, graph.timebase)
                        samples = np.zeros((count, fmt.channels),
                                           dtype=np.float32)
                    block = np.ascontiguousarray(samples, dtype=np.float32)
                    audio_frame = av.AudioFrame.from_ndarray(
                        block.reshape(1, -1), format="flt",
                        layout="stereo" if block.shape[1] == 2 else "mono")
                    audio_frame.sample_rate = graph.audio_format.sample_rate
                    audio_frame.pts = sample_pts
                    audio_frame.time_base = audio_tb
                    sample_pts += block.shape[0]
                    for packet in audio_stream.encode(audio_frame):
                        container.mux(packet)

                if index % 10 == 0:
                    self.progress.emit(index, total)

            for packet in stream.encode():
                container.mux(packet)
            if audio_stream is not None:
                for packet in audio_stream.encode():
                    container.mux(packet)
            container.close()
            container = None
            tmp_path.replace(out_path)      # only now does the file become real

            self.progress.emit(total, total)
            log.info("Export finished: %s", out_path)
            self.finished.emit(str(out_path))
        except Exception as exc:
            log.exception("Export failed")
            self._cleanup(container, tmp_path)
            self.failed.emit(str(exc))
        finally:
            if graph is not None:
                graph.close()
            if decoder is not None:
                decoder.close()

    @staticmethod
    def _add_audio_stream(container, options: dict, audio_format):
        """Open the audio stream, or ``None`` for a soundless export.

        Failing to open an audio encoder must not kill the export: a video
        without its sound is a lesser file the log explains, a failed export
        is lost work.
        """
        logical = str(options.get("audio_codec") or "aac")
        names = _AUDIO_ENCODERS.get(logical) or _AUDIO_ENCODERS["aac"]
        for name in names:
            try:
                stream = container.add_stream(name,
                                              rate=audio_format.sample_rate)
                stream.layout = "stereo" if audio_format.channels == 2 else "mono"
                if logical in _LOSSY_AUDIO:
                    kbps = int(options.get("audio_bitrate_kbps") or 192)
                    stream.bit_rate = kbps * 1000
                return stream
            except Exception:
                log.warning("Audio encoder %s failed to open", name,
                            exc_info=True)
        log.error("No usable audio encoder for %s: exporting without sound",
                  logical)
        return None

    @staticmethod
    def _cleanup(container, tmp_path: Path) -> None:
        if container is not None:
            try:
                container.close()
            except Exception:
                pass
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            log.warning("Could not remove the partial file %s", tmp_path)


class ExportService(QObject):
    """Drives the export worker and reports progress to QML."""

    stateChanged = Signal()
    progressChanged = Signal()
    completed = Signal(str)
    failed = Signal(str)

    _start = Signal(str, str, "QVariantMap")
    _cancel = Signal()

    def __init__(self, parent: QObject | None = None, *, playback=None) -> None:
        #: Where the timeline comes from, so export renders the SEQUENCE from
        #: the same model the preview plays.
        self._playback = playback
        super().__init__(parent)
        self._running = False
        self._done = 0
        self._total = 0
        self._output = ""

        self._thread = QThread()
        self._thread.setObjectName("export")
        self._worker = _Worker()
        self._worker.moveToThread(self._thread)
        self._start.connect(self._worker.run)
        # Direct on purpose, and by name: the worker thread is busy inside
        # run(), so a queued cancel would only be delivered when the export
        # is already over. (`type=0` was AutoConnection, which across threads
        # IS queued - the cancel button did nothing.)
        self._cancel.connect(self._worker.cancel,
                             type=Qt.ConnectionType.DirectConnection)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    # ── properties ────────────────────────────────────────────────────

    @Property(bool, notify=stateChanged)
    def running(self) -> bool:
        return self._running

    @Property(float, notify=progressChanged)
    def progress(self) -> float:
        return (self._done / self._total) if self._total else 0.0

    @Property(str, notify=stateChanged)
    def output(self) -> str:
        return self._output

    @Property("QVariantList", constant=True)
    def encoders(self) -> list[dict[str, Any]]:
        """Which logical codecs this machine can actually write."""
        from ive.export.presets import VIDEO_CODECS

        return [
            {"id": key, "label": label, "encoder": available_encoder(key) or "",
             "available": available_encoder(key) is not None}
            for key, label in VIDEO_CODECS.items()
        ]

    @Property("QVariantList", constant=True)
    def presets(self) -> list[dict[str, Any]]:
        from ive.export.presets import as_maps

        return as_maps()

    @Property("QVariantList", constant=True)
    def platforms(self) -> list[dict[str, Any]]:
        """The social platforms, one icon each, in display order."""
        from ive.export.presets import PLATFORMS

        return [dict(entry) for entry in PLATFORMS]

    @Property("QVariantList", constant=True)
    def containers(self) -> list[dict[str, Any]]:
        """Containers with the codecs each accepts.

        Every nested sequence is converted to a **list**: a Python tuple
        reaches QML as an opaque wrapper without ``.map()``, and the codec
        pickers silently come up empty.
        """
        from ive.export.presets import CONTAINERS

        out = []
        for entry in CONTAINERS:
            item = dict(entry)
            item["video"] = list(item.get("video", ()))
            item["audio"] = list(item.get("audio", ()))
            out.append(item)
        return out

    @Slot(str, result=str)
    def codecLabel(self, codec_id: str) -> str:
        from ive.export.presets import AUDIO_CODECS, VIDEO_CODECS

        return VIDEO_CODECS.get(codec_id) or AUDIO_CODECS.get(codec_id) or codec_id

    def current_source(self, playback) -> str:
        """The file this export renders.

        Still returned for the label and for the single-file case. When the
        timeline holds a sequence the export walks the graph instead - see
        `sequence_clips` on the playback service - so this is the first clip,
        not the whole story.

        Always the FIRST segment, never the clip under the playhead: the
        sequence timebase is the first clip's (transport sets fps from it),
        and fps and default dimensions are derived from this file. Matching
        the playhead clip made the exported file's frame rate and size depend
        on where the cursor happened to be parked.
        """
        segments = getattr(playback, "_segments", None)
        if segments:
            return segments[0].path
        raise RuntimeError("No media is loaded")

    # ── control ───────────────────────────────────────────────────────

    def start(self, source: str, destination: str, options: dict) -> bool:
        if self._running:
            log.warning("An export is already running")
            return False
        if not Path(source).is_file():
            self.failed.emit("no_source")
            return False
        clips = []
        # A single previewed file is a one-clip sequence to the transport, so
        # it renders through the graph too - that is what carries its AUDIO
        # into the file. The gate used to be `isSequence`, which sent single
        # files down the video-only decoder path.
        if self._playback is not None and getattr(self._playback, "hasMedia", False):
            try:
                clips = self._playback.sequence_clips()
            except Exception:
                log.exception("Could not read the sequence; exporting one file")
        if clips:
            options = dict(options)
            options["clips"] = clips
            spans = getattr(self._playback, "sequence_color_spans", None)
            if callable(spans):
                # The Color lane grades the export exactly as it grades the
                # preview: same graph, same recipes.
                options["color_spans"] = spans()
            stickers = getattr(self._playback, "sequence_sticker_spans", None)
            if callable(stickers):
                options["sticker_spans"] = stickers()
            texts = getattr(self._playback, "sequence_text_spans", None)
            if callable(texts):
                options["text_spans"] = texts()

        self._running = True
        self._done = 0
        self._total = 0
        self._output = destination
        self.stateChanged.emit()
        self.progressChanged.emit()
        self._start.emit(source, destination, options)
        return True

    @Slot()
    def cancel(self) -> None:
        if self._running:
            self._cancel.emit()

    # ── reactions ─────────────────────────────────────────────────────

    def _on_progress(self, done: int, total: int) -> None:
        self._done, self._total = done, total
        self.progressChanged.emit()

    def _on_finished(self, path: str) -> None:
        self._running = False
        self._output = path
        self.stateChanged.emit()
        self.completed.emit(path)

    def _on_failed(self, message: str) -> None:
        self._running = False
        self.stateChanged.emit()
        self.failed.emit(message)

    def shutdown(self) -> None:
        self.cancel()
        self._thread.quit()
        if not self._thread.wait(4000):
            log.warning("Export thread did not stop in time")
            self._thread.terminate()
            self._thread.wait(1000)
