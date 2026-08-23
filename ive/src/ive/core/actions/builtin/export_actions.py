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
        settings = preset.to_options()
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
    # data-loss bug, not a convenience. A destination promised to a job
    # still in the queue counts as taken even though the file is not on
    # disk yet - two queued exports of the same preset must not collide.
    taken = export.queued_paths() if hasattr(export, "queued_paths") else set()
    counter = 1
    while target.exists() or str(target) in taken:
        target = base / f"{stem}_{counter}.{container}"
        counter += 1

    if not export.start(source, str(target), settings):
        raise RuntimeError("Could not start the export")


@action(
    id="export.cancel",
    title_key="export.cancel",
    desc_key="Stop the running export. The partial file is removed; "
             "any queued exports still run.",
    category="export",
)
def cancel_export(ctx):
    ctx.require("export").cancel()


@action(
    id="export.cancel_all",
    title_key="export.cancel",
    desc_key="Stop the running export AND drop every waiting one.",
    category="export",
)
def cancel_all_exports(ctx):
    ctx.require("export").cancel_all()


@action(
    id="export.save_preset",
    title_key="export.preset.save",
    desc_key="Save export settings as a named user preset "
             "(a single reusable .json).",
    category="export",
    params={
        "name": Param(str, required=True, doc="Display name of the preset."),
        "options": Param(dict, required=True,
                         doc="container/video_codec/audio_codec/width/height/"
                             "video_bitrate_kbps."),
    },
)
def save_export_preset(ctx, name: str, options: dict):
    if not ctx.require("export").save_preset(name, dict(options or {})):
        raise RuntimeError("The preset could not be saved")


@action(
    id="export.delete_preset",
    title_key="export.preset.delete",
    desc_key="Delete one of the user's own export presets.",
    category="export",
    params={"preset_id": Param(str, required=True)},
)
def delete_export_preset(ctx, preset_id: str):
    if not ctx.require("export").delete_preset(preset_id):
        raise RuntimeError(f"Preset {preset_id!r} is not deletable")


@action(
    id="export.share_preset",
    title_key="export.preset.share",
    desc_key="Write one export preset as a single .json file in a folder, "
             "ready to hand to someone else.",
    category="export",
    params={"preset_id": Param(str, required=True),
            "folder": Param(str, required=True)},
)
def share_export_preset(ctx, preset_id: str, folder: str):
    if not ctx.require("export").share_preset(preset_id, folder):
        raise RuntimeError(f"Unknown preset {preset_id!r}")


@action(
    id="export.import_preset",
    title_key="export.preset.import",
    desc_key="Import export presets from a .json file into the user's "
             "catalogue. Existing ids are skipped, never overwritten.",
    category="export",
    params={"path": Param(str, required=True)},
)
def import_export_preset(ctx, path: str):
    report = ctx.require("export").import_preset(path)
    if not report.get("ok"):
        raise RuntimeError(report.get("error") or "nothing_imported")
