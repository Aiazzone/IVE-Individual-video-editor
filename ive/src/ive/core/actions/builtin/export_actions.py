"""Actions for exporting."""

from __future__ import annotations

import logging
from pathlib import Path

from ive.core.actions.registry import Param, action
from ive.export.presets import preset_by_id

log = logging.getLogger(__name__)

#: Characters no filesystem here accepts in a file name, plus separators so a
#: typed name can never escape the chosen folder.
_FORBIDDEN = '<>:"/\\|?*'


def _safe_stem(name: str, container: str) -> str:
    """A typed file name reduced to a usable stem, or "" for "use the default".

    Strips the extension ONLY when it names a container this app writes (the
    chosen one or another known one) - "v1.2.final" is a name with dots, not
    a file type, and eating its tail would surprise. Then removes path
    separators and the characters Windows refuses, and trims the dots and
    spaces a Windows name cannot end with.
    """
    stem = str(name or "").strip()
    if not stem:
        return ""
    known = {container.lower(), "mp4", "mov", "mkv", "webm", "avi"}
    lower = stem.lower()
    for ext in known:
        # Compared on the raw tail, not Path().suffix: ".mp4" alone is a
        # "hidden file" to pathlib and would slip through with no suffix.
        if lower.endswith("." + ext):
            stem = stem[: -(len(ext) + 1)]
            break
    stem = "".join(c for c in stem if c not in _FORBIDDEN and ord(c) >= 32)
    return stem.rstrip(". ").strip()


@action(
    id="export.start",
    title_key="export.start",
    desc_key="Export the media currently in the preview. Either pass "
             "preset_id for a platform preset, or the individual settings.",
    category="export",
    params={
        "options": Param(dict, required=True,
                         doc="preset_id, or container/video_codec/width/height/"
                             "video_bitrate_kbps."),
        "folder": Param(str, required=False, doc="Destination folder."),
        "filename": Param(str, required=False,
                          doc="Output file name, without the extension. "
                              "Empty means the automatic name."),
    },
    shortcut="Ctrl+E",
)
def start_export(ctx, options: dict, folder: str = "", filename: str = ""):
    playback = ctx.require("playback")
    export = ctx.require("export")
    if not playback.hasMedia:
        raise RuntimeError("Nothing to export: no media is loaded")

    settings = dict(options or {})
    preset_id = settings.pop("preset_id", "")
    if preset_id:
        preset = preset_by_id(preset_id)
        if preset is None:
            raise RuntimeError(f"Unknown preset {preset_id!r}")
        settings = {
            "container": preset.container,
            "video_codec": preset.video_codec,
            "audio_codec": preset.audio_codec,
            "width": preset.width,
            "height": preset.height,
            "video_bitrate_kbps": preset.video_bitrate_kbps,
        }
        stem_suffix = preset.id
    else:
        stem_suffix = "custom"

    source = export.current_source(playback)
    base = Path(folder) if folder else Path(source).parent
    container = str(settings.get("container") or "mp4")

    stem = _safe_stem(filename, container)
    if not stem:
        stem = f"{Path(source).stem}_{stem_suffix}"
    target = base / f"{stem}.{container}"

    # Never silently overwrite: an export that eats the previous one is a
    # data-loss bug, not a convenience.
    counter = 1
    while target.exists():
        target = base / f"{stem}_{counter}.{container}"
        counter += 1

    if not export.start(source, str(target), settings):
        raise RuntimeError("Could not start the export")


@action(
    id="export.cancel",
    title_key="export.cancel",
    desc_key="Stop the running export. The partial file is removed.",
    category="export",
)
def cancel_export(ctx):
    ctx.require("export").cancel()
