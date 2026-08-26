"""Media inspection: what a file contains.

Reads container and stream metadata, plus at most ONE decoded frame when
a video stream carries no legacy ``rotate`` tag - the display matrix
(how every modern phone records orientation) is only reachable that way
in this PyAV build. Still ~10 ms per file, and imports probe on a worker
thread. Everything a clip needs to be placed on a timeline comes from
here; pixels come from :mod:`ive.media.decoder`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

log = logging.getLogger(__name__)

__all__ = ["MediaInfo", "VideoStreamInfo", "AudioStreamInfo", "probe", "MediaProbeError"]


class MediaProbeError(RuntimeError):
    """The file could not be opened or contains no usable stream."""


@dataclass(frozen=True)
class VideoStreamInfo:
    index: int
    codec: str
    width: int
    height: int
    #: Nominal frame rate. Variable-frame-rate files report an average here.
    fps: Fraction
    #: Rotation in degrees from the container metadata, not baked into pixels.
    rotation: int = 0
    pixel_format: str = ""
    #: Storage aspect vs display aspect; != 1 for anamorphic material.
    sample_aspect_ratio: Fraction = Fraction(1, 1)
    duration: float = 0.0
    frames: int = 0
    #: FFmpeg AVCOL_* ids as tagged in the file; 2 = unspecified.
    #: Transfer 16 = PQ (SMPTE 2084), 18 = HLG (ARIB STD-B67) - the two
    #: ways phones record HDR.
    color_transfer: int = 2
    color_primaries: int = 2
    #: Bits per sample of the stored pixels (8 for classic footage,
    #: 10 for HDR and most log profiles).
    bit_depth: int = 8

    @property
    def is_hdr(self) -> bool:
        """PQ or HLG transfer: the material needs tone mapping to show
        correctly on an SDR canvas (docs/MEDIA_FORMATS.md §8)."""
        return self.color_transfer in (16, 18)

    @property
    def display_size(self) -> tuple[int, int]:
        """Size as it must be shown: rotation and pixel aspect applied.

        Phone footage is the common case: 1920x1080 stored with rotate=90,
        which has to be presented as 1080x1920. Ignoring this shows every
        vertical video on its side.
        """
        w = int(round(self.width * float(self.sample_aspect_ratio)))
        h = self.height
        if self.rotation in (90, 270):
            return h, w
        return w, h


@dataclass(frozen=True)
class AudioStreamInfo:
    index: int
    codec: str
    sample_rate: int
    channels: int
    duration: float = 0.0


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    container: str
    duration: float
    size_bytes: int
    video: list[VideoStreamInfo] = field(default_factory=list)
    audio: list[AudioStreamInfo] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def has_video(self) -> bool:
        return bool(self.video)

    @property
    def has_audio(self) -> bool:
        return bool(self.audio)

    @property
    def primary_video(self) -> VideoStreamInfo | None:
        return self.video[0] if self.video else None

    def describe(self) -> str:
        """One line for the log."""
        parts = [f"{self.path.name} {self.container} {self.duration:.2f}s"]
        for v in self.video:
            w, h = v.display_size
            parts.append(f"video={v.codec} {w}x{h} @{float(v.fps):.3f}fps "
                         f"rot={v.rotation}"
                         + (" HDR" if v.is_hdr else ""))
        for a in self.audio:
            parts.append(f"audio={a.codec} {a.sample_rate}Hz x{a.channels}")
        return " | ".join(parts)


def _rotation_of(stream) -> int:
    """Rotation from the legacy ``rotate`` metadata tag, when present.

    Modern files do not have the tag: FFmpeg dropped it years ago in
    favour of display-matrix side data, which this PyAV build exposes
    only on DECODED frames - see :func:`_frame_rotation`.
    """
    raw = stream.metadata.get("rotate")
    if raw:
        try:
            return int(float(raw)) % 360
        except (TypeError, ValueError):
            pass
    return 0


def _frame_rotation(container, stream) -> int:
    """Rotation in CLOCKWISE display degrees, read off the first frame.

    A phone shoots portrait video stored landscape plus a display
    matrix; PyAV 17 surfaces that matrix only as ``frame.rotation``
    (counterclockwise, ffprobe's convention - an iPhone portrait file
    reads -90), and the stream object has no getter at all. So the probe
    decodes ONE frame when a video stream is present: ~10 ms, the price
    of never showing a vertical video on its side. The sign is flipped
    to the clockwise convention of the old ``rotate`` tag, which is what
    the decoder's ``np.rot90`` mapping was built against.
    """
    try:
        for frame in container.decode(stream):
            raw = getattr(frame, "rotation", 0) or 0
            return int(-round(float(raw))) % 360
    except Exception:
        log.debug("Could not decode a frame for the rotation of %s",
                  stream.index, exc_info=True)
    return 0


#: AV_DISPOSITION_ATTACHED_PIC - stable FFmpeg constant.
_ATTACHED_PIC = 0x0400


def _is_attached_picture(stream) -> bool:
    """True for cover art, which FFmpeg reports as a one-frame video stream.

    ``stream.disposition`` is a Flag enum, so ``getattr(d, "attached_pic")``
    returns the *class member* and is always truthy - it does not test whether
    the flag is set. The bit has to be masked explicitly.
    """
    try:
        return bool(int(getattr(stream, "disposition", 0) or 0) & _ATTACHED_PIC)
    except (TypeError, ValueError):
        return False


def probe(path: str | Path) -> MediaInfo:
    """Read metadata for one media file.

    Raises:
        MediaProbeError: file missing, unreadable, or with no usable stream.
    """
    import av  # imported lazily: it pulls in the FFmpeg libraries

    path = Path(path)
    if not path.is_file():
        raise MediaProbeError(f"File not found: {path}")

    try:
        container = av.open(str(path))
    except Exception as exc:
        raise MediaProbeError(f"Could not open {path.name}: {exc}") from exc

    try:
        duration = float(container.duration or 0) / 1_000_000.0  # av.time_base
        videos: list[VideoStreamInfo] = []
        audios: list[AudioStreamInfo] = []

        for stream in container.streams:
            if stream.type == "video":
                # Cover art is stored as a one-frame video stream; not footage.
                if _is_attached_picture(stream):
                    continue
                rate = stream.average_rate or stream.guessed_rate or Fraction(25, 1)
                stream_duration = (
                    float(stream.duration * stream.time_base) if stream.duration else duration
                )
                ctx = stream.codec_context
                pix_fmt = str(ctx.pix_fmt) if ctx else ""
                bit_depth = (12 if "12" in pix_fmt
                             else 10 if "10" in pix_fmt else 8)
                videos.append(
                    VideoStreamInfo(
                        index=stream.index,
                        codec=stream.codec_context.name if stream.codec_context else "?",
                        width=stream.codec_context.width if stream.codec_context else 0,
                        height=stream.codec_context.height if stream.codec_context else 0,
                        fps=Fraction(rate),
                        rotation=_rotation_of(stream),
                        pixel_format=(
                            str(stream.codec_context.pix_fmt) if stream.codec_context else ""
                        ),
                        sample_aspect_ratio=Fraction(stream.sample_aspect_ratio or 1),
                        duration=stream_duration,
                        frames=int(stream.frames or 0),
                        color_transfer=int(getattr(ctx, "color_trc", 2)
                                           or 2) if ctx else 2,
                        color_primaries=int(getattr(ctx, "color_primaries",
                                                    2) or 2) if ctx else 2,
                        bit_depth=bit_depth,
                    )
                )
            elif stream.type == "audio":
                ctx = stream.codec_context
                audios.append(
                    AudioStreamInfo(
                        index=stream.index,
                        codec=ctx.name if ctx else "?",
                        sample_rate=int(ctx.sample_rate or 0) if ctx else 0,
                        channels=int(getattr(ctx, "channels", 0) or 0) if ctx else 0,
                        duration=(
                            float(stream.duration * stream.time_base)
                            if stream.duration else duration
                        ),
                    )
                )

        if not videos and not audios:
            raise MediaProbeError(f"{path.name} contains no audio or video stream")

        # The display matrix (how EVERY modern phone stores rotation) is
        # only reachable through a decoded frame in this PyAV; ask for it
        # when the metadata tag said nothing. One decode per probe.
        if videos and videos[0].rotation == 0:
            from dataclasses import replace

            stream = next((s for s in container.streams
                           if s.index == videos[0].index), None)
            if stream is not None:
                rotation = _frame_rotation(container, stream)
                if rotation:
                    videos[0] = replace(videos[0], rotation=rotation)

        # Containers sometimes lie about the overall duration; trust the streams.
        if duration <= 0:
            duration = max([s.duration for s in videos + audios] or [0.0])

        info = MediaInfo(
            path=path,
            container=container.format.name if container.format else path.suffix.lstrip("."),
            duration=duration,
            size_bytes=path.stat().st_size,
            video=videos,
            audio=audios,
            metadata=dict(container.metadata),
        )
        log.info("Probed %s", info.describe())
        return info
    finally:
        container.close()
