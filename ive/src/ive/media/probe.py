"""Media inspection: what a file contains, without decoding it.

Reads container and stream metadata only, so opening a media pool of hundreds
of files stays fast. Everything a clip needs to be placed on a timeline comes
from here; pixels come from :mod:`ive.media.decoder`.
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
            parts.append(f"video={v.codec} {w}x{h} @{float(v.fps):.3f}fps rot={v.rotation}")
        for a in self.audio:
            parts.append(f"audio={a.codec} {a.sample_rate}Hz x{a.channels}")
        return " | ".join(parts)


def _rotation_of(stream) -> int:
    """Rotation in degrees, from metadata or the display matrix."""
    raw = stream.metadata.get("rotate")
    if raw:
        try:
            return int(float(raw)) % 360
        except (TypeError, ValueError):
            pass
    # Newer FFmpeg exposes it as display matrix side data instead.
    try:
        for side in stream.side_data:
            if "DISPLAYMATRIX" in str(side.type).upper():
                return int(round(float(side.rotation))) % 360
    except Exception:  # pragma: no cover - depends on the PyAV build
        log.debug("Could not read the display matrix of stream %s", stream.index)
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
