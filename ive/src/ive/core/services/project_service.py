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

from PySide6.QtCore import Property, QObject, Qt, QThread, Signal, Slot

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


class _ImportWorker(QObject):
    """Probes media files off the GUI thread, one job at a time.

    Probing is the slow half of an import (FFmpeg opens every file); a
    camera-card folder froze the interface for seconds when it ran on
    the GUI thread. The worker only READS: it hands (path, probe info)
    pairs back and the service applies them to the model on the GUI
    thread, where the model lives (rule 4.8).
    """

    progress = Signal(int, int)          # done, total
    finished = Signal(object)            # {"job", "results", "cancelled"}

    def __init__(self) -> None:
        super().__init__()
        self._abort = False

    def cancel(self) -> None:
        # Called DIRECTLY from the GUI thread (a bool write is atomic
        # enough): a queued cancel would arrive when the job is over.
        self._abort = True

    def reset(self) -> None:
        # Armed by the service RIGHT BEFORE a job is dispatched - never
        # inside run(), where it would erase a cancel that raced ahead
        # of the queued start.
        self._abort = False

    @Slot(object)
    def run(self, job: dict) -> None:
        files = job["files"]
        results: list[tuple[str, Any]] = []
        for index, path in enumerate(files):
            if self._abort:
                break
            try:
                info = probe(Path(path))
            except MediaProbeError as exc:
                log.warning("Skipping %s: %s", Path(path).name, exc)
                info = None
            if info is not None:
                results.append((str(path), info))
            self.progress.emit(index + 1, len(files))
        self.finished.emit({"job": job, "results": results,
                            "cancelled": self._abort})


class ProjectService(QObject):
    """Owns the open project."""

    projectChanged = Signal()       # identity: opened, closed, renamed
    mediaChanged = Signal()         # the pool gained or lost items
    dirtyChanged = Signal()
    timelineChanged = Signal()
    error = Signal(str)
    #: (imported, skipped, failed) after an import batch.
    imported = Signal(int, int, int)

    importChanged = Signal()

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
        #: The async import worker (lazy: tests and scripts that only use
        #: the synchronous paths never pay for a thread).
        self._import_thread = None
        self._import_worker = None
        self._import_queue: list[dict[str, Any]] = []
        self._import_active: dict[str, Any] | None = None
        self._import_done = 0
        self._import_total = 0
        #: Copied clip snapshots, and the project they belong to.
        self._clipboard: list[dict[str, Any]] = []
        self._clipboard_project = ""

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
                "hdr": item.hdr,
                "missing": item.missing,
                "durationLabel": _duration_label(item.duration),
                # The HDR badge rides the size label: the user must know
                # this clip is being shown tone-mapped to SDR.
                "sizeLabel": (f"{item.width}x{item.height}"
                              + (" · HDR→SDR" if item.hdr else ""))
                             if item.width else "",
            })
        return out

    @Property("QVariantList", notify=timelineChanged)
    def timelineClips(self) -> list[dict[str, Any]]:
        """Clips on the timeline, resolved against the pool, ready for QML."""
        if self._project is None:
            return []
        from ive.color.library import effect_by_id
        from ive.music.library import track_by_path
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
            elif clip.track == Project.COLOR_TRACK:
                # A bare Adjust clip: the manual grade IS its identity.
                name = "Adjust"
            elif clip.sticker_id:
                sticker = sticker_by_id(clip.sticker_id)
                names = sticker["names"] if sticker else {}
                name = names.get("en") or clip.sticker_id
            elif clip.text:
                # The words themselves label the clip; one line, kept short.
                name = clip.text.split("\n")[0][:24]
            else:
                name = item.name if item else clip.media_id
                if clip.track == Project.MUSIC_TRACK and item is not None:
                    # The piece's TITLE, not its file name, when the
                    # library knows the file.
                    track = track_by_path(item.resolve(base))
                    if track is not None:
                        titles = track["titles"]
                        name = (titles.get("en")
                                or next(iter(titles.values()), name))
            out.append({
                "id": clip.id,
                "mediaId": clip.media_id,
                "effectId": clip.effect_id,
                "grade": dict(clip.grade),
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
                "speed": clip.speed,
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
                "placed": clip.placed,
                "words": list(clip.words),
                "karaoke": clip.karaoke,
                "karaokeColor": clip.karaoke_color,
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

    @Slot("QVariantList", result=bool)
    def remove_clips(self, clip_ids: list) -> bool:
        """Remove a whole selection - one undo step for all of it."""
        ids = [str(i) for i in clip_ids or []]
        if not ids:
            return False
        return self._edit("timeline.remove_clip",
                          lambda: self._project.remove_clips(ids) > 0)

    # ── clipboard ─────────────────────────────────────────────────────
    # Snapshots of copied clips, kept per project: a clip references its
    # pool entry, and pasting it into a project that never imported that
    # file would create a link to nothing.

    clipboardChanged = Signal()

    @Property(int, notify=clipboardChanged)
    def clipboardCount(self) -> int:
        return len(self._clipboard)

    @Slot("QVariantList", result=int)
    def copy_clips(self, clip_ids: list) -> int:
        """Snapshot the clips for a later paste. Returns how many."""
        if self._project is None:
            return 0
        documents = []
        for clip_id in clip_ids or []:
            clip = self._project.find_clip(str(clip_id))
            if clip is not None:
                documents.append(clip.to_dict())
        if documents:
            self._clipboard = documents
            self._clipboard_project = self._project.id
            self.clipboardChanged.emit()
            log.info("Copied %d clip(s)", len(documents))
        return len(documents)

    @Slot(float, result=int)
    def paste_clips(self, at: float = -1.0) -> int:
        """Paste the copied clips from ``at`` (negative = the end of the
        cut), keeping their spacing. One undo step; a clipboard from
        another project is refused, never half-linked."""
        if self._project is None or not self._clipboard:
            return 0
        if self._clipboard_project != self._project.id:
            log.warning("Clipboard belongs to another project; not pasting")
            self.error.emit("clipboard_other_project")
            return 0
        if at < 0:
            at = self._project.timeline_duration
        import copy as _copy

        documents = _copy.deepcopy(self._clipboard)
        pasted: list = []

        def mutate():
            pasted.extend(self._project.paste_clips(documents, at))
            return bool(pasted)

        if not self._edit("timeline.paste", mutate):
            return 0
        log.info("Pasted %d clip(s) at %.2fs", len(pasted), at)
        return len(pasted)

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

    @Slot(float, result=bool)
    def place_grade(self, at: float) -> bool:
        """An "Adjust" clip at ``at``: manual dials, no recipe.

        Dropped over a video clip it adopts that clip's exact span (the
        common intent, same as the effect drop); on empty ground it
        covers three seconds and the trim handles take it from there.
        """
        if self._project is None:
            return False
        start, duration = float(at), 3.0
        for clip in self._project.timeline:
            if clip.track == 0 and clip.media_id \
                    and clip.start <= at < clip.end:
                start, duration = clip.start, clip.duration
                break

        def mutate():
            clip = self._project.add_grade(start, duration)
            log.info("Adjust clip placed at %.2fs for %.2fs",
                     clip.start, clip.duration)
            return clip

        return self._edit("color.adjust", mutate)

    @Slot(str, str, float, result=bool)
    def set_clip_grade(self, clip_id: str, key: str, value: float) -> bool:
        """Turn one dial of a Color-lane clip's manual grade."""
        return self._edit("color.grade",
                          lambda: self._project.set_clip_grade(clip_id,
                                                               key, value))

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

    @Slot("QVariantList", result=int)
    def place_subtitles(self, lines: list) -> int:
        """Generated subtitle lines land as text clips - ONE undo step.

        Each entry is ``{"start", "end", "text"}`` in timeline seconds.
        The clips are ordinary titles in the subtitle position (low,
        small), so every line is editable, movable and deletable by
        hand afterwards - the AI produced a starting point, nothing
        opaque (docs/AI_FEATURES.md §1). Returns how many lines landed.
        """
        if self._project is None:
            return 0
        payload = []
        for raw in (lines.toVariant() if hasattr(lines, "toVariant")
                    else lines) or []:
            text = str(raw.get("text") or "").strip()
            try:
                start = float(raw.get("start"))
                end = float(raw.get("end"))
            except (TypeError, ValueError):
                continue
            if not text or not end > start >= 0.0:
                continue
            # Word timestamps come in TIMELINE time (the transcriber's
            # frame of reference); the clip stores them CLIP-LOCAL so
            # they survive the clip being moved.
            words = []
            for word in raw.get("words") or []:
                try:
                    w_start = float(word.get("start")) - start
                    w_end = float(word.get("end")) - start
                except (TypeError, ValueError):
                    continue
                w_text = str(word.get("text") or "").strip()
                if w_text and w_end > w_start >= -1e-3:
                    words.append({"start": max(0.0, w_start),
                                  "end": w_end, "text": w_text})
            payload.append((start, end, text, words))
        if not payload:
            return 0

        def mutate():
            landed = 0
            for start, end, text, words in payload:
                clip = self._project.add_text(
                    text, start, max(0.1, end - start),
                    y=0.88, scale=0.05, words=words)
                if clip is not None:
                    landed += 1
            return landed > 0

        if not self._edit("timeline.subtitles", mutate):
            return 0
        log.info("Subtitles placed: %d lines", len(payload))
        return len(payload)

    @Slot("QVariantList", result=int)
    def apply_translations(self, changes: list) -> int:
        """Translated words land on their clips - ONE undo step.

        Each entry is ``{"clip_id", "text"}``. Timings stay exactly as
        they were (docs/AI_FEATURES.md §5); the WORD timestamps and the
        karaoke switch are cleared, because they belong to the original
        language's words and lighting the wrong ones would be worse
        than lighting none. Ctrl+Z brings the original text (and its
        karaoke) back whole. Returns how many clips changed.
        """
        if self._project is None:
            return 0
        payload = []
        for raw in (changes.toVariant() if hasattr(changes, "toVariant")
                    else changes) or []:
            clip_id = str(raw.get("clip_id") or "")
            text = str(raw.get("text") or "").strip()
            if clip_id and text:
                payload.append((clip_id, text))
        if not payload:
            return 0
        applied = 0

        def mutate():
            nonlocal applied
            for clip_id, text in payload:
                clip = self._project.find_clip(clip_id)
                if clip is None or not clip.text:
                    continue
                clip.text = text
                clip.words = []
                clip.karaoke = False
                applied += 1
            return applied > 0

        if not self._edit("subtitles.translate", mutate):
            return 0
        log.info("Translations applied: %d clips", applied)
        return applied

    @Slot(str, bool, result=bool)
    def set_clip_karaoke(self, clip_id: str, enabled: bool) -> bool:
        """Light the words of one subtitle up as they are spoken."""
        return self._edit("text.karaoke",
                          lambda: self._project.set_clip_karaoke(
                              clip_id, enabled))

    @Slot(str, result=int)
    def export_subtitles(self, path: str) -> int:
        """Write the Text lane as a subtitle FILE - .srt or .vtt.

        The dialect follows the extension. Every Text-lane clip is a
        cue, whatever made it - generated, imported or typed by hand:
        the lane IS the subtitle track. Returns how many cues were
        written; 0 means nothing to write or an unwritable path.
        """
        if self._project is None:
            return 0
        from ive.text.subtitle_files import format_srt, format_vtt

        lines = [{"start": clip.start, "end": clip.end, "text": clip.text}
                 for clip in self._project.timeline
                 if clip.track == self._project.TEXT_TRACK and clip.text]
        if not lines:
            return 0
        target = Path(_strip_url(str(path)))
        content = (format_vtt(lines) if target.suffix.lower() == ".vtt"
                   else format_srt(lines))
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError:
            log.exception("Could not write subtitles to %s", target)
            return 0
        log.info("Subtitles exported: %d cues -> %s", len(lines), target)
        return len(lines)

    @Slot(str, result=int)
    def import_subtitles(self, path: str) -> int:
        """Read an .srt/.vtt file onto the Text lane, one undo step.

        The cues land through the same gate the generated lines use, so
        position, size and editability are identical. Returns the cue
        count; 0 = unreadable file or nothing readable in it.
        """
        if self._project is None:
            return 0
        from ive.text.subtitle_files import parse_subtitles

        source = Path(_strip_url(str(path)))
        try:
            content = source.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            log.warning("Could not read subtitle file %s", source)
            return 0
        lines = parse_subtitles(content)
        if not lines:
            return 0
        count = self.place_subtitles(lines)
        log.info("Subtitles imported: %d cues from %s", count, source)
        return count

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
                 else "video.transform" if clip is not None
                 and clip.media_id else "sticker.transform")
        return self._edit(label,
                          lambda: self._project.set_clip_transform(
                              clip_id, x, y, scale, rotation))

    @Slot(str, result=bool)
    def reset_clip_transform(self, clip_id: str) -> bool:
        """Hand a placed A/V clip back to the project's canvas fit."""
        return self._edit("video.transform_reset",
                          lambda: self._project.reset_clip_transform(clip_id))

    @Slot(str, result=float)
    def overlay_aspect(self, clip_id: str) -> float:
        """Width / height of an overlay clip's graphic, for the handles."""
        if self._project is None:
            return 1.0
        clip = self._project.find_clip(clip_id)
        if clip is None:
            return 1.0
        try:
            if clip.media_id and clip.track == 0:
                # An A/V clip: the picture's DISPLAY aspect, for the
                # canvas-placement handles.
                item = self._project.find_media(clip.media_id) \
                    if hasattr(self._project, "find_media") else None
                if item is None:
                    item = next((m for m in self._project.media
                                 if m.id == clip.media_id), None)
                if item is not None and item.height:
                    return max(0.05, float(item.width) / float(item.height))
                return 16.0 / 9.0
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
    @Slot(str, float, float, float, result=bool)
    def trim_clip(self, clip_id: str, source_in: float, duration: float,
                  start: float = -1.0) -> bool:
        """Resize one clip, clamped to its source material.

        ``start`` < 0 keeps the clip where it is; a head trim on a free
        lane passes the new start so the LEFT edge is the one moving.
        """
        return self._edit("timeline.trim",
                          lambda: self._project.trim_clip(
                              clip_id, source_in, duration,
                              start=None if start < 0 else float(start)))

    @Slot(str, float, result=bool)
    def set_clip_speed(self, clip_id: str, speed: float) -> bool:
        """Change an A/V clip's pace (0.1-8x); the track reflows."""
        return self._edit("timeline.speed",
                          lambda: self._project.set_clip_speed(clip_id,
                                                               speed))

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

    @Slot("QVariantList", float, result=int)
    def import_and_place(self, paths: list, at: float) -> int:
        """Files dropped ON the timeline: pool and cut in ONE undo step.

        Each usable file (folders scanned like import) becomes a pool
        entry - reused when the file is already there - and a clip on the
        A/V track, laid back to back from the drop point. Probing happens
        outside the recorded edit, like import; one Ctrl+Z takes the
        clips AND the new pool entries away together. Returns how many
        clips were placed.
        """
        if self._project is None:
            self.error.emit("no_project")
            return 0
        at = max(0.0, float(at))
        files: list[Path] = []
        for raw in paths:
            path = Path(_strip_url(str(raw)))
            if path.is_dir():
                files.extend(sorted(
                    p for p in path.rglob("*")
                    if p.is_file() and p.suffix.lower() in MEDIA_SUFFIXES
                ))
            elif path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES:
                files.append(path)
        base = self._project.base
        new_items: list[MediaItem] = []
        line: list[MediaItem] = []
        seen: set = set()
        for file in files:
            try:
                resolved = file.resolve()
            except OSError:
                resolved = file
            if resolved in seen:
                continue
            seen.add(resolved)
            def _same(entry) -> bool:
                try:
                    return Path(entry.resolve(base)).resolve() == resolved
                except OSError:
                    return False

            existing = next((m for m in self._project.media if _same(m)),
                            None)
            item = existing or self._probe_to_item(file)
            if item is None:
                continue
            if existing is None:
                new_items.append(item)
            line.append(item)
        if not line:
            self.error.emit("nothing_imported")
            return 0

        def mutate():
            for item in new_items:
                self._project.add_media(item)
            cursor = at
            for item in line:
                duration = item.duration or 5.0
                clip = self._project.add_clip(item.id, duration, at=cursor)
                cursor = clip.end
            return True

        if not self._edit("timeline.place_media", mutate,
                          media=bool(new_items)):
            return 0
        log.info("Dropped %d file(s) onto the timeline at %.2fs "
                 "(%d new in the pool)", len(line), at, len(new_items))
        return len(line)

    # ── asynchronous import ───────────────────────────────────────────
    # The slow half of an import is the probe (FFmpeg opens every file);
    # these run it on a worker and apply the results in ONE edit when it
    # lands. The interface never freezes, a progress line says where the
    # job is, and cancel discards the batch whole - never half a landing.

    @Property(bool, notify=importChanged)
    def importing(self) -> bool:
        return self._import_active is not None

    @Property(int, notify=importChanged)
    def importDone(self) -> int:
        return self._import_done

    @Property(int, notify=importChanged)
    def importTotal(self) -> int:
        return self._import_total

    _startImport = Signal(object)

    @Slot("QVariantList", result=int)
    def import_paths_async(self, paths: list) -> int:
        """Import off the GUI thread. Returns how many files were queued
        (0 = nothing usable); the pool updates when the probing lands."""
        return self._queue_import(paths, None)

    @Slot("QVariantList", float, result=int)
    def import_and_place_async(self, paths: list, at: float) -> int:
        """The drop-on-the-timeline gesture, probed off the GUI thread:
        the clips land where the pointer said, when the probing is done."""
        return self._queue_import(paths, max(0.0, float(at)))

    @Slot()
    def cancel_import(self) -> None:
        """Stop the running batch and drop the waiting ones. Nothing of
        a cancelled batch is applied: no half landings."""
        self._import_queue.clear()
        if self._import_worker is not None and self._import_active:
            self._import_worker.cancel()

    def _queue_import(self, paths: list, at: float | None) -> int:
        if self._project is None:
            self.error.emit("no_project")
            return 0
        files = [str(f) for f in self._collect_files(paths)]
        if not files:
            self.error.emit("nothing_imported")
            return 0
        self._import_queue.append({"files": files, "at": at,
                                   "project_id": self._project.id})
        self._ensure_import_worker()
        self._dispatch_import()
        return len(files)

    def _collect_files(self, paths: list) -> list[Path]:
        """Files and folders (recursive), media suffixes only, deduped -
        the fast part of an import, safe on the GUI thread."""
        files: list[Path] = []
        seen: set = set()
        for raw in paths:
            path = Path(_strip_url(str(raw)))
            if path.is_dir():
                candidates = sorted(
                    p for p in path.rglob("*")
                    if p.is_file() and p.suffix.lower() in MEDIA_SUFFIXES)
            elif path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES:
                candidates = [path]
            else:
                continue
            for file in candidates:
                try:
                    resolved = file.resolve()
                except OSError:
                    resolved = file
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(file)
        return files

    def _ensure_import_worker(self) -> None:
        if self._import_thread is not None:
            return
        self._import_thread = QThread()
        self._import_thread.setObjectName("import")
        self._import_worker = _ImportWorker()
        self._import_worker.moveToThread(self._import_thread)
        self._startImport.connect(self._import_worker.run)
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_thread.start()

    def _dispatch_import(self) -> None:
        if self._import_active is not None or not self._import_queue:
            return
        self._import_active = self._import_queue.pop(0)
        self._import_done = 0
        self._import_total = len(self._import_active["files"])
        self._import_worker.reset()
        self.importChanged.emit()
        self._startImport.emit(self._import_active)

    def _on_import_progress(self, done: int, total: int) -> None:
        self._import_done, self._import_total = done, total
        self.importChanged.emit()

    def _on_import_finished(self, payload: dict) -> None:
        job = payload["job"]
        results = payload["results"]
        self._import_active = None
        self.importChanged.emit()
        try:
            if payload["cancelled"]:
                log.info("Import cancelled; %d probed file(s) discarded",
                         len(results))
                return
            if self._project is None or self._project.id != job["project_id"]:
                log.info("Import landed after its project closed; discarded")
                return
            self._apply_import(results, job["at"])
        finally:
            self._dispatch_import()

    def _apply_import(self, results: list, at: float | None) -> None:
        """Turn probed files into pool entries (and clips, for a drop on
        the timeline) - ONE edit, exactly like the synchronous paths."""
        base = self._project.base
        new_items: list[MediaItem] = []
        line: list[MediaItem] = []
        for path_str, info in results:
            path = Path(path_str)
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path

            def _same(entry) -> bool:
                try:
                    return Path(entry.resolve(base)).resolve() == resolved
                except OSError:
                    return False

            existing = next((m for m in self._project.media if _same(m)),
                            None)
            if existing is not None:
                if at is not None:
                    line.append(existing)
                continue
            video = info.primary_video
            width = height = 0
            fps = 0.0
            if video is not None:
                width, height = video.display_size
                fps = float(video.fps)
            item = MediaItem(
                path=self._project.relative_to_base(path),
                name=path.name, duration=info.duration,
                width=width, height=height, fps=fps,
                has_audio=info.has_audio,
                hdr=bool(video is not None and video.is_hdr),
            )
            new_items.append(item)
            line.append(item)
        if not new_items and not line:
            self.error.emit("nothing_imported")
            return

        def mutate():
            for item in new_items:
                self._project.add_media(item)
            if at is not None:
                cursor = at
                for item in line:
                    clip = self._project.add_clip(
                        item.id, item.duration or 5.0, at=cursor)
                    cursor = clip.end
            return True

        label = "timeline.place_media" if at is not None else "media.import"
        self._edit(label, mutate, timeline=at is not None,
                   media=bool(new_items))
        log.info("Async import landed: %d new in the pool, %d clip(s) "
                 "placed", len(new_items), len(line) if at is not None else 0)

    def shutdown(self) -> None:
        """Stop the import worker; safe to call with none running."""
        self.cancel_import()
        if self._import_thread is not None:
            self._import_thread.quit()
            if not self._import_thread.wait(4000):
                log.warning("Import thread did not stop in time")
                self._import_thread.terminate()
                self._import_thread.wait(1000)
            self._import_thread = None
            self._import_worker = None

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
            hdr=bool(video is not None and video.is_hdr),
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
