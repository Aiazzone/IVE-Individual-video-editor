"""Creating, loading and saving projects, and holding the media pool.

The QML side reads ``Project.media`` (a list of plain maps) and the usual
scalar properties. Everything that mutates goes through an action, so the same
operations work from a script or the assistant.

Importing media probes each file: that reads metadata only, no decoding, so a
folder of a hundred clips lands in about a second.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ive.core.commands.project_commands import ProjectEdit
from ive.core.model.project import PROJECT_SUFFIX, MediaItem, Project
from ive.media.probe import MediaProbeError, probe
from ive.utils.paths import get_data_path, local_path_from_url

log = logging.getLogger(__name__)

__all__ = ["ProjectService"]

#: Extensions offered in the import dialog and accepted by drag and drop.
MEDIA_SUFFIXES = {
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mts", ".m2ts",
    ".mpg", ".mpeg", ".wmv", ".gif",
    ".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".opus",
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff",
}


class ProjectService(QObject):
    """Owns the open project."""

    projectChanged = Signal()       # identity: opened, closed, renamed
    mediaChanged = Signal()         # the pool gained or lost items
    dirtyChanged = Signal()
    timelineChanged = Signal()
    error = Signal(str)
    #: (imported, skipped, failed) after an import batch.
    imported = Signal(int, int, int)

    def __init__(self, settings=None, history=None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        #: The UndoStack. Every mutation of the open project goes through it
        #: (rule 4.6): the slots below build a ProjectEdit and push it, so
        #: Ctrl+Z can replay the timeline backwards. None (tests, scripts)
        #: means mutations apply directly and nothing is recorded.
        self._history = history
        self._project: Project | None = None
        self._dirty = False

    # ── properties for QML ────────────────────────────────────────────

    @Property(bool, notify=projectChanged)
    def isOpen(self) -> bool:
        return self._project is not None

    @Property(str, notify=projectChanged)
    def name(self) -> str:
        return self._project.name if self._project else ""

    @Property(str, notify=projectChanged)
    def folder(self) -> str:
        return self._project.folder if self._project else ""

    @Property(str, notify=projectChanged)
    def defaultFolder(self) -> str:
        """Where new projects are proposed: ``user_data/projects``."""
        return str(get_data_path("projects"))

    @Property("QVariantList", notify=projectChanged)
    def recentProjects(self) -> list[dict[str, Any]]:
        """Projects found in the default folder, newest first.

        Scanning the folder rather than keeping a separate recents list means
        the entries cannot go stale: what is listed is what exists.
        """
        root = Path(self.defaultFolder)
        if not root.is_dir():
            return []
        found = []
        try:
            for path in root.rglob(f"*{PROJECT_SUFFIX}"):
                if path.is_file():
                    found.append(path)
        except OSError:
            log.warning("Could not scan %s for projects", root)
            return []
        def mtime(path: Path) -> float:
            # The file can vanish between the scan and this sort (synced
            # folders do that); a missing one just sorts last.
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0

        found.sort(key=mtime, reverse=True)
        return [
            {"name": p.stem, "folder": str(p.parent), "path": str(p)}
            for p in found[:8]
        ]

    @Property(bool, notify=dirtyChanged)
    def dirty(self) -> bool:
        return self._dirty

    @Property(int, notify=mediaChanged)
    def mediaCount(self) -> int:
        return len(self._project.media) if self._project else 0

    @Property("QVariantList", notify=mediaChanged)
    def media(self) -> list[dict[str, Any]]:
        """The pool, as plain maps QML can bind to directly."""
        if self._project is None:
            return []
        base = self._project.base
        out = []
        for item in self._project.media:
            out.append({
                "id": item.id,
                "name": item.name or Path(item.path).name,
                "path": str(item.resolve(base)),
                "duration": item.duration,
                "width": item.width,
                "height": item.height,
                "fps": item.fps,
                "hasAudio": item.has_audio,
                "missing": item.missing,
                "durationLabel": _duration_label(item.duration),
                "sizeLabel": f"{item.width}x{item.height}" if item.width else "",
            })
        return out

    @Property("QVariantList", notify=timelineChanged)
    def timelineClips(self) -> list[dict[str, Any]]:
        """Clips on the timeline, resolved against the pool, ready for QML."""
        if self._project is None:
            return []
        from ive.color.library import effect_by_id
        from ive.stickers.library import sticker_by_id

        base = self._project.base
        out = []
        # Every track: 0 is A/V, 1 is the Color lane, 2 is the Sticker
        # lane, 3 is the Text lane.
        for clip in sorted(self._project.timeline,
                           key=lambda c: (c.track, c.start)):
            item = self._project.find_media(clip.media_id)
            if clip.effect_id:
                effect = effect_by_id(clip.effect_id)
                names = effect["names"] if effect else {}
                name = names.get("en") or clip.effect_id
            elif clip.sticker_id:
                sticker = sticker_by_id(clip.sticker_id)
                names = sticker["names"] if sticker else {}
                name = names.get("en") or clip.sticker_id
            elif clip.text:
                # The words themselves label the clip; one line, kept short.
                name = clip.text.split("\n")[0][:24]
            else:
                name = item.name if item else clip.media_id
            out.append({
                "id": clip.id,
                "mediaId": clip.media_id,
                "effectId": clip.effect_id,
                "stickerId": clip.sticker_id,
                "text": clip.text,
                "motionId": clip.motion_id,
                "font": clip.font,
                "color": clip.color,
                "outline": clip.outline,
                "bold": clip.bold,
                "italic": clip.italic,
                "track": clip.track,
                "name": name,
                "path": str(item.resolve(base)) if item else "",
                "start": clip.start,
                "duration": clip.duration,
                "end": clip.end,
                "sourceIn": clip.source_in,
                "transitionId": clip.transition_id,
                "transitionDuration": clip.transition_duration,
                "transitionInId": clip.transition_in_id,
                "transitionInDuration": clip.transition_in_duration,
                "mediaDuration": (item.duration if item else 0.0),
                "volume": clip.volume,
                "audioEnabled": clip.audio_enabled,
                "muted": clip.muted,
                "audioEffectId": clip.audio_effect_id,
                "fadeIn": clip.fade_in,
                "fadeOut": clip.fade_out,
                "duck": clip.duck,
                "duckDb": clip.duck_db,
                "x": clip.x, "y": clip.y,
                "scale": clip.scale, "rotation": clip.rotation,
                "hasVideo": bool(item.width > 0) if item else False,
                "hasAudio": bool(item.has_audio) if item else False,
                "missing": bool(item.missing) if item
                           else not (clip.effect_id or clip.sticker_id
                                     or clip.text),
            })
        return out

    @Property(float, notify=timelineChanged)
    def timelineDuration(self) -> float:
        return self._project.timeline_duration if self._project else 0.0

    @Property(int, notify=timelineChanged)
    def timelineCount(self) -> int:
        return len(self._project.timeline) if self._project else 0

    # Every mutating slot below has the same shape: validate what needs the
    # service (lookups, logging), then hand the actual mutation to _edit(),
    # which records it on the undo stack, emits the signals and autosaves.
    # The label is the SAME translation key the UI uses for the operation,
    # so the undo tooltip can say what Ctrl+Z is about to revert.

    @Slot(str, result=bool)
    @Slot(str, float, result=bool)
    def place_media(self, media_id: str, at: float = -1.0) -> bool:
        """Put a pool item on the timeline: at the end, or at a point in time."""
        if self._project is None:
            return False
        item = self._project.find_media(media_id)
        if item is None:
            log.warning("Cannot place unknown media %s", media_id)
            return False
        duration = item.duration or 5.0

        def mutate():
            clip = self._project.add_clip(media_id, duration,
                                          at=None if at < 0 else float(at))
            log.info("Placed %s on the timeline at %.2fs (%.2fs long)",
                     item.name, clip.start, clip.duration)
            return clip

        return self._edit("timeline.place_media", mutate)

    @Slot(str, float, result=bool)
    def move_clip(self, clip_id: str, to: float) -> bool:
        return self._edit("timeline.move_clip",
                          lambda: self._project.move_clip(clip_id, float(to)))

    @Slot(str, result=bool)
    def remove_clip(self, clip_id: str) -> bool:
        return self._edit("timeline.remove_clip",
                          lambda: self._project.remove_clip(clip_id))

    @Slot(str, float, result=bool)
    def split_clip(self, clip_id: str, at: float) -> bool:
        """Cut a clip in two at a point on the timeline (seconds)."""
        return self._edit("timeline.split",
                          lambda: self._project.split_clip(clip_id, float(at)))

    @Slot(str, float, result=bool)
    def set_clip_volume(self, clip_id: str, volume: float) -> bool:
        """Audio gain for one clip: 0 = silent, 1 = as recorded, max 2."""
        return self._edit("timeline.volume",
                          lambda: self._project.set_clip_volume(clip_id, volume))

    @Slot(str, float, float, result=bool)
    def place_effect(self, effect_id: str, at: float, duration: float) -> bool:
        """Put a colour effect on the Color lane over [at, at+duration)."""
        if self._project is None:
            return False
        from ive.color.library import effect_by_id

        if effect_by_id(effect_id) is None:
            log.warning("Unknown colour effect %r", effect_id)
            return False

        def mutate():
            clip = self._project.add_effect(effect_id, at, duration)
            log.info("Colour effect %s placed at %.2fs for %.2fs",
                     effect_id, clip.start, clip.duration)
            return clip

        return self._edit("timeline.place_effect", mutate)

    @Slot(str, float, float, result=bool)
    def place_sticker(self, sticker_id: str, at: float,
                      duration: float) -> bool:
        """Put a sticker on the Sticker lane over [at, at+duration)."""
        if self._project is None:
            return False
        from ive.stickers.library import sticker_by_id

        if sticker_by_id(sticker_id) is None:
            log.warning("Unknown sticker %r", sticker_id)
            return False

        def mutate():
            clip = self._project.add_sticker(sticker_id, at, duration)
            log.info("Sticker %s placed at %.2fs for %.2fs",
                     sticker_id, clip.start, clip.duration)
            return clip

        return self._edit("sticker.place", mutate)

    @Slot(str, float, float, float, result=bool)
    @Slot(str, float, float, float, float, result=bool)
    def place_text(self, text: str, at: float, duration: float,
                   y: float = 0.5) -> bool:
        """Put a title on the Text lane over [at, at+duration)."""
        if self._project is None:
            return False

        def mutate():
            clip = self._project.add_text(text, at, duration, y=y)
            if clip is not None:
                log.info("Title %r placed at %.2fs for %.2fs",
                         clip.text[:24], clip.start, clip.duration)
            return clip

        return self._edit("text.place", mutate)

    @Slot(str, str, str, str, str, bool, bool, result=bool)
    def set_clip_text(self, clip_id: str, text: str, font: str, color: str,
                      outline: str, bold: bool, italic: bool) -> bool:
        """Change a title's words and style."""
        return self._edit("text.edit",
                          lambda: self._project.set_clip_text(
                              clip_id, text, font, color, outline,
                              bold, italic))

    @Slot(str, str, result=bool)
    def set_clip_motion(self, clip_id: str, motion_id: str) -> bool:
        """Apply (or clear, with "") a motion preset to an overlay clip."""
        if self._project is None:
            return False
        if motion_id:
            from ive.motion.library import preset_by_id

            if preset_by_id(motion_id) is None:
                log.warning("Unknown motion preset %r", motion_id)
                return False
        return self._edit("motion.set",
                          lambda: self._project.set_clip_motion(clip_id,
                                                                motion_id))

    @Slot(str, float, float, float, float, result=bool)
    def set_clip_transform(self, clip_id: str, x: float, y: float,
                           scale: float, rotation: float) -> bool:
        """Reposition an overlay clip (sticker or text) on the canvas."""
        clip = (self._project.find_clip(clip_id)
                if self._project is not None else None)
        label = ("text.transform" if clip is not None and clip.text
                 else "sticker.transform")
        return self._edit(label,
                          lambda: self._project.set_clip_transform(
                              clip_id, x, y, scale, rotation))

    @Slot(str, result=float)
    def overlay_aspect(self, clip_id: str) -> float:
        """Width / height of an overlay clip's graphic, for the handles."""
        if self._project is None:
            return 1.0
        clip = self._project.find_clip(clip_id)
        if clip is None:
            return 1.0
        try:
            if clip.text:
                from ive.text.raster import text_aspect

                return float(text_aspect(clip.text, clip.font,
                                         clip.bold, clip.italic))
            if clip.sticker_id:
                from ive.stickers.library import sticker_by_id
                from ive.stickers.raster import sprite_aspect

                sticker = sticker_by_id(clip.sticker_id)
                if sticker is not None:
                    return float(sprite_aspect(sticker["path"],
                                               sticker["kind"]))
        except Exception:
            log.exception("Could not measure overlay clip %s", clip_id)
        return 1.0

    @Slot(str, str, float, result=bool)
    @Slot(str, str, float, str, result=bool)
    def set_clip_transition(self, clip_id: str, transition_id: str,
                            duration: float, edge: str = "out") -> bool:
        """Dress (or undress, with "") one edge of a video clip.

        ``edge`` "out" = the cut towards what follows (or the outro to
        black on the last clip); "in" = the intro from black.
        """
        if self._project is None:
            return False
        if transition_id:
            from ive.transitions.library import transition_by_id

            if transition_by_id(transition_id) is None:
                log.warning("Unknown transition %r", transition_id)
                return False
        return self._edit("transition.set",
                          lambda: self._project.set_clip_transition(
                              clip_id, transition_id, duration, edge))

    @Slot(str, float, float, result=bool)
    def trim_clip(self, clip_id: str, source_in: float, duration: float) -> bool:
        """Resize one clip, clamped to its source material."""
        return self._edit("timeline.trim",
                          lambda: self._project.trim_clip(clip_id, source_in,
                                                          duration))

    @Slot(str, bool, result=bool)
    def set_clip_muted(self, clip_id: str, muted: bool) -> bool:
        """Silence one clip; its volume survives for the unmute."""
        return self._edit("timeline.mute_clip",
                          lambda: self._project.set_clip_muted(clip_id, muted))

    @Slot(str, float, bool, result=bool)
    def place_music(self, path: str, at: float, cover: bool = False) -> bool:
        """Lay a music file on the Music lane at ``at`` seconds.

        The file joins the pool if it is not there yet (one probe, outside
        the recorded edit, like import). With ``cover`` the track repeats
        back to back until the A/V cut ends - a loop without a seam the
        user has to draw. One undo step for the whole placement.
        """
        if self._project is None:
            return False
        path = Path(_strip_url(str(path)))
        if not path.is_file():
            log.warning("Music file missing: %s", path)
            return False
        item = next((m for m in self._project.media
                     if Path(m.path) == path), None)
        new_item = None
        if item is None:
            new_item = self._probe_to_item(path)
            if new_item is None:
                return False
            item = new_item
        length = float(item.duration or 0.0)
        if length <= 0.1:
            log.warning("Music file has no duration: %s", path)
            return False
        at = max(0.0, float(at))
        cut_end = max((c.end for c in self._project.timeline if c.track == 0),
                      default=0.0)
        pieces: list[tuple[float, float]] = []
        if cover and cut_end > at + 0.1:
            cursor = at
            while cursor < cut_end - 0.05:
                pieces.append((cursor, min(length, cut_end - cursor)))
                cursor += length
        else:
            pieces.append((at, length))

        def mutate():
            if new_item is not None:
                self._project.add_media(new_item)
            for start, duration in pieces:
                self._project.add_music(item.id, start, duration)
            return True

        return self._edit("timeline.place_music", mutate,
                          media=new_item is not None)

    @Slot(str, str, result=bool)
    def set_clip_audio_effect(self, clip_id: str, effect_id: str) -> bool:
        """Apply an audio effect recipe to one clip's sound ("" = none)."""
        if self._project is None:
            return False
        if effect_id:
            from ive.audio.library import effect_by_id

            if effect_by_id(effect_id) is None:
                log.warning("Unknown audio effect %r", effect_id)
                return False
        return self._edit("timeline.audio_effect",
                          lambda: self._project.set_clip_audio_effect(
                              clip_id, effect_id))

    @Slot(str, bool, float, result=bool)
    def set_clip_ducking(self, clip_id: str, enabled: bool,
                         depth_db: float) -> bool:
        """Dip this music clip under the cut's speech, by ``depth_db``."""
        return self._edit("timeline.ducking",
                          lambda: self._project.set_clip_ducking(
                              clip_id, enabled, depth_db))

    @Slot(str, float, float, result=bool)
    def set_clip_fades(self, clip_id: str, fade_in: float,
                       fade_out: float) -> bool:
        """Audio fade in / fade out of one clip, in seconds."""
        return self._edit("timeline.fades",
                          lambda: self._project.set_clip_fades(
                              clip_id, fade_in, fade_out))

    @Slot(str, bool, result=bool)
    def set_clip_audio(self, clip_id: str, enabled: bool) -> bool:
        """Remove or restore one clip's sound; its volume is remembered."""
        return self._edit("timeline.remove_audio",
                          lambda: self._project.set_clip_audio(clip_id, enabled))

    @Slot(str, result=str)
    def clip_media_path(self, clip_id: str) -> str:
        """Resolve the file behind a timeline clip."""
        if self._project is None:
            return ""
        clip = next((c for c in self._project.timeline if c.id == clip_id), None)
        if clip is None:
            return ""
        return self.media_path(clip.media_id)

    # ── lifecycle ─────────────────────────────────────────────────────

    @Slot(str, str, result=bool)
    def create(self, name: str, folder: str) -> bool:
        """Start a new project and write it to disk straight away.

        Saving immediately means the folder exists and is writable before the
        user spends an hour importing into a project that cannot be stored.
        """
        name = (name or "").strip() or "Untitled"
        if any(ch in name for ch in '\\/:*?"<>|'):
            self.error.emit("invalid_name")
            log.warning("Rejected project name %r: illegal characters", name)
            return False

        target = Path(folder or self.defaultFolder).expanduser()
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.exception("Cannot create the project folder %s", target)
            self.error.emit(str(exc))
            return False

        # Never overwrite an existing document: "create" with the name of a
        # project that already exists used to silently replace an hour of
        # work with an empty file. A taken name gets a numbered variant
        # instead - the existing project stays reachable from the recents.
        unique = name
        counter = 2
        while (target / f"{unique}{PROJECT_SUFFIX}").exists():
            unique = f"{name} {counter}"
            counter += 1
        if unique != name:
            log.info("Project name %r is taken in %s; using %r",
                     name, target, unique)
            name = unique

        self._project = Project(name=name, folder=str(target))
        self._dirty = True
        self._clear_history()
        log.info("Project created: %s in %s", name, target)
        self.projectChanged.emit()
        self.mediaChanged.emit()
        self.timelineChanged.emit()
        self.dirtyChanged.emit()
        return self.save()

    @Slot(str, result=bool)
    def open(self, path: str) -> bool:
        file_path = Path(_strip_url(path))
        if not file_path.is_file():
            self.error.emit(f"not_found:{file_path.name}")
            return False
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not a project document")
            # Inside the try on purpose: valid JSON with a broken structure
            # used to raise out of this Slot, past any error signal, with
            # whatever project was open before left in an unknown state.
            loaded = Project.from_dict(data, folder=str(file_path.parent))
        except Exception as exc:
            log.exception("Could not read project %s", file_path)
            self.error.emit(str(exc))
            return False

        # The file the user opened is the truth. When its name on disk and
        # the name stored inside disagree (renamed in a file manager), keep
        # the disk name - otherwise every save() would go to a file derived
        # from the stored name, silently forking the project in two.
        if file_path.stem != loaded.name:
            log.info("Adopting the file name %r over the stored name %r",
                     file_path.stem, loaded.name)
            loaded.name = file_path.stem

        self._project = loaded
        self._check_missing()
        self._dirty = False
        self._clear_history()
        log.info("Project opened: %s (%d media)", self._project.name, len(self._project.media))
        self.projectChanged.emit()
        self.mediaChanged.emit()
        self.timelineChanged.emit()
        self.dirtyChanged.emit()
        return True

    @Slot(result=bool)
    def save(self) -> bool:
        if self._project is None:
            return False
        file_path = self._project.file_path
        if file_path is None:
            self.error.emit("no_folder")
            return False
        payload = json.dumps(self._project.to_dict(), indent=2, ensure_ascii=False)
        tmp = file_path.with_suffix(file_path.suffix + ".tmp")
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(file_path)      # atomic: never a half-written project
        except OSError as exc:
            log.exception("Could not save project to %s", file_path)
            self.error.emit(str(exc))
            return False
        self._dirty = False
        log.info("Project saved: %s", file_path)
        self.dirtyChanged.emit()
        return True

    @Slot(result=bool)
    def close(self) -> bool:
        if self._project is None:
            return True
        if self._dirty and not self.save():
            # Unsaved work must never be discarded because a save failed
            # (full disk, read-only folder): the project stays open and the
            # save() above has already emitted what went wrong.
            log.error("Not closing %s: the final save failed",
                      self._project.name)
            return False
        log.info("Project closed: %s", self._project.name)
        self._project = None
        self._dirty = False
        self._clear_history()
        self.projectChanged.emit()
        self.mediaChanged.emit()
        self.dirtyChanged.emit()
        return True

    # ── media pool ────────────────────────────────────────────────────

    @Slot("QVariantList", result=int)
    def import_paths(self, paths: list) -> int:
        """Import files and folders. Returns how many were added.

        Folders are scanned one level deep by default; that covers a camera
        card without walking an entire drive by accident.
        """
        if self._project is None:
            self.error.emit("no_project")
            return 0

        files: list[Path] = []
        for raw in paths:
            path = Path(_strip_url(str(raw)))
            if path.is_dir():
                files.extend(sorted(
                    p for p in path.rglob("*")
                    if p.is_file() and p.suffix.lower() in MEDIA_SUFFIXES
                ))
            elif path.is_file():
                files.append(path)

        # Probing happens OUTSIDE the recorded edit: it is slow I/O with no
        # model effect, and redoing an import must not read the files again.
        items: list[MediaItem] = []
        seen: set = set()
        skipped = failed = 0
        for path in files:
            if path.suffix.lower() not in MEDIA_SUFFIXES:
                skipped += 1
                continue
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            # `seen` catches duplicates inside this batch; has_path() the
            # ones already in the pool. Before the items were added as the
            # loop went, so has_path() alone covered both.
            if resolved in seen or self._project.has_path(path):
                skipped += 1
                continue
            item = self._probe_to_item(path)
            if item is None:
                failed += 1
                continue
            seen.add(resolved)
            items.append(item)

        added = len(items)
        if added:
            def mutate():
                for item in items:
                    self._project.add_media(item)
                return True

            self._edit("media.import", mutate, timeline=False, media=True)
        log.info("Import: %d added, %d skipped, %d failed", added, skipped, failed)
        self.imported.emit(added, skipped, failed)
        return added

    @Slot(str, result=bool)
    def remove_media(self, media_id: str) -> bool:
        # Its timeline clips go with it, so both lists are in the snapshot.
        return self._edit("media.remove",
                          lambda: self._project.remove_media(media_id),
                          media=True)

    @Slot(str, result=str)
    def localPath(self, url: str) -> str:
        """A filesystem path from a QML file dialog URL, for display and use."""
        return local_path_from_url(url)

    @Slot(str, result=str)
    def media_path(self, media_id: str) -> str:
        if self._project is None:
            return ""
        item = self._project.find_media(media_id)
        if item is None:
            return ""
        return str(item.resolve(self._project.base))

    @Slot(str, result=bool)
    def rename(self, name: str) -> bool:
        """Rename the project; the document file follows."""
        if self._project is None:
            return False
        name = (name or "").strip()
        if not name or any(ch in name for ch in '\\/:*?"<>|'):
            self.error.emit("invalid_name")
            return False
        old_name = self._project.name
        if name == old_name:
            return True
        old = self._project.file_path

        # Renaming must not overwrite another project's file. Same-file is
        # allowed (a case-only rename on Windows resolves to itself).
        base = self._project.base
        target = base / f"{name}{PROJECT_SUFFIX}" if base else None
        if target is not None and target.exists():
            same = False
            if old is not None and old.exists():
                try:
                    same = target.samefile(old)
                except OSError:
                    same = False
            if not same:
                self.error.emit(f"name_taken:{name}")
                log.warning("Not renaming to %r: %s already exists", name, target)
                return False

        self._project.name = name
        if not self.save():
            # The document on disk still has the old name; the model must
            # agree with it, or the next save forks the project in two.
            self._project.name = old_name
            return False
        self.projectChanged.emit()
        if old is not None and old.exists() and old != self._project.file_path:
            try:
                old.unlink()
            except OSError:
                log.warning("Could not remove the old project file %s", old)
        return True

    # ── internals ─────────────────────────────────────────────────────

    def _edit(self, label: str, mutate, *, timeline: bool = True,
              media: bool = False) -> bool:
        """Run one mutation through the undo stack, then notify and save.

        ``mutate`` returns falsy when the model refused the edit (unknown
        id, a split outside the clip); nothing is recorded then. Without a
        history (tests, scripts) the mutation applies directly.
        """
        if self._project is None:
            return False
        if self._history is None:
            if not mutate():
                return False
        else:
            command = ProjectEdit(self, label, timeline=timeline, media=media)
            if not command.capture(mutate):
                return False
            self._history.push(command)
        self._mark_dirty()
        if timeline:
            self.timelineChanged.emit()
        if media:
            self.mediaChanged.emit()
        self.save()
        return True

    def _history_restored(self, *, media_changed: bool,
                          timeline_changed: bool) -> None:
        """After an undo or redo put the model back: same duties as an edit."""
        self._mark_dirty()
        if timeline_changed:
            self.timelineChanged.emit()
        if media_changed:
            self.mediaChanged.emit()
        self.save()

    def _clear_history(self) -> None:
        """A new document means a new past: undo never crosses projects."""
        if self._history is not None:
            self._history.clear()

    def _probe_to_item(self, path: Path) -> MediaItem | None:
        try:
            info = probe(path)
        except MediaProbeError as exc:
            log.warning("Skipping %s: %s", path.name, exc)
            return None
        video = info.primary_video
        width = height = 0
        fps = 0.0
        if video is not None:
            width, height = video.display_size
            fps = float(video.fps)
        return MediaItem(
            path=self._project.relative_to_base(path) if self._project else str(path),
            name=path.name,
            duration=info.duration,
            width=width,
            height=height,
            fps=fps,
            has_audio=info.has_audio,
        )

    def _check_missing(self) -> None:
        """Flag links that no longer resolve, without refusing to open."""
        if self._project is None:
            return
        base = self._project.base
        missing = 0
        for item in self._project.media:
            item.missing = not item.resolve(base).is_file()
            missing += int(item.missing)
        if missing:
            log.warning("%d media file(s) missing in %s", missing, self._project.name)

    def _mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self.dirtyChanged.emit()


def _strip_url(value: str) -> str:
    """QML gives file:// URLs; the filesystem wants paths."""
    return local_path_from_url(value)


def _duration_label(seconds: float) -> str:
    if seconds <= 0:
        return ""
    total = int(round(seconds))
    if total >= 3600:
        return f"{total // 3600}:{(total // 60) % 60:02d}:{total % 60:02d}"
    return f"{total // 60}:{total % 60:02d}"
