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
    #: PQ/HLG material: shown and exported tone-mapped to SDR
    #: (docs/MEDIA_FORMATS.md §8) - the user gets told, never surprised.
    hdr: bool = False
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
            hdr=bool(data.get("hdr", False)),
        )


def _clean_crop(crop: dict) -> dict:
    """Known edges only, clamped to 0..0.45, zeros dropped."""
    out: dict[str, float] = {}
    for edge in ("left", "top", "right", "bottom"):
        try:
            value = float((crop or {}).get(edge, 0.0))
        except (TypeError, ValueError):
            continue
        value = min(0.45, max(0.0, value))
        if value > 1e-4:
            out[edge] = round(value, 4)
    return out


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
    #: Playback pace: 2.0 shows the material twice as fast (and the clip
    #: occupies half the timeline), 0.5 is slow motion. One TIMELINE
    #: second consumes ``speed`` SOURCE seconds - the conversion every
    #: piece of source_in arithmetic below must apply.
    speed: float = 1.0
    #: Audio gain of this clip: 1 = as recorded, 0 = silent, up to 2.
    volume: float = 1.0
    #: False = the clip's sound is removed from the sequence. Separate from
    #: volume, so restoring the audio brings the loudness it had back.
    audio_enabled: bool = True
    #: Muted is a STATE, not a volume of zero: unmuting must bring back the
    #: loudness the user had set, which volume=0 would have destroyed.
    muted: bool = False
    #: Audio effect applied to this clip's sound: the id of an ops recipe
    #: from the audio catalogue, "" = as recorded.
    audio_effect_id: str = ""
    #: Audio fades at the clip's head and tail, in seconds (0 = none).
    fade_in: float = 0.0
    fade_out: float = 0.0
    #: Ducking (Music-lane clips): dip this bed by ``duck_db`` while the
    #: cut is talking. The detector is a global preference, the choice
    #: and the amount are the clip's.
    duck: bool = False
    duck_db: float = 12.0
    #: For clips on the Color track (track 1): the colour effect applied to
    #: the stretch of timeline this clip covers. media_id is "" for these.
    effect_id: str = ""
    #: Manual grade on a Color-lane clip: dial values away from their
    #: defaults (ive/color/grade.py), layered AFTER the effect recipe.
    #: A clip may carry a grade alone - the "Adjust" clip.
    grade: dict = field(default_factory=dict)
    #: For clips on the Sticker track (track 2): which sticker is shown.
    #: media_id is "" for these too.
    sticker_id: str = ""
    #: Transition TOWARDS WHAT FOLLOWS this clip ("" = a plain cut). It
    #: belongs to the outgoing clip, so it survives reorders. With a next
    #: clip, CapCut semantics: the next clip is pulled back by the
    #: transition's duration, so both sides have material - the sequence
    #: shortens by that much and no extra source material ("handles") is
    #: ever needed. On the LAST clip it plays as an OUTRO towards black.
    transition_id: str = ""
    transition_duration: float = 0.5
    #: Transition FROM BLACK at this clip's head - the intro. Read only
    #: on the first clip of the timeline.
    transition_in_id: str = ""
    transition_in_duration: float = 0.5
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
    #: Word timestamps inside a text clip, CLIP-LOCAL seconds:
    #: ``[{"start", "end", "text"}, ...]``. The automatic subtitles fill
    #: them; hand-made titles have none. What makes karaoke possible.
    words: list = field(default_factory=list)
    #: Karaoke: words switch to ``karaoke_color`` as they are spoken.
    #: Only meaningful on a clip that HAS words.
    karaoke: bool = False
    karaoke_color: str = "#FFD467"
    #: Motion preset applied to an overlay clip (sticker or text): the
    #: id of a keyframe recipe from the motion catalogue, "" = still.
    motion_id: str = ""
    #: Overlay placement (stickers AND text), in CANVAS FRACTIONS so it
    #: survives any export resolution: (x, y) is the centre, scale is the
    #: height as a fraction of the canvas height, rotation in degrees
    #: clockwise. A/V clips use the same fields once ``placed`` is on.
    x: float = 0.5
    y: float = 0.5
    scale: float = 0.3
    rotation: float = 0.0
    #: A/V clips only: True = this clip is placed FREELY on the canvas
    #: with the transform above (CapCut's pinch), False = the project's
    #: canvas fit strategy applies. Overlays ignore it (always placed).
    placed: bool = False
    #: A/V clips: crop insets as FRACTIONS of the source picture
    #: (keys left/top/right/bottom, each 0..0.45, zeros dropped - the
    #: dict says exactly which edges the user pulled).
    crop: dict = field(default_factory=dict)
    #: A/V clips: 1 = opaque, towards 0 the picture fades into what is
    #: underneath (the black track, or the other roll in a window).
    opacity: float = 1.0
    #: Transform/opacity keyframes, CLIP-LOCAL seconds
    #: (utils/keyframes.py): [{"t", "x"?, "y"?, "scale"?, "rotation"?,
    #: "opacity"?}, ...] sorted. Empty = the static fields above rule.
    keyframes: list = field(default_factory=list)

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
        # A Color-lane clip may be a bare "Adjust": no effect, just a
        # manual grade (possibly still at its defaults).
        is_colour_lane = _as_int(data.get("track")) == 1
        if (not media_id and not effect_id and not sticker_id and not text
                and not is_colour_lane):
            raise ValueError("timeline clip references no media, effect, "
                             "sticker or text")
        from ive.color.grade import clamp_grade

        return cls(
            media_id=media_id,
            effect_id=effect_id,
            grade=clamp_grade(data.get("grade") or {}),
            sticker_id=sticker_id,
            transition_id=_as_str(data.get("transition_id")),
            transition_duration=min(5.0, max(0.1, _as_float(
                data.get("transition_duration"), 0.5))),
            transition_in_id=_as_str(data.get("transition_in_id")),
            transition_in_duration=min(5.0, max(0.1, _as_float(
                data.get("transition_in_duration"), 0.5))),
            text=text,
            words=[{"start": max(0.0, _as_float(w.get("start"))),
                    "end": max(0.0, _as_float(w.get("end"))),
                    "text": _as_str(w.get("text"))}
                   for w in (data.get("words") or [])
                   if isinstance(w, dict) and _as_str(w.get("text"))],
            karaoke=bool(data.get("karaoke", False)),
            karaoke_color=_as_str(data.get("karaoke_color"),
                                  "#FFD467") or "#FFD467",
            font=_as_str(data.get("font")),
            color=_as_str(data.get("color"), "#FFFFFF") or "#FFFFFF",
            # None (absent) falls back to the default; an explicit "" is
            # the user's "no outline" and survives the round trip.
            outline=_as_str(data.get("outline"), "#000000"),
            motion_id=_as_str(data.get("motion_id")),
            bold=bool(data.get("bold", True)),
            italic=bool(data.get("italic", False)),
            start=max(0.0, _as_float(data.get("start"))),
            duration=max(0.0, _as_float(data.get("duration"))),
            track=_as_int(data.get("track")),
            id=_as_str(data.get("id")) or _new_id(),
            source_in=max(0.0, _as_float(data.get("source_in"))),
            speed=min(8.0, max(0.1, _as_float(data.get("speed"), 1.0))),
            volume=min(2.0, max(0.0, _as_float(data.get("volume"), 1.0))),
            audio_enabled=bool(data.get("audio_enabled", True)),
            muted=bool(data.get("muted", False)),
            audio_effect_id=_as_str(data.get("audio_effect_id")),
            fade_in=min(30.0, max(0.0, _as_float(data.get("fade_in")))),
            fade_out=min(30.0, max(0.0, _as_float(data.get("fade_out")))),
            duck=bool(data.get("duck", False)),
            duck_db=min(30.0, max(0.0, _as_float(data.get("duck_db"), 12.0))),
            x=min(1.0, max(0.0, _as_float(data.get("x"), 0.5))),
            y=min(1.0, max(0.0, _as_float(data.get("y"), 0.5))),
            scale=min(2.0, max(0.02, _as_float(data.get("scale"), 0.3))),
            rotation=_as_float(data.get("rotation")),
            placed=bool(data.get("placed", False)),
            crop=_clean_crop(data.get("crop") or {}),
            opacity=min(1.0, max(0.0, _as_float(data.get("opacity"), 1.0))),
            keyframes=[
                {**{str(k): float(v) for k, v in entry.items()
                    if k in ("t", "x", "y", "scale", "rotation",
                             "opacity")},
                 **({"easing": str(entry["easing"])}
                    if entry.get("easing") else {})}
                for entry in (data.get("keyframes") or [])
                if isinstance(entry, dict) and "t" in entry
            ],
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

    #: The Music lane: audio-only clips laid FREELY under the cut (they
    #: overlap the A/V track by design), never reflowed.
    MUSIC_TRACK = 4

    def add_music(self, media_id: str, at: float,
                  duration: float) -> "TimelineClip":
        """A music clip exactly at ``at``: free placement, no reorder."""
        clip = TimelineClip(media_id=media_id, start=max(0.0, float(at)),
                            duration=max(0.1, float(duration)),
                            track=self.MUSIC_TRACK)
        self.timeline.append(clip)
        return clip

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

    def add_grade(self, at: float, duration: float) -> "TimelineClip":
        """An "Adjust" clip: a manual grade with no recipe underneath."""
        clip = TimelineClip(media_id="", effect_id="",
                            start=max(0.0, float(at)),
                            duration=max(0.1, float(duration)),
                            track=self.COLOR_TRACK)
        self.timeline.append(clip)
        return clip

    def set_clip_grade(self, clip_id: str, key: str, value: float) -> bool:
        """Turn one dial of a Color-lane clip's manual grade.

        Setting a dial back to its default REMOVES it from the grade:
        the dict stays the exact list of what the user changed.
        """
        from ive.color.grade import DIALS, clamp_grade

        clip = self.find_clip(clip_id)
        if clip is None or clip.track != self.COLOR_TRACK \
                or str(key) not in DIALS:
            return False
        merged = dict(clip.grade)
        merged[str(key)] = float(value)
        clip.grade = clamp_grade(merged)
        return True

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
                 bold: bool = True, italic: bool = False,
                 words: list | None = None) -> "TimelineClip | None":
        """Place a title over ``[at, at+duration)`` on the Text lane.

        ``words`` are CLIP-LOCAL word timestamps (the automatic
        subtitles pass them); they enable the karaoke switch later.
        """
        text = str(text).strip()
        if not text:
            return None
        clip = TimelineClip(media_id="", text=text,
                            words=list(words or []),
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

    def set_clip_speed(self, clip_id: str, speed: float) -> bool:
        """Change an A/V clip's pace; the SOURCE material stays the same.

        CapCut semantics: the clip keeps showing exactly the span of
        footage it showed, so at 2x it occupies half the timeline and
        the gapless track reflows around it. Clamped to 0.1-8x and to
        the tenth-of-a-second minimum every clip has.
        """
        clip = self.find_clip(clip_id)
        if clip is None or not clip.media_id or clip.track != 0:
            return False
        speed = min(8.0, max(0.1, float(speed)))
        if abs(speed - clip.speed) < 1e-6:
            return True
        source_span = clip.duration * clip.speed
        clip.duration = max(0.1, source_span / speed)
        clip.speed = speed
        self.reflow(0)
        return True

    def set_clip_karaoke(self, clip_id: str, enabled: bool,
                         color: str = "") -> bool:
        """Turn per-word highlighting on or off for one text clip.

        Only a clip WITH word timestamps can light up: without them
        there is nothing to time the highlight against, and pretending
        otherwise would paint garbage.
        """
        clip = self.find_clip(clip_id)
        if clip is None or not clip.text or not clip.words:
            return False
        clip.karaoke = bool(enabled)
        if color:
            clip.karaoke_color = str(color)
        return True

    def set_clip_motion(self, clip_id: str, motion_id: str) -> bool:
        """Apply (or clear, with "") a motion preset to an overlay clip."""
        clip = self.find_clip(clip_id)
        if clip is None or not (clip.sticker_id or clip.text):
            return False
        clip.motion_id = str(motion_id)
        return True

    def set_clip_transform(self, clip_id: str, x: float, y: float,
                           scale: float, rotation: float) -> bool:
        """Reposition a clip on the canvas: overlays, or an A/V clip.

        For an A/V clip the first transform also turns ``placed`` on -
        from then on the clip floats freely instead of following the
        project's canvas fit. ``reset_clip_transform`` hands it back.
        """
        clip = self.find_clip(clip_id)
        if clip is None:
            return False
        is_video = bool(clip.media_id) and clip.track == 0
        if not (clip.sticker_id or clip.text or is_video):
            return False
        clip.x = min(1.0, max(0.0, float(x)))
        clip.y = min(1.0, max(0.0, float(y)))
        clip.scale = min(2.0, max(0.02, float(scale)))
        clip.rotation = float(rotation)
        if is_video:
            clip.placed = True
        return True

    def clear_lane(self, kind: str) -> int:
        """Empty one timeline lane in a single stroke.

        ``kind`` is the LANE as the user sees it, not a raw track
        number, because two lanes share track 0: clearing "video"
        removes the A/V clips themselves (A1 empties with them);
        clearing "audio" only silences them - the same asymmetry the
        per-clip delete has. The overlay lanes ("color", "sticker",
        "text", "music") drop their clips. Returns how many clips were
        touched; 0 = nothing to do (the caller can refuse the undo
        entry).
        """
        kind = str(kind)
        if kind == "audio":
            touched = [c for c in self.timeline
                       if c.track == 0 and c.media_id and c.audio_enabled]
            for clip in touched:
                clip.audio_enabled = False
            return len(touched)
        tracks = {"video": 0, "color": self.COLOR_TRACK,
                  "sticker": self.STICKER_TRACK, "text": self.TEXT_TRACK,
                  "music": self.MUSIC_TRACK}
        if kind not in tracks:
            return 0
        track = tracks[kind]
        touched = [c for c in self.timeline if c.track == track]
        for clip in touched:
            self.timeline.remove(clip)
        return len(touched)

    def set_clip_crop(self, clip_id: str, left: float, top: float,
                      right: float, bottom: float) -> bool:
        """Crop an A/V clip's picture by edge insets (source fractions)."""
        clip = self.find_clip(clip_id)
        if clip is None or not clip.media_id or clip.track != 0:
            return False
        clip.crop = _clean_crop({"left": left, "top": top,
                                 "right": right, "bottom": bottom})
        return True

    def set_clip_opacity(self, clip_id: str, opacity: float) -> bool:
        """Fade an A/V clip towards what sits underneath it."""
        clip = self.find_clip(clip_id)
        if clip is None or not clip.media_id or clip.track != 0:
            return False
        clip.opacity = min(1.0, max(0.0, float(opacity)))
        return True

    def set_clip_keyframe(self, clip_id: str, t: float,
                          values: dict) -> bool:
        """Pin transform/opacity values at clip-local ``t`` seconds.

        A diamond already standing there is replaced. Pinning any
        TRANSFORM parameter turns free placement on - an animated
        position only means something on a floating clip.
        """
        from ive.utils.keyframes import upsert

        clip = self.find_clip(clip_id)
        if clip is None or not clip.media_id or clip.track != 0:
            return False
        allowed = {k: float(v) for k, v in (values or {}).items()
                   if k in ("x", "y", "scale", "rotation", "opacity")}
        if not allowed or not (0.0 <= float(t) <= clip.duration + 1e-6):
            return False
        easing = str((values or {}).get("easing") or "")
        if easing:
            allowed["easing"] = easing
        clip.keyframes = upsert(clip.keyframes, float(t), allowed)
        if any(k in allowed for k in ("x", "y", "scale", "rotation")):
            clip.placed = True
        return True

    def set_keyframe_easing(self, clip_id: str, t: float,
                            easing: str) -> bool:
        """Give the diamond at clip-local ``t`` its travel character.

        The easing describes how the values ARRIVE at that pin
        (utils/keyframes.py). Only a diamond that exists can take one.
        """
        from ive.utils.keyframes import EASINGS, keyframe_at

        clip = self.find_clip(clip_id)
        if clip is None or str(easing) not in EASINGS:
            return False
        standing = keyframe_at(clip.keyframes, float(t))
        if standing is None:
            return False
        if str(easing) == "linear":
            standing.pop("easing", None)   # linear is the unmarked default
        else:
            standing["easing"] = str(easing)
        return True

    def remove_clip_keyframe(self, clip_id: str, t: float) -> bool:
        """Take the diamond at clip-local ``t`` away, values and all."""
        from ive.utils.keyframes import remove_at

        clip = self.find_clip(clip_id)
        if clip is None:
            return False
        kept = remove_at(clip.keyframes, float(t))
        if kept is None:
            return False
        clip.keyframes = kept
        return True

    def reset_clip_transform(self, clip_id: str) -> bool:
        """Hand a placed A/V clip back to the project's canvas fit.

        The transform keyframes go with it: an animated position on a
        clip that no longer floats would just re-place it at the first
        frame. One Ctrl+Z brings placement and diamonds back together.
        """
        clip = self.find_clip(clip_id)
        if clip is None or not clip.placed:
            return False
        clip.placed = False
        clip.x, clip.y = 0.5, 0.5
        clip.scale, clip.rotation = 0.3, 0.0
        clip.keyframes = []
        return True

    def set_clip_transition(self, clip_id: str, transition_id: str,
                            duration: float = 0.5,
                            edge: str = "out") -> bool:
        """Set (or clear, with "") a transition on one clip.

        ``edge`` "out" dresses the cut towards what follows (the next
        clip, or black when this is the last one); "in" dresses the
        clip's head - the intro from black, read on the first clip.
        Only the A/V track has cuts to dress; the timeline reflows so a
        next clip slides back by the overlap.
        """
        clip = self.find_clip(clip_id)
        if clip is None or clip.track != 0:
            return False
        duration = min(5.0, max(0.1, float(duration)))
        if edge == "in":
            clip.transition_in_id = str(transition_id)
            clip.transition_in_duration = duration
        else:
            clip.transition_id = str(transition_id)
            clip.transition_duration = duration
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

    def remove_clips(self, clip_ids) -> int:
        """Remove several clips at once; one reflow at the end."""
        wanted = {str(i) for i in clip_ids}
        before = len(self.timeline)
        self.timeline = [c for c in self.timeline if c.id not in wanted]
        removed = before - len(self.timeline)
        if removed:
            self.reflow()
        return removed

    def paste_clips(self, documents: list, at: float) -> list:
        """Recreate copied clips from ``at``, keeping their spacing.

        Each document is a ``TimelineClip.to_dict()`` snapshot; every
        pasted clip gets a FRESH id (a paste is a new clip, never an
        alias). The earliest copied start becomes ``at`` and the others
        keep their distance from it, so a copied arrangement lands as
        the same arrangement. Track 0 reflows: there the paste point is
        an insertion point, like a drop.
        """
        if not documents:
            return []
        base = min(float(d.get("start") or 0.0) for d in documents)
        at = max(0.0, float(at))
        pasted = []
        for document in documents:
            clip = TimelineClip.from_dict(document)
            clip.id = _new_id()
            clip.start = at + (float(document.get("start") or 0.0) - base)
            self.timeline.append(clip)
            pasted.append(clip)
        if any(c.track == 0 for c in pasted):
            self.reflow(0)
        return pasted

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
            # `offset` is TIMELINE seconds; the source advances at the
            # clip's own pace.
            source_in=clip.source_in + offset * clip.speed,
            speed=clip.speed,
            volume=clip.volume,
            audio_enabled=clip.audio_enabled,
            muted=clip.muted,
            audio_effect_id=clip.audio_effect_id,
            duck=clip.duck, duck_db=clip.duck_db,
            # The fade-out belongs to the tail, the fade-in to the head.
            fade_out=clip.fade_out,
            effect_id=clip.effect_id,
            # Overlay clips keep what they are and where they sit: a split
            # title must show the same words at the same place on both sides.
            sticker_id=clip.sticker_id,
            text=clip.text, font=clip.font, color=clip.color,
            outline=clip.outline, bold=clip.bold, italic=clip.italic,
            motion_id=clip.motion_id,
            x=clip.x, y=clip.y, scale=clip.scale, rotation=clip.rotation,
            # The transition OUT belongs to the tail: after a split it is
            # the second half that meets the next clip.
            transition_id=clip.transition_id,
            transition_duration=clip.transition_duration,
        )
        clip.duration = offset
        clip.fade_out = 0.0
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

    def set_clip_audio_effect(self, clip_id: str, effect_id: str) -> bool:
        clip = self.find_clip(clip_id)
        if clip is None:
            return False
        clip.audio_effect_id = str(effect_id)
        return True

    def set_clip_ducking(self, clip_id: str, enabled: bool,
                         depth_db: float) -> bool:
        clip = self.find_clip(clip_id)
        if clip is None:
            return False
        clip.duck = bool(enabled)
        clip.duck_db = min(30.0, max(0.0, float(depth_db)))
        return True

    def set_clip_fades(self, clip_id: str, fade_in: float,
                       fade_out: float) -> bool:
        """Head and tail audio fades, clamped so they never cross."""
        clip = self.find_clip(clip_id)
        if clip is None:
            return False
        half = max(0.0, clip.duration / 2.0)
        clip.fade_in = min(half, max(0.0, float(fade_in)))
        clip.fade_out = min(half, max(0.0, float(fade_out)))
        return True

    def trim_clip(self, clip_id: str, source_in: float, duration: float,
                  start: float | None = None) -> bool:
        """Resize a clip: new head offset into the source, new length.

        Clamped against the SOURCE: a clip can never show material the file
        does not have (head before 0, tail past the media duration), and
        never collapses below a tenth of a second. The timeline reflows, so
        neighbours close up around the new size.

        ``start`` matters on the FREE lanes (colour, sticker, text, music):
        a head trim there must move the left edge, not the right one -
        without it the clip keeps its start and shrinks from the tail,
        which is the other handle's job. On track 0 the reflow decides
        every start, so the value is accepted and then overruled.
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
            # `duration` is TIMELINE seconds; the source is consumed at
            # the clip's pace, so the ceiling scales with the speed.
            duration = min(duration, (limit - source_in) / clip.speed)
        clip.source_in = source_in
        clip.duration = duration
        if start is not None:
            clip.start = max(0.0, float(start))
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
