"""Export presets: the catalogue and the fixed tables around it.

Presets declare a **logical** codec (``h264``), never a specific encoder
(``h264_nvenc``): the encoder is chosen at runtime from what the machine
has. That is what lets a preset shared between two people work on both.

Presets are JSON documents, not code (docs/EXPORT_PRESETS.md §2). The
factory set ships in ``ive/config/defaults/export_presets/``; the user's
own live in ``user_data/export_presets/``; installed content packs bring
theirs in an ``export_presets/`` folder. Shape of one preset::

    {
      "schema_version": 1,
      "id": "youtube_1080p",
      "name": {"en": "YouTube 1080p"},
      "platform": "youtube",            # a PLATFORMS id; else "other"
      "container": "mp4",
      "video": {"codec": "h264", "width": 1920, "height": 1080,
                "fps": "source", "bitrate_kbps": 12000},
      "audio": {"codec": "aac", "bitrate_kbps": 384},
      "constraints": {"recommended_aspect": "16:9",
                      "max_duration_sec": 0},
      "note": "16:9"
    }

A preset naming a container or codec this build does not know is
skipped with a warning (an export that cannot start is worse than a
missing card); an unknown platform lands under "Other" - the pack
still works, the icon is just generic.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from ive.utils.paths import get_data_path, get_defaults_path

log = logging.getLogger(__name__)

__all__ = ["ExportPreset", "PLATFORMS", "OTHER_PLATFORM", "CONTAINERS",
           "VIDEO_CODECS", "AUDIO_CODECS", "QUALITY_LEVELS", "list_presets",
           "preset_by_id", "reload", "as_maps", "platforms_in_use"]


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
    #: "factory" | "user" | "pack" - the panel tells them apart.
    source: str = "factory"
    names: tuple[tuple[str, str], ...] = ()

    def to_map(self) -> dict[str, Any]:
        data = asdict(self)
        data["resolution"] = f"{self.width}x{self.height}"
        data["names"] = dict(self.names)
        return data

    def to_recipe(self) -> dict[str, Any]:
        """The JSON document form - what a pack carries."""
        return {
            "schema_version": 1, "id": self.id,
            "name": dict(self.names) or {"en": self.label},
            "platform": self.platform, "container": self.container,
            "video": {"codec": self.video_codec, "width": self.width,
                      "height": self.height, "fps": self.fps,
                      "bitrate_kbps": self.video_bitrate_kbps},
            "audio": {"codec": self.audio_codec,
                      "bitrate_kbps": self.audio_bitrate_kbps},
            "constraints": {"recommended_aspect": self.recommended_aspect,
                            "max_duration_sec": self.max_duration_sec},
            "note": self.note,
        }


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

#: Where presets with no known platform gather (user and pack presets
#: for a service we have no icon for). Shown only when it has members.
OTHER_PLATFORM: dict[str, Any] = {"id": "other", "label": "Other",
                                  "icon": "pack"}

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


# ── the catalogue ─────────────────────────────────────────────────────

_cache: list[ExportPreset] | None = None


def _coerce(entry: Any, origin: str, source: str) -> ExportPreset | None:
    if not isinstance(entry, dict):
        return None
    preset_id = str(entry.get("id") or "").strip()
    if not preset_id:
        log.warning("Skipping an export preset without id in %s", origin)
        return None
    video = entry.get("video") if isinstance(entry.get("video"), dict) else {}
    audio = entry.get("audio") if isinstance(entry.get("audio"), dict) else {}
    limits = (entry.get("constraints")
              if isinstance(entry.get("constraints"), dict) else {})
    container = str(entry.get("container") or "mp4").lower()
    video_codec = str(video.get("codec") or "h264").lower()
    audio_codec = str(audio.get("codec") or "aac").lower()
    known = next((c for c in CONTAINERS if c["id"] == container), None)
    if known is None or video_codec not in VIDEO_CODECS \
            or audio_codec not in AUDIO_CODECS:
        log.warning("Export preset %r (%s) names an unknown container or "
                    "codec (%s/%s/%s); skipped", preset_id, origin,
                    container, video_codec, audio_codec)
        return None
    names = entry.get("name")
    if not isinstance(names, dict):
        names = {"en": str(names) if names else preset_id}
    names = {str(k): str(v) for k, v in names.items()}
    platform = str(entry.get("platform") or "").strip().lower()
    if platform not in {p["id"] for p in PLATFORMS}:
        platform = OTHER_PLATFORM["id"]
    try:
        width = max(16, int(video.get("width") or 1920))
        height = max(16, int(video.get("height") or 1080))
        vbr = max(100, int(video.get("bitrate_kbps") or 12000))
        abr = max(32, int(audio.get("bitrate_kbps") or 192))
        max_duration = max(0, int(limits.get("max_duration_sec") or 0))
    except (TypeError, ValueError):
        log.warning("Export preset %r (%s) has non-numeric fields; skipped",
                    preset_id, origin)
        return None
    return ExportPreset(
        id=preset_id,
        label=names.get("en") or next(iter(names.values()), preset_id),
        group="social", platform=platform, container=container,
        video_codec=video_codec, audio_codec=audio_codec,
        width=width - width % 2, height=height - height % 2,
        fps=str(video.get("fps") or "source"),
        video_bitrate_kbps=vbr, audio_bitrate_kbps=abr,
        recommended_aspect=str(limits.get("recommended_aspect") or ""),
        max_duration_sec=max_duration, note=str(entry.get("note") or ""),
        source=source, names=tuple(sorted(names.items())),
    )


def _scan(folder: Path, source: str) -> list[ExportPreset]:
    found: list[ExportPreset] = []
    if not folder.is_dir():
        return found
    for path in sorted(folder.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Unreadable export preset file %s: %s", path.name, exc)
            continue
        entries = raw if isinstance(raw, list) else [raw]
        for entry in entries:
            preset = _coerce(entry, path.name, source)
            if preset is not None:
                found.append(preset)
    return found


def _load() -> list[ExportPreset]:
    from ive.packs.pack import pack_content_dirs

    presets: list[ExportPreset] = []
    seen: set[str] = set()
    scanned = (_scan(get_defaults_path("export_presets"), "factory")
               + _scan(get_data_path("export_presets"), "user"))
    for folder in pack_content_dirs("export_presets"):
        scanned += _scan(folder, "pack")
    for preset in scanned:
        if preset.id in seen:
            log.warning("Duplicate export preset id %r ignored", preset.id)
            continue
        seen.add(preset.id)
        presets.append(preset)
    log.info("Export presets loaded: %d (%d factory)", len(presets),
             sum(1 for p in presets if p.source == "factory"))
    return presets


def list_presets() -> list[ExportPreset]:
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache


def reload() -> None:
    """Forget the cache; the next query rescans the folders."""
    global _cache
    _cache = None


def preset_by_id(preset_id: str) -> ExportPreset | None:
    return next((p for p in list_presets() if p.id == preset_id), None)


def as_maps() -> list[dict[str, Any]]:
    """The presets as plain maps for QML."""
    return [p.to_map() for p in list_presets()]


def platforms_in_use() -> list[dict[str, Any]]:
    """The platform row: the fixed icons, plus "Other" only when some
    preset needs it."""
    out = [dict(p) for p in PLATFORMS]
    if any(p.platform == OTHER_PLATFORM["id"] for p in list_presets()):
        out.append(dict(OTHER_PLATFORM))
    return out


def __getattr__(name: str):
    # The pre-JSON name of the catalogue, kept for older callers.
    if name == "SOCIAL_PRESETS":
        return tuple(list_presets())
    raise AttributeError(name)
