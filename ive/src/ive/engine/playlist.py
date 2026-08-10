"""Playlist: a track. And a playlist is itself a producer.

That single fact is what keeps the model small. A track is a producer, a
sequence is a producer, a nested sequence is a producer - no special cases
anywhere (docs/ENGINE.md §2.4).

A playlist holds entries and blanks. Blanks are explicit rather than implied
by gaps, so "there is nothing here" is a thing the model can say, and the
compositor below still has something to render.
"""

from __future__ import annotations

import logging
from bisect import bisect_right
from dataclasses import dataclass, field

from ive.engine.frame import AudioFormat, Frame, Timebase
from ive.engine.producer import Producer

log = logging.getLogger(__name__)

__all__ = ["Entry", "Playlist"]


@dataclass
class Entry:
    """One item on a track: a producer, trimmed, with its own filters."""

    producer: Producer
    #: In and out inside the SOURCE, in sequence frames.
    source_in: int = 0
    length: int = 0
    filters: list = field(default_factory=list)
    #: Set for a gap; the producer is then ignored.
    blank: bool = False
    clip_id: str = ""

    def __post_init__(self) -> None:
        if not self.length:
            self.length = max(0, self.producer.length - self.source_in) if self.producer else 0


class Playlist(Producer):
    """An ordered run of entries; positions are contiguous by construction."""

    def __init__(self, timebase: Timebase | None = None,
                 audio_format: AudioFormat | None = None,
                 name: str = "track") -> None:
        self.timebase = timebase or Timebase()
        self.audio_format = audio_format or AudioFormat()
        self.name = name
        self.entries: list[Entry] = []
        self._offsets: list[int] = []
        self.length = 0
        #: Filters applied to whatever this track produces, after the entries.
        self.filters: list = []

    # ── building ──────────────────────────────────────────────────────

    def append(self, entry: Entry) -> Entry:
        self.entries.append(entry)
        self._reindex()
        return entry

    def append_blank(self, length: int) -> Entry:
        return self.append(Entry(producer=None, length=max(0, int(length)), blank=True))

    def clear(self) -> None:
        self.entries.clear()
        self._reindex()

    def _reindex(self) -> None:
        offset = 0
        self._offsets = []
        for entry in self.entries:
            self._offsets.append(offset)
            offset += max(0, entry.length)
        self.length = offset

    def entry_at(self, position: int) -> tuple[Entry | None, int]:
        """The entry covering ``position``, and the offset inside it."""
        if not self.entries or not (0 <= position < self.length):
            return None, 0
        index = bisect_right(self._offsets, position) - 1
        index = max(0, min(index, len(self.entries) - 1))
        return self.entries[index], position - self._offsets[index]

    # ── producing ─────────────────────────────────────────────────────

    def frame_at(self, position: int) -> Frame | None:
        if not (0 <= position < self.length):
            return None

        entry, local = self.entry_at(position)
        if entry is None:
            return None

        if entry.blank or entry.producer is None:
            # A blank still produces a frame: silent, with no picture. The
            # compositor below decides what shows through.
            frame = Frame(position, self.timebase, self.audio_format)
            frame.set_audio(frame.silence())
            frame.properties["blank"] = True
            return frame

        source = entry.producer.frame_at(entry.source_in + local)
        if source is None:
            frame = Frame(position, self.timebase, self.audio_format)
            frame.set_audio(frame.silence())
            frame.properties["blank"] = True
            return frame

        # Rewrite the position to the TRACK's timeline: from here on, nothing
        # downstream should know that the clip started somewhere else.
        frame = source.derive()
        frame.position = position
        frame.properties.update(source.properties)
        frame.properties["clip_id"] = entry.clip_id

        for filt in entry.filters:
            frame = filt.process(frame)
        for filt in self.filters:
            frame = filt.process(frame)
        return frame

    def close(self) -> None:
        seen = set()
        for entry in self.entries:
            producer = entry.producer
            if producer is not None and id(producer) not in seen:
                seen.add(id(producer))
                producer.close()
