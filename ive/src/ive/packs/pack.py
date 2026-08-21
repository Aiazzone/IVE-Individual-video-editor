"""Building, previewing, installing and removing ``.ivepack`` files.

A pack is a ZIP renamed ``.ivepack`` (docs/CONTENT_PACKS.md §2): one
file travels by mail or chat and does not fray in the copying. Inside,
the same folder shapes the catalogues already scan:

    pack.json                       the manifest
    color_effects/effects.json      colour recipes (a list)
    transitions/transitions.json    transition recipes
    transitions/luma/<file>.png     the luma maps the recipes reference
    stickers/pack_stickers.json     sticker manifest
    stickers/files/<graphics>       SVG / PNG / Lottie JSON
    motion/motion.json              motion preset recipes (keyframes)
    export_presets/presets.json     export presets (logical codecs)
    audio_effects/effects.json      audio effect recipes (EQ, dynamics)
    music/tracks.json               music tracks (licence facts included)
    music/files/<audio>             the tracks themselves

Install = unpack into ``user_data/packs/<pack_id>/`` (each catalogue
also scans those folders); uninstall = delete that folder. Nothing
else, no registry, no residue. Duplicate ids are the catalogues'
business: they skip them with a warning, never overwrite - so a pack
can never silently replace what the user already has.

Security: members are extracted ONLY through a sanitiser that refuses
absolute paths and ``..`` traversal (zip-slip), and a pack is data end
to end - nothing in it is ever executed.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from ive.utils.paths import get_data_path

log = logging.getLogger(__name__)

__all__ = ["build_pack", "preview_pack", "install_pack", "installed_packs",
           "remove_pack"]

SCHEMA_VERSION = 1
PACK_SUFFIX = ".ivepack"


def _packs_root() -> Path:
    return get_data_path("packs")


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return slug or "pack"


def _localized(value: Any) -> dict[str, str]:
    """Descriptions and names are per-language dicts in the manifest."""
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    return {"en": str(value)} if value else {}


# ── building ──────────────────────────────────────────────────────────

def build_pack(destination: str | Path, *, name: str, author: str = "",
               description: str = "", version: str = "1.0",
               color_ids: list[str] | None = None,
               transition_ids: list[str] | None = None,
               sticker_ids: list[str] | None = None,
               motion_ids: list[str] | None = None,
               export_preset_ids: list[str] | None = None,
               audio_effect_ids: list[str] | None = None,
               track_ids: list[str] | None = None) -> dict[str, Any]:
    """Write a ``.ivepack`` with the selected catalogue entries.

    Recipes are re-serialised from the LIVE catalogues (so a pack always
    carries what the user actually sees), and the files they reference -
    luma maps, sticker graphics - are copied in next to them with the
    references rewritten to relative paths. Returns a small report
    ``{path, counts}``; raises ValueError on an empty selection or an
    unknown id (a pack must never ship half of what was asked).
    """
    from ive.audio.library import effect_by_id as audio_by_id
    from ive.color.library import effect_by_id
    from ive.export.presets import preset_by_id as export_by_id
    from ive.motion.library import preset_by_id as motion_by_id
    from ive.music.library import track_by_id
    from ive.stickers.library import sticker_by_id
    from ive.transitions.library import transition_by_id

    name = str(name).strip() or "Pack"
    color_ids = [str(v) for v in (color_ids or [])]
    transition_ids = [str(v) for v in (transition_ids or [])]
    sticker_ids = [str(v) for v in (sticker_ids or [])]
    motion_ids = [str(v) for v in (motion_ids or [])]
    export_preset_ids = [str(v) for v in (export_preset_ids or [])]
    audio_effect_ids = [str(v) for v in (audio_effect_ids or [])]
    track_ids = [str(v) for v in (track_ids or [])]
    if not (color_ids or transition_ids or sticker_ids or motion_ids
            or export_preset_ids or audio_effect_ids or track_ids):
        raise ValueError("empty selection")

    effects = []
    for effect_id in color_ids:
        effect = effect_by_id(effect_id)
        if effect is None:
            raise ValueError(f"unknown colour effect {effect_id!r}")
        effects.append({
            "schema_version": 1, "id": effect["id"],
            "name": dict(effect["names"]), "section": effect["section"],
            "ops": [dict(op) for op in effect["ops"]],
        })

    transitions = []
    luma_files: dict[str, Path] = {}
    for transition_id in transition_ids:
        transition = transition_by_id(transition_id)
        if transition is None:
            raise ValueError(f"unknown transition {transition_id!r}")
        payload = dict(transition["op"])
        source_file = payload.get("file")
        if source_file:
            source = Path(str(source_file))
            arcname = f"{transition['id']}_{source.name}"
            luma_files[arcname] = source
            payload["file"] = f"luma/{arcname}"
        transitions.append({
            "schema_version": 1, "id": transition["id"],
            "name": dict(transition["names"]),
            "section": transition["section"],
            "duration": transition["duration"],
            "easing": transition["easing"], "op": payload,
        })

    stickers = []
    sticker_files: dict[str, Path] = {}
    for sticker_id in sticker_ids:
        sticker = sticker_by_id(sticker_id)
        if sticker is None:
            raise ValueError(f"unknown sticker {sticker_id!r}")
        source = Path(sticker["path"])
        arcname = f"{sticker['id']}{source.suffix.lower()}"
        sticker_files[arcname] = source
        stickers.append({
            "schema_version": 1, "id": sticker["id"],
            "name": dict(sticker["names"]), "section": sticker["section"],
            "kind": sticker["kind"], "file": f"files/{arcname}",
        })

    motions = []
    for motion_id in motion_ids:
        preset = motion_by_id(motion_id)
        if preset is None:
            raise ValueError(f"unknown motion preset {motion_id!r}")
        motions.append({
            "schema_version": 1, "id": preset["id"],
            "name": dict(preset["names"]), "kind": preset["kind"],
            "duration": preset["duration"],
            "tracks": [dict(t) for t in preset["tracks"]],
        })

    exports = []
    for preset_id in export_preset_ids:
        preset = export_by_id(preset_id)
        if preset is None:
            raise ValueError(f"unknown export preset {preset_id!r}")
        exports.append(preset.to_recipe())

    audio_effects = []
    for effect_id in audio_effect_ids:
        effect = audio_by_id(effect_id)
        if effect is None:
            raise ValueError(f"unknown audio effect {effect_id!r}")
        audio_effects.append({
            "schema_version": 1, "id": effect["id"],
            "name": dict(effect["names"]), "section": effect["section"],
            "ops": [dict(op) for op in effect["ops"]],
        })

    tracks = []
    track_files: dict[str, Path] = {}
    for track_id in track_ids:
        track = track_by_id(track_id)
        if track is None:
            raise ValueError(f"unknown track {track_id!r}")
        source = Path(track["path"])
        arcname = f"{track['id']}{source.suffix.lower()}"
        track_files[arcname] = source
        tracks.append({
            "schema_version": 1, "id": track["id"],
            "title": dict(track["titles"]), "artist": track["artist"],
            "category": track["category"], "tags": list(track["tags"]),
            "bpm": track["bpm"], "vocals": track["vocals"],
            "duration": track["duration"], "license": track["license"],
            "license_url": track["license_url"],
            "source_url": track["source_url"],
            "attribution_required": track["attribution_required"],
            "attribution": track["attribution"],
            "file": f"files/{arcname}",
        })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "id": _slug(f"{author}-{name}" if author else name),
        "name": name,
        "version": str(version) or "1.0",
        "author": str(author),
        "description": _localized(description),
        "contents": {
            "color_effects": [e["id"] for e in effects],
            "transitions": [t["id"] for t in transitions],
            "stickers": [s["id"] for s in stickers],
            "motion": [m["id"] for m in motions],
            "export_presets": [e["id"] for e in exports],
            "audio_effects": [a["id"] for a in audio_effects],
            "music": [t["id"] for t in tracks],
        },
    }

    destination = Path(destination)
    if destination.suffix.lower() != PACK_SUFFIX:
        destination = destination.with_suffix(PACK_SUFFIX)
    destination.parent.mkdir(parents=True, exist_ok=True)

    def dumps(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2)

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("pack.json", dumps(manifest))
        if effects:
            archive.writestr("color_effects/effects.json", dumps(effects))
        if transitions:
            archive.writestr("transitions/transitions.json",
                             dumps(transitions))
            for arcname, source in luma_files.items():
                archive.write(source, f"transitions/luma/{arcname}")
        if stickers:
            archive.writestr("stickers/pack_stickers.json", dumps(stickers))
            for arcname, source in sticker_files.items():
                archive.write(source, f"stickers/files/{arcname}")
        if motions:
            archive.writestr("motion/motion.json", dumps(motions))
        if exports:
            archive.writestr("export_presets/presets.json", dumps(exports))
        if audio_effects:
            archive.writestr("audio_effects/effects.json",
                             dumps(audio_effects))
        if tracks:
            archive.writestr("music/tracks.json", dumps(tracks))
            for arcname, source in track_files.items():
                archive.write(source, f"music/files/{arcname}")

    counts = {"color_effects": len(effects), "transitions": len(transitions),
              "stickers": len(stickers), "motion": len(motions),
              "export_presets": len(exports),
              "audio_effects": len(audio_effects), "music": len(tracks)}
    log.info("Pack written: %s (%s)", destination, counts)
    return {"path": str(destination), "counts": counts,
            "id": manifest["id"]}


# ── reading ───────────────────────────────────────────────────────────

def _find_manifest(archive: zipfile.ZipFile) -> tuple[str, dict] | None:
    """``(prefix, manifest)``: pack.json at the root, or one folder deep
    (a pack zipped as a folder is just as valid as one zipped flat)."""
    names = archive.namelist()
    for candidate in sorted(names, key=lambda n: n.count("/")):
        parts = candidate.split("/")
        if parts[-1] == "pack.json" and len(parts) <= 2:
            try:
                manifest = json.loads(
                    archive.read(candidate).decode("utf-8-sig"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None
            if isinstance(manifest, dict):
                prefix = candidate[:-len("pack.json")]
                return prefix, manifest
    return None


def preview_pack(path: str | Path) -> dict[str, Any]:
    """What a pack file holds, WITHOUT installing it - the confirmation
    card shows this. ``{ok, name, author, version, description, counts,
    duplicates, already_installed, error}``."""
    from ive.audio.library import effect_by_id as audio_by_id
    from ive.color.library import effect_by_id
    from ive.export.presets import preset_by_id as export_by_id
    from ive.motion.library import preset_by_id as motion_by_id
    from ive.music.library import track_by_id
    from ive.stickers.library import sticker_by_id
    from ive.transitions.library import transition_by_id

    path = Path(path)
    out: dict[str, Any] = {"ok": False, "error": ""}
    if not path.is_file():
        out["error"] = "not_found"
        return out
    try:
        with zipfile.ZipFile(path) as archive:
            found = _find_manifest(archive)
    except zipfile.BadZipFile:
        out["error"] = "not_a_pack"
        return out
    if found is None:
        out["error"] = "no_manifest"
        return out
    _prefix, manifest = found

    contents = manifest.get("contents") or {}
    ids = {
        "color_effects": [str(v) for v in
                          (contents.get("color_effects") or [])],
        "transitions": [str(v) for v in (contents.get("transitions") or [])],
        "stickers": [str(v) for v in (contents.get("stickers") or [])],
        "motion": [str(v) for v in (contents.get("motion") or [])],
        "export_presets": [str(v) for v in
                           (contents.get("export_presets") or [])],
        "audio_effects": [str(v) for v in
                          (contents.get("audio_effects") or [])],
        "music": [str(v) for v in (contents.get("music") or [])],
    }
    duplicates = (
        sum(1 for v in ids["color_effects"] if effect_by_id(v) is not None)
        + sum(1 for v in ids["transitions"]
              if transition_by_id(v) is not None)
        + sum(1 for v in ids["stickers"] if sticker_by_id(v) is not None)
        + sum(1 for v in ids["motion"] if motion_by_id(v) is not None)
        + sum(1 for v in ids["export_presets"]
              if export_by_id(v) is not None)
        + sum(1 for v in ids["audio_effects"] if audio_by_id(v) is not None)
        + sum(1 for v in ids["music"] if track_by_id(v) is not None)
    )
    pack_id = _slug(str(manifest.get("id") or manifest.get("name") or
                        path.stem))
    out.update({
        "ok": True,
        "id": pack_id,
        "name": str(manifest.get("name") or path.stem),
        "author": str(manifest.get("author") or ""),
        "version": str(manifest.get("version") or ""),
        "description": _localized(manifest.get("description")),
        "counts": {k: len(v) for k, v in ids.items()},
        "duplicates": duplicates,
        "already_installed": (_packs_root() / pack_id).is_dir(),
        "path": str(path),
    })
    return out


# ── installing ────────────────────────────────────────────────────────

def install_pack(path: str | Path) -> dict[str, Any]:
    """Unpack a ``.ivepack`` into ``user_data/packs/<pack_id>/``.

    Refuses a pack whose id is already installed (remove it first - two
    copies of the same pack would only produce duplicate-id warnings).
    Member paths are sanitised: anything absolute or climbing out with
    ``..`` fails the whole install.
    """
    preview = preview_pack(path)
    if not preview.get("ok"):
        return preview
    if preview["already_installed"]:
        preview.update(ok=False, error="already_installed")
        return preview

    target = _packs_root() / preview["id"]
    try:
        with zipfile.ZipFile(Path(path)) as archive:
            found = _find_manifest(archive)
            prefix = found[0] if found else ""
            for info in archive.infolist():
                if info.is_dir():
                    continue
                member = info.filename
                if prefix and not member.startswith(prefix):
                    continue
                relative = member[len(prefix):]
                parts = Path(relative).parts
                if (not parts or Path(relative).is_absolute()
                        or any(p == ".." for p in parts)):
                    raise ValueError(f"unsafe member path {member!r}")
                destination = target / Path(*parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, \
                        open(destination, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        log.exception("Pack install failed: %s", path)
        shutil.rmtree(target, ignore_errors=True)
        preview.update(ok=False, error=str(exc))
        return preview

    log.info("Pack installed: %s -> %s", preview["name"], target)
    return preview


def installed_packs() -> list[dict[str, Any]]:
    """The packs under ``user_data/packs``, manifest facts included."""
    root = _packs_root()
    if not root.is_dir():
        return []
    out = []
    for folder in sorted(root.iterdir()):
        manifest_path = folder / "pack.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            log.warning("Unreadable pack manifest: %s", manifest_path)
            continue
        contents = manifest.get("contents") or {}
        out.append({
            "id": folder.name,
            "name": str(manifest.get("name") or folder.name),
            "author": str(manifest.get("author") or ""),
            "version": str(manifest.get("version") or ""),
            "description": _localized(manifest.get("description")),
            "counts": {
                "color_effects": len(contents.get("color_effects") or []),
                "transitions": len(contents.get("transitions") or []),
                "stickers": len(contents.get("stickers") or []),
                "motion": len(contents.get("motion") or []),
                "export_presets": len(contents.get("export_presets") or []),
                "audio_effects": len(contents.get("audio_effects") or []),
                "music": len(contents.get("music") or []),
            },
            "folder": str(folder),
        })
    return out


def remove_pack(pack_id: str) -> bool:
    """Delete an installed pack's folder. That IS the uninstall."""
    pack_id = _slug(pack_id)
    target = _packs_root() / pack_id
    if not (target.is_dir() and (target / "pack.json").is_file()):
        log.warning("No installed pack %r to remove", pack_id)
        return False
    shutil.rmtree(target, ignore_errors=True)
    log.info("Pack removed: %s", pack_id)
    return True


def pack_content_dirs(kind: str) -> list[Path]:
    """The installed packs' folders one catalogue should also scan.

    ``kind`` is the subfolder name: "color_effects", "transitions",
    "stickers", "motion" or "export_presets". Startup cost stays flat: this only lists directories.
    """
    root = _packs_root()
    if not root.is_dir():
        return []
    return [folder / kind for folder in sorted(root.iterdir())
            if (folder / "pack.json").is_file()
            and (folder / kind).is_dir()]
