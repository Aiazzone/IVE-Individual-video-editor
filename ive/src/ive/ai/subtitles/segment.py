"""Words with timestamps -> subtitle lines a person can actually read.

Pure functions, no model, no Qt: this is the half of the subtitle
pipeline that is fully testable without downloading anything. The rules
are the classic subtitling ones (docs/AI_FEATURES.md §4): a maximum of
characters per line, a maximum duration, a minimum duration so a short
word does not flash, and a break wherever the speech itself breaks -
a long silence or a sentence end.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["SubtitleLine", "segment_words"]

#: Punctuation that ends a sentence: always a good place to break.
_STRONG = (".", "!", "?", "…")


@dataclass
class SubtitleLine:
    """One subtitle: what is said between ``start`` and ``end`` seconds."""

    start: float
    end: float
    text: str
    #: The words inside, ``[{"start", "end", "text"}, ...]`` - kept for a
    #: future karaoke/highlight mode; the timeline only needs the line.
    words: list = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start


def segment_words(words: list[dict], *,
                  max_chars: int = 42,
                  max_duration: float = 5.5,
                  min_duration: float = 0.8,
                  max_gap: float = 0.9) -> list[SubtitleLine]:
    """Group word timestamps into subtitle lines.

    ``words`` is ``[{"start": s, "end": s, "text": str}, ...]`` in
    ascending time (the transcriber's output; leading spaces in the text
    are tolerated). A new line starts when adding the word would exceed
    ``max_chars`` or ``max_duration``, when the silence before it is
    longer than ``max_gap``, or right after a sentence end. Lines
    shorter than ``min_duration`` are held on screen longer - up to the
    start of the next line - because a flash nobody can read is worse
    than a slightly lazy exit.
    """
    lines: list[SubtitleLine] = []
    current: list[dict] = []

    def flush() -> None:
        if not current:
            return
        text = " ".join(w["text"].strip() for w in current
                        if w["text"].strip())
        if text:
            lines.append(SubtitleLine(
                start=float(current[0]["start"]),
                end=float(current[-1]["end"]),
                text=text,
                words=[dict(w) for w in current]))
        current.clear()

    for word in words:
        text = str(word.get("text") or "").strip()
        if not text:
            continue
        word = {"start": float(word["start"]), "end": float(word["end"]),
                "text": text}
        if current:
            joined = sum(len(w["text"]) for w in current) + len(current)
            gap = word["start"] - current[-1]["end"]
            length = word["end"] - current[0]["start"]
            if (joined + len(word["text"]) > max_chars
                    or gap > max_gap
                    or length > max_duration
                    or current[-1]["text"].endswith(_STRONG)):
                flush()
        current.append(word)
    flush()

    # Second pass: minimum on-screen time, without ever overlapping the
    # next line (a small breath of 80 ms is kept between the two).
    for index, line in enumerate(lines):
        if line.duration >= min_duration:
            continue
        limit = (lines[index + 1].start - 0.08
                 if index + 1 < len(lines) else line.start + min_duration)
        line.end = max(line.end, min(line.start + min_duration, limit))

    return lines
