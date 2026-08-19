"""The project model.

Plain Python, no Qt: it must stay serialisable and testable without an
interface. The UI observes it through :mod:`ive.core.services.project_service`.

Every stored file path is kept **relative to the project folder when possible**,
so moving or sending a project folder does not break its media links.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

__all__ = ["Project", "MediaItem", "TimelineClip", "SCHEMA_VERSION",
           "PROJECT_SUFFIX"]

#: Bumped whenever the on-disk shape changes; migrations live alongside.
SCHEMA_VERSION = 1
PROJECT_SUFFIX = ".iveproj"


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# JSON is edited by hand, synced by tools, and written by future versions:
# a field can arrive as the wrong type. Loading must degrade the field, not
# blow up the document - a TypeError here used to escape from open() and the
# user could not open their own project any more.

def _as_str(value: Any, default: str = "") -> str:
    return default if value is None else str(value)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class MediaItem:
    """One file in the project's media pool."""

    path: str                       # absolute, or relative to the project folder
    id: str = field(default_factory=_new_id)
    name: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = False
    #: Set when the file could not be found or read at load time.
    missing: bool = False

    def resolve(self, base: Path | None) -> Path:
        """Absolute path, resolved against the project folder when relative."""
        candidate = Path(self.path)
        if candidate.is_absolute() or base is None:
            return candidate
        return (base / candidate).resolve()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("missing", None)   # a runtime state, not part of the document
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaItem":
        path = _as_str(data.get("path"))
        if not path:
            raise ValueError("media entry has no path")
        return cls(
            path=path,
            id=_as_str(data.get("id")) or _new_id(),
            name=_as_str(data.get("name")),
            duration=_as_float(data.get("duration")),
            width=_as_int(data.get("width")),
            height=_as_int(data.get("height")),
            fps=_as_float(data.get("fps")),
            has_audio=bool(data.get("has_audio", False)),
        )


@dataclass
class TimelineClip:
    """One media item placed on the timeline.

    ``start`` and ``duration`` are seconds. Frames come later, with the
    sequence timebase; until then seconds keep the model honest about the fact
    that there is no timebase yet.
    """

    media_id: str
    start: float = 0.0
    duration: float = 0.0
    track: int = 0
    id: str = field(default_factory=_new_id)
    #: Offset into the source file, in seconds. Split sets it; 0 = the head.
    source_in: float = 0.0
    #: Audio gain of this clip: 1 = as recorded, 0 = silent, up to 2.
    volume: float = 1.0
    #: False = the clip's sound is removed from the sequence. Separate from
    #: volume, so restoring the audio brings the loudness it had back.
    audio_enabled: bool = True
    #: Muted is a STATE, not a volume of zero: unmuting must bring back the
    #: loudness the user had set, which volume=0 would have destroyed.
    muted: bool = False
    #: For clips on the Color track (track 1): the colour effect applied to
    #: the stretch of timeline this clip covers. media_id is "" for these.
    effect_id: str = ""
    #: For clips on the Sticker track (track 2): which sticker is shown.
    #: media_id is "" for these too.
    sticker_id: str = ""
    #: Transition TOWARDS THE NEXT clip on the same track ("" = a plain
    #: cut). It belongs to the outgoing clip, so it survives reorders.
    #: CapCut semantics: the next clip is pulled back by the transition's
    #: duration, so both sides have material - the sequence shortens by
    #: that much and no extra source material ("handles") is ever needed.
    transition_id: str = ""
    transition_duration: float = 0.5
    #: For clips on the Text track (track 3): the words on the video. A
    #: non-empty text is what MAKES a clip a text clip, exactly as a
    #: non-empty sticker_id makes a sticker clip.
    text: str = ""
    #: Text style. Empty font = the application's default family; empty
    #: outline = no outline. Colours are #RRGGBB strings.
    font: str = ""
    color: str = "#FFFFFF"
    outline: str = "#000000"
    bold: bool = True
    italic: bool = False
    #: Overlay placement (stickers AND text), in CANVAS FRACTIONS so it
    #: survives any export resolution: (x, y) is the centre, scale is the
    #: height as a fraction of the canvas height, rotation in degrees
    #: clockwise.
    x: float = 0.5
    y: float = 0.5
    scale: float = 0.3
    rotation: float = 0.0

    @property
    def end(self) -> float:
        return self.start + self.duration

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimelineClip":
        media_id = _as_str(data.get("media_id"))
        effect_id = _as_str(data.get("effect_id"))
        sticker_id = _as_str(data.get("sticker_id"))
        text = _as_str(data.get("text"))
        if not media_id and not effect_id and not sticker_id and not text:
            raise ValueError("timeline clip references no media, effect, "
                             "sticker or text")
        return cls(
            media_id=media_id,
            effect_id=effect_id,
            sticker_id=sticker_id,
            transition_id=_as_str(data.get("transition_id")),
            transition_duration=min(5.0, max(0.1, _as_float(
                data.get("transition_duration"), 0.5))),
            text=text,
            font=_as_str(data.get("font")),
            color=_as_str(data.get("color"), "#FFFFFF") or "#FFFFFF",
            # None (absent) falls back to the default; an explicit "" is
            # the user's "no outline" and survives the round trip.
            outline=_as_str(data.get("outline"), "#000000"),
            bold=bool(data.get("bold", True)),
            italic=bool(data.get("italic", False)),
            start=max(0.0, _as_float(data.get("start"))),
            duration=max(0.0, _as_float(data.get("duration"))),
            track=_as_int(data.get("track")),
            id=_as_str(data.get("id")) or _new_id(),
            source_in=max(0.0, _as_float(data.get("source_in"))),
            volume=min(2.0, max(0.0, _as_float(data.get("volume"), 1.0))),
            audio_enabled=bool(data.get("audio_enabled", True)),
            muted=bool(data.get("muted", False)),
            x=min(1.0, max(0.0, _as_float(data.get("x"), 0.5))),
            y=min(1.0, max(0.0, _as_float(data.get("y"), 0.5))),
            scale=min(2.0, max(0.02, _as_float(data.get("scale"), 0.3))),
            rotation=_as_float(data.get("rotation")),
        )


@dataclass
class Project:
    """A project: a name, a folder, and the media gathered into it."""

    name: str = "Untitled"
    folder: str = ""
    id: str = field(default_factory=_new_id)
    media: list[MediaItem] = field(default_factory=list)
    timeline: list[TimelineClip] = field(default_factory=list)
    #: Free-form, for things later stages add without a schema bump.
    extras: dict[str, Any] = field(default_factory=dict)

    # ── paths ─────────────────────────────────────────────────────────

    @property
    def base(self) -> Path | None:
        return Path(self.folder) if self.folder else None

    @property
    def file_path(self) -> Path | None:
        """Where the project document lives."""
        if not self.folder:
            return None
        return Path(self.folder) / f"{self.name}{PROJECT_SUFFIX}"

    def relative_to_base(self, path: Path) -> str:
        """Store a path relative to the project folder when it lives inside it."""
        base = self.base
        if base is None:
            return str(path)
        try:
            return str(path.resolve().relative_to(base.resolve()))
        except (ValueError, OSError):
            return str(path)

    # ── media pool ────────────────────────────────────────────────────

    def find_media(self, media_id: str) -> MediaItem | None:
        return next((m for m in self.media if m.id == media_id), None)

    def has_path(self, path: Path) -> bool:
        """True when this file is already in the pool (same resolved path)."""
        target = path.resolve()
        for item in self.media:
            try:
                if item.resolve(self.base).resolve() == target:
                    return True
            except OSError:
                continue
        return False

    def add_media(self, item: MediaItem) -> MediaItem:
        self.media.append(item)
        return item

    def remove_media(self, media_id: str) -> bool:
        item = self.find_media(media_id)
        if item is None:
            return False
        self.media.remove(item)
        # A pool item that goes away takes its timeline clips with it,
        # otherwise the timeline keeps referring to something that is gone.
        self.timeline = [c for c in self.timeline if c.media_id != media_id]
        self.reflow()
        return True

    # ── timeline ──────────────────────────────────────────────────────

    @property
    def timeline_duration(self) -> float:
        return max((c.end for c in self.timeline), default=0.0)

    def ordered_clips(self, track: int = 0) -> list["TimelineClip"]:
        return sorted((c for c in self.timeline if c.track == track),
                      key=lambda c: c.start)

    def reflow(self, track: int = 0) -> None:
        """Close the gaps: clips sit back to back in their current order.

        Gapless is the right default for assembling footage. Free positioning
        arrives with ripple editing; until then a gap would just be a hole the
        user cannot see the rules of.
        """
        self._lay(self.ordered_clips(track))

    def transition_overlap(self, left: "TimelineClip",
                           right: "TimelineClip") -> float:
        """Seconds the two clips overlap for ``left``'s transition.

        Capped at HALF of either clip, so a clip between two transitions
        still has a stretch where it stands alone and the windows can
        never touch each other.
        """
        if not left.transition_id:
            return 0.0
        return max(0.0, min(left.transition_duration,
                            left.duration / 2, right.duration / 2))

    def _lay(self, ordered: list["TimelineClip"]) -> None:
        """Positions for a run of clips: back to back, except that a clip
        after a transition starts EARLY by the overlap - both sides have
        material there, and that is where the blend happens."""
        cursor = 0.0
        prev = None
        for clip in ordered:
            overlap = (self.transition_overlap(prev, clip)
                       if prev is not None else 0.0)
            clip.start = max(0.0, cursor - overlap)
            cursor = clip.start + clip.duration
            prev = clip

    @staticmethod
    def _insertion_index(ordered: list["TimelineClip"], point: float) -> int:
        """Where ``point`` lands among ``ordered`` clips: the MIDPOINT rule.

        A drop before a clip's middle goes in front of it, past the middle
        goes after - the behaviour every editor trains the hand to expect.
        Sorting by raw start instead put a drop anywhere over the first
        clip BEFORE it, so "drag the new video onto the timeline" kept
        playing the new one first.
        """
        for index, clip in enumerate(ordered):
            if point < clip.start + clip.duration / 2:
                return index
        return len(ordered)

    def _reorder(self, ordered: list["TimelineClip"], track: int) -> None:
        """Lay ``ordered`` back to back and adopt it as the track's order."""
        self._lay(ordered)
        others = [c for c in self.timeline if c.track != track]
        self.timeline = others + ordered

    def add_clip(self, media_id: str, duration: float, at: float | None = None,
                 track: int = 0) -> "TimelineClip":
        """Place a clip: at the end, or where ``at`` (the drop point) says."""
        clip = TimelineClip(media_id=media_id, duration=max(0.1, duration), track=track)
        if at is None:
            clip.start = self.timeline_duration
            self.timeline.append(clip)
            return clip
        ordered = self.ordered_clips(track)
        ordered.insert(self._insertion_index(ordered, max(0.0, at)), clip)
        self._reorder(ordered, track)
        return clip

    #: Track 1 is the Color lane. Unlike track 0 it is NOT gapless: an
    #: effect sits exactly over the stretch of timeline the user gave it.
    COLOR_TRACK = 1

    def add_effect(self, effect_id: str, at: float,
                   duration: float) -> "TimelineClip":
        """Place a colour effect over ``[at, at+duration)`` on the Color lane."""
        clip = TimelineClip(media_id="", effect_id=str(effect_id),
                            start=max(0.0, float(at)),
                            duration=max(0.1, float(duration)),
                            track=self.COLOR_TRACK)
        self.timeline.append(clip)
        return clip

    #: Track 2 is the Sticker lane; free-form like the Color lane.
    STICKER_TRACK = 2

    def add_sticker(self, sticker_id: str, at: float, duration: float,
                    x: float = 0.5, y: float = 0.5, scale: float = 0.3,
                    rotation: float = 0.0) -> "TimelineClip":
        """Place a sticker over ``[at, at+duration)`` on the Sticker lane."""
        clip = TimelineClip(media_id="", sticker_id=str(sticker_id),
                            start=max(0.0, float(at)),
                            duration=max(0.1, float(duration)),
                            track=self.STICKER_TRACK,
                            x=min(1.0, max(0.0, float(x))),
                            y=min(1.0, max(0.0, float(y))),
                            scale=min(2.0, max(0.02, float(scale))),
                            rotation=float(rotation))
        self.timeline.append(clip)
        return clip

    #: Track 3 is the Text lane; free-form like the Color and Sticker lanes.
    TEXT_TRACK = 3

    def add_text(self, text: str, at: float, duration: float,
                 x: float = 0.5, y: float = 0.5, scale: float = 0.1,
                 rotation: float = 0.0, font: str = "",
                 color: str = "#FFFFFF", outline: str = "#000000",
                 bold: bool = True, italic: bool = False) -> "TimelineClip | None":
        """Place a title over ``[at, at+duration)`` on the Text lane."""
        text = str(text).strip()
        if not text:
            return None
        clip = TimelineClip(media_id="", text=text,
                            font=str(font), color=str(color) or "#FFFFFF",
                            outline=str(outline),
                            bold=bool(bold), italic=bool(italic),
                            start=max(0.0, float(at)),
                            duration=max(0.1, float(duration)),
                            track=self.TEXT_TRACK,
                            x=min(1.0, max(0.0, float(x))),
                            y=min(1.0, max(0.0, float(y))),
                            scale=min(2.0, max(0.02, float(scale))),
                            rotation=float(rotation))
        self.timeline.append(clip)
        return clip

    def set_clip_text(self, clip_id: str, text: str, font: str, color: str,
                      outline: str, bold: bool, italic: bool) -> bool:
        """Change a text clip's words and style."""
        clip = self.find_clip(clip_id)
        if clip is None or not clip.text:
            return False
        text = str(text).strip()
        if not text:
            # Empty words would erase the clip's very identity (text IS the
            # discriminator); deleting the clip is a different, explicit act.
            return False
        clip.text = text
        clip.font = str(font)
        clip.color = str(color) or "#FFFFFF"
        clip.outline = str(outline)
        clip.bold = bool(bold)
        clip.italic = bool(italic)
        return True

    def set_clip_transform(self, clip_id: str, x: float, y: float,
                           scale: float, rotation: float) -> bool:
        """Reposition an overlay clip (sticker or text) on the canvas."""
        clip = self.find_clip(clip_id)
        if clip is None or not (clip.sticker_id or clip.text):
            return False
        clip.x = min(1.0, max(0.0, float(x)))
        clip.y = min(1.0, max(0.0, float(y)))
        clip.scale = min(2.0, max(0.02, float(scale)))
        clip.rotation = float(rotation)
        return True

    def set_clip_transition(self, clip_id: str, transition_id: str,
                            duration: float = 0.5) -> bool:
        """Set (or clear, with "") the transition towards the next clip.

        Only the A/V track has cuts to dress; the timeline reflows so the
        next clip slides back by the overlap.
        """
        clip = self.find_clip(clip_id)
        if clip is None or clip.track != 0:
            return False
        clip.transition_id = str(transition_id)
        clip.transition_duration = min(5.0, max(0.1, float(duration)))
        self.reflow(0)
        return True

    def move_clip(self, clip_id: str, to: float) -> bool:
        """Reorder by dragging: ``to`` is the clip's proposed new start.

        The decision compares the dragged clip's LEADING EDGE against the
        other clips' midpoints as they would lie WITHOUT it (compacted).
        Using the dragged clip's centre instead breaks down when a long
        clip is dragged over a short one: its centre can never reach the
        short clip's midpoint, and the drag silently does nothing.
        """
        clip = self.find_clip(clip_id)
        if clip is None:
            return False
        if clip.track != 0:
            # The Color lane is free-form: a moved effect goes exactly
            # where the hand left it, nothing reorders around it.
            clip.start = max(0.0, float(to))
            return True
        others = [c for c in self.ordered_clips(clip.track) if c is not clip]
        to = max(0.0, to)
        cursor = 0.0
        index = len(others)
        for i, other in enumerate(others):
            if to < cursor + other.duration / 2:
                index = i
                break
            cursor += other.duration
        others.insert(index, clip)
        self._reorder(others, clip.track)
        return True

    def remove_clip(self, clip_id: str) -> bool:
        before = len(self.timeline)
        self.timeline = [c for c in self.timeline if c.id != clip_id]
        if len(self.timeline) == before:
            return False
        self.reflow()
        return True

    def find_clip(self, clip_id: str) -> "TimelineClip | None":
        return next((c for c in self.timeline if c.id == clip_id), None)

    def split_clip(self, clip_id: str, at: float) -> "TimelineClip | None":
        """Cut a clip in two at ``at`` (timeline seconds).

        The first part keeps the id, the second is a new clip whose
        ``source_in`` continues where the first part stops - so both halves
        play the same material they did before the cut. Nothing moves:
        the two halves occupy exactly the span the whole clip did.
        Returns the new second half, or None when ``at`` does not fall
        strictly inside the clip (a zero-length half is not a split).
        """
        clip = self.find_clip(clip_id)
        if clip is None:
            return None
        offset = at - clip.start
        # A hair from either edge is a misclick, not a cut.
        minimum = 0.05
        if offset < minimum or offset > clip.duration - minimum:
            return None
        second = TimelineClip(
            media_id=clip.media_id,
            start=clip.start + offset,
            duration=clip.duration - offset,
            track=clip.track,
            source_in=clip.source_in + offset,
            volume=clip.volume,
            audio_enabled=clip.audio_enabled,
            muted=clip.muted,
            effect_id=clip.effect_id,
            # Overlay clips keep what they are and where they sit: a split
            # title must show the same words at the same place on both sides.
            sticker_id=clip.sticker_id,
            text=clip.text, font=clip.font, color=clip.color,
            outline=clip.outline, bold=clip.bold, italic=clip.italic,
            x=clip.x, y=clip.y, scale=clip.scale, rotation=clip.rotation,
            # The transition OUT belongs to the tail: after a split it is
            # the second half that meets the next clip.
            transition_id=clip.transition_id,
            transition_duration=clip.transition_duration,
        )
        clip.duration = offset
        clip.transition_id = ""
        self.timeline.append(second)
        if clip.track == 0:
            # Durations changed under a possible overlap; keep positions
            # honest (a no-op without transitions: the two halves already
            # cover exactly the span the whole clip did).
            self.reflow(0)
        return second

    def set_clip_volume(self, clip_id: str, volume: float) -> bool:
        clip = self.find_clip(clip_id)
        if clip is None:
            return False
        clip.volume = min(2.0, max(0.0, float(volume)))
        return True

    def set_clip_audio(self, clip_id: str, enabled: bool) -> bool:
        """Remove (or restore) the clip's sound, keeping its volume."""
        clip = self.find_clip(clip_id)
        if clip is None:
            return False
        clip.audio_enabled = bool(enabled)
        return True

    def trim_clip(self, clip_id: str, source_in: float, duration: float) -> bool:
        """Resize a clip: new head offset into the source, new length.

        Clamped against the SOURCE: a clip can never show material the file
        does not have (head before 0, tail past the media duration), and
        never collapses below a tenth of a second. The timeline reflows, so
        neighbours close up around the new size.
        """
        clip = self.find_clip(clip_id)
        if clip is None:
            return False
        media = self.find_media(clip.media_id)
        limit = media.duration if media is not None and media.duration > 0 else None
        source_in = max(0.0, float(source_in))
        duration = max(0.1, float(duration))
        if limit is not None:
            source_in = min(source_in, max(0.0, limit - 0.1))
            duration = min(duration, limit - source_in)
        clip.source_in = source_in
        clip.duration = duration
        if clip.track == 0:
            # Only the A/V track is gapless; a resized effect stays put.
            self.reflow(0)
        return True

    def set_clip_muted(self, clip_id: str, muted: bool) -> bool:
        """Silence (or unsilence) the clip without touching its volume."""
        clip = self.find_clip(clip_id)
        if clip is None:
            return False
        clip.muted = bool(muted)
        return True

    # ── serialisation ─────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "name": self.name,
            "media": [m.to_dict() for m in self.media],
            "timeline": [c.to_dict() for c in self.timeline],
            "extras": self.extras,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], folder: str = "") -> "Project":
        version = int(data.get("schema_version", 0))
        if version > SCHEMA_VERSION:
            # Forward compatibility: load what we understand rather than
            # refusing the file outright. The user keeps their work.
            log.warning(
                "Project written by a newer version (schema %d > %d); "
                "unknown fields are ignored", version, SCHEMA_VERSION,
            )
        # An unreadable entry loses that entry, never the document: the rest
        # of the project is the user's work and must survive it.
        media: list[MediaItem] = []
        for entry in data.get("media") or []:
            if not isinstance(entry, dict):
                continue
            try:
                media.append(MediaItem.from_dict(entry))
            except ValueError as exc:
                log.warning("Skipping a media entry: %s", exc)
        timeline: list[TimelineClip] = []
        for entry in data.get("timeline") or []:
            if not isinstance(entry, dict):
                continue
            try:
                timeline.append(TimelineClip.from_dict(entry))
            except ValueError as exc:
                log.warning("Skipping a timeline clip: %s", exc)
        extras = data.get("extras")
        return cls(
            id=_as_str(data.get("id")) or _new_id(),
            name=_as_str(data.get("name")) or "Untitled",
            folder=folder,
            media=media,
            timeline=timeline,
            extras=dict(extras) if isinstance(extras, dict) else {},
        )
