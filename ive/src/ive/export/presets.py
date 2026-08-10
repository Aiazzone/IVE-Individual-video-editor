"""Export presets.

Presets declare a **logical** codec (``h264``), never a specific encoder
(``h264_nvenc``): the encoder is chosen at runtime from what the machine has.
That is what lets a preset shared between two people work on both.

Definitions live in code for now; they move to JSON files under
``config/defaults/export_presets/`` once the content-pack loader exists, and
the shape here is already the shape of those files.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

__all__ = ["ExportPreset", "SOCIAL_PRESETS", "PLATFORMS", "CONTAINERS",
           "VIDEO_CODECS", "AUDIO_CODECS", "QUALITY_LEVELS", "preset_by_id",
           "as_maps"]


@dataclass(frozen=True)
class ExportPreset:
    id: str
    label: str                    # shown as-is; platform names are not translated
    group: str                    # "social" | "custom"
    platform: str = ""            # PLATFORMS id; groups presets behind one icon
    container: str = "mp4"
    video_codec: str = "h264"
    audio_codec: str = "aac"
    width: int = 1920
    height: int = 1080
    fps: str = "source"           # "source" or a number as text
    video_bitrate_kbps: int = 12000
    audio_bitrate_kbps: int = 192
    #: Informative only - it warns, it never blocks.
    recommended_aspect: str = "16:9"
    max_duration_sec: int = 0     # 0 = no limit
    note: str = ""

    def to_map(self) -> dict[str, Any]:
        data = asdict(self)
        data["resolution"] = f"{self.width}x{self.height}"
        return data


#: The platform row shown in the social tab: one icon each, presets grouped
#: behind it. `icon` names an entry in the QML Icons singleton.
PLATFORMS: tuple[dict[str, Any], ...] = (
    {"id": "youtube", "label": "YouTube", "icon": "youtube"},
    {"id": "instagram", "label": "Instagram", "icon": "instagram"},
    {"id": "tiktok", "label": "TikTok", "icon": "tiktok"},
    {"id": "linkedin", "label": "LinkedIn", "icon": "linkedin"},
    {"id": "facebook", "label": "Facebook", "icon": "facebook"},
    {"id": "whatsapp", "label": "WhatsApp", "icon": "whatsapp"},
)

#: Platform requirements change. These live in one place so updating them is a
#: data edit, never a hunt through the UI code.
SOCIAL_PRESETS: tuple[ExportPreset, ...] = (
    ExportPreset("youtube_1080p", "YouTube 1080p", "social", "youtube",
                 width=1920, height=1080, video_bitrate_kbps=12000,
                 audio_bitrate_kbps=384, note="16:9"),
    ExportPreset("youtube_4k", "YouTube 4K", "social", "youtube",
                 width=3840, height=2160, video_codec="h265",
                 video_bitrate_kbps=45000, audio_bitrate_kbps=384, note="16:9"),
    ExportPreset("youtube_shorts", "YouTube Shorts", "social", "youtube",
                 width=1080, height=1920, video_bitrate_kbps=10000,
                 recommended_aspect="9:16", max_duration_sec=60, note="9:16 · max 60s"),
    ExportPreset("instagram_reels", "Instagram Reels", "social", "instagram",
                 width=1080, height=1920, video_bitrate_kbps=9000,
                 recommended_aspect="9:16", max_duration_sec=90, note="9:16 · max 90s"),
    ExportPreset("instagram_feed", "Instagram Feed", "social", "instagram",
                 width=1080, height=1350, video_bitrate_kbps=8000,
                 recommended_aspect="4:5", note="4:5"),
    ExportPreset("instagram_stories", "Instagram Stories", "social", "instagram",
                 width=1080, height=1920, video_bitrate_kbps=9000,
                 recommended_aspect="9:16", max_duration_sec=60, note="9:16 · max 60s"),
    ExportPreset("tiktok", "TikTok", "social", "tiktok",
                 width=1080, height=1920, video_bitrate_kbps=9000,
                 recommended_aspect="9:16", note="9:16"),
    ExportPreset("linkedin", "LinkedIn", "social", "linkedin",
                 width=1920, height=1080, video_bitrate_kbps=8000,
                 max_duration_sec=600, note="16:9 · max 10 min"),
    ExportPreset("facebook", "Facebook", "social", "facebook",
                 width=1920, height=1080, video_bitrate_kbps=8000, note="16:9"),
    ExportPreset("whatsapp", "WhatsApp", "social", "whatsapp",
                 width=1280, height=720, video_bitrate_kbps=2500,
                 audio_bitrate_kbps=128, note="light file"),
)

#: Containers offered in the custom tab, with the codecs each one accepts.
CONTAINERS: tuple[dict[str, Any], ...] = (
    {"id": "mp4", "label": "MP4", "video": ("h264", "h265", "av1"),
     "audio": ("aac", "mp3"), "note": "the compatible default"},
    {"id": "mov", "label": "MOV", "video": ("h264", "h265", "prores"),
     "audio": ("aac", "pcm"), "note": "hand-off to another editor"},
    {"id": "mkv", "label": "MKV", "video": ("h264", "h265", "av1", "vp9"),
     "audio": ("aac", "opus", "flac"), "note": "accepts anything"},
    {"id": "webm", "label": "WebM", "video": ("vp9", "av1"),
     "audio": ("opus",), "note": "web, supports alpha"},
    {"id": "avi", "label": "AVI", "video": ("mpeg4",), "audio": ("mp3",),
     "note": "legacy; only for old workflows"},
)

VIDEO_CODECS: dict[str, str] = {
    "h264": "H.264", "h265": "H.265 / HEVC", "av1": "AV1",
    "vp9": "VP9", "prores": "ProRes", "mpeg4": "MPEG-4",
}

AUDIO_CODECS: dict[str, str] = {
    "aac": "AAC", "mp3": "MP3", "opus": "Opus",
    "flac": "FLAC", "pcm": "PCM (uncompressed)",
}

#: Bitrate multipliers applied to the preset value.
QUALITY_LEVELS: tuple[dict[str, Any], ...] = (
    {"id": "low", "label": "Low", "factor": 0.5},
    {"id": "medium", "label": "Medium", "factor": 1.0},
    {"id": "high", "label": "High", "factor": 1.8},
)


def preset_by_id(preset_id: str) -> ExportPreset | None:
    return next((p for p in SOCIAL_PRESETS if p.id == preset_id), None)


def as_maps() -> list[dict[str, Any]]:
    """Social presets as plain maps for QML."""
    return [p.to_map() for p in SOCIAL_PRESETS]
