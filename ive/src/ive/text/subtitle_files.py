"""Subtitle files: SRT and WebVTT, both directions, no dependencies.

Lines travel as ``[{"start", "end", "text"}, ...]`` in seconds - the
same shape the automatic subtitles produce and ``place_subtitles``
consumes, so a parsed file and a transcription are indistinguishable
downstream. Writing picks the dialect from the caller (the UI infers it
from the extension); parsing detects it from the content, because users
rename files.

Parsing is deliberately tolerant: BOM, CRLF, missing indices, hour-less
VTT timestamps, styling tags (``<i>``, ``{\\an8}``) - real files have
all of it. What cannot be read as a cue is skipped, never fatal: a
subtitle file with one broken cue is a file with N-1 good ones.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

__all__ = ["format_srt", "format_vtt", "parse_subtitles"]

#: "HH:MM:SS,mmm" (SRT) or "[HH:]MM:SS.mmm" (VTT); both separators are
#: accepted everywhere because files in the wild mix them.
_TIME = re.compile(
    r"(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})")
_ARROW = re.compile(
    r"(?P<a>[\d:.,]+)\s*-->\s*(?P<b>[\d:.,]+)")
#: <i>, </font>, {\an8} and friends: styling, not words.
_TAGS = re.compile(r"<[^>]+>|\{\\[^}]*\}")


def _parse_time(value: str) -> float | None:
    match = _TIME.fullmatch(value.strip())
    if match is None:
        return None
    hours = int(match.group(1) or 0)
    millis = int(match.group(4).ljust(3, "0"))
    return (hours * 3600 + int(match.group(2)) * 60
            + int(match.group(3)) + millis / 1000.0)


def _stamp(seconds: float, decimal: str) -> str:
    total = max(0, int(round(float(seconds) * 1000)))
    hours, rest = divmod(total, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal}{millis:03d}"


def format_srt(lines: list[dict]) -> str:
    """The classic dialect: index, comma timestamps, blank-line cues."""
    out = []
    for index, line in enumerate(sorted(lines, key=lambda l: l["start"]), 1):
        out.append(f"{index}\n"
                   f"{_stamp(line['start'], ',')} --> "
                   f"{_stamp(line['end'], ',')}\n"
                   f"{str(line['text']).strip()}\n")
    return "\n".join(out)


def format_vtt(lines: list[dict]) -> str:
    """WebVTT: the same cues with a header and dot timestamps."""
    out = ["WEBVTT\n"]
    for line in sorted(lines, key=lambda l: l["start"]):
        out.append(f"{_stamp(line['start'], '.')} --> "
                   f"{_stamp(line['end'], '.')}\n"
                   f"{str(line['text']).strip()}\n")
    return "\n".join(out)


def parse_subtitles(content: str) -> list[dict]:
    """Cues out of SRT or VTT text, sorted, tags stripped.

    Anything that does not read as a cue (headers, NOTE blocks, broken
    timestamps) is skipped with a debug line. Returns ``[]`` for a file
    with nothing readable - the caller decides whether that is an error.
    """
    text = content.lstrip("﻿")
    lines_out: list[dict] = []
    for block in re.split(r"\r?\n\s*\r?\n", text):
        rows = [r.strip("\r") for r in block.strip().split("\n")]
        arrow_at = next((i for i, r in enumerate(rows)
                         if _ARROW.search(r)), None)
        if arrow_at is None:
            continue                       # header, NOTE, numbering junk
        match = _ARROW.search(rows[arrow_at])
        start = _parse_time(match.group("a"))
        end = _parse_time(match.group("b"))
        if start is None or end is None or end <= start:
            log.debug("Unreadable cue timing skipped: %r", rows[arrow_at])
            continue
        body = "\n".join(rows[arrow_at + 1:]).strip()
        body = _TAGS.sub("", body).strip()
        if body:
            lines_out.append({"start": start, "end": end, "text": body})
    lines_out.sort(key=lambda l: l["start"])
    return lines_out
