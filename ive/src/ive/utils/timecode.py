"""Frame rates, frame counts and SMPTE timecode.

The sequence runs on a frame grid: a cut, a clip edge or a fade can only
fall ON a frame, never between two. This module is the one place that
knows the grid - the model snaps to it, the file stores frame counts on
it, the transport formats it - so the three can never disagree by the
rounding of a float.

Rates are ``Fraction``s, never floats: 29.97 is ``30000/1001`` exactly,
and a float of it multiplied by an hour of frames is off by enough to
land a cut on the neighbour frame.

**Drop-frame.** At 29.97 a timecode that counts 30 frames per second
runs 3.6 s per hour slower than the wall clock: after one real hour it
reads 00:59:56;12. SMPTE drop-frame skips frame NUMBERS 00 and 01 at the
start of every minute except each tenth (four numbers at 59.94), so the
timecode stays on the clock. No picture is dropped, only labels; the
separator before the frames turns into ``;`` to say so.
"""

from __future__ import annotations

import math
from fractions import Fraction

__all__ = ["DEFAULT_RATE", "COMMON_RATES", "parse_rate", "rate_to_str",
           "rate_label", "to_frames", "to_seconds", "snap", "frame_seconds",
           "is_drop_frame", "nominal_rate", "format_timecode",
           "parse_timecode"]

DEFAULT_RATE = Fraction(25, 1)

#: The rates offered for a project, in display order.
COMMON_RATES = (Fraction(24000, 1001), Fraction(24), Fraction(25),
                Fraction(30000, 1001), Fraction(30), Fraction(50),
                Fraction(60000, 1001), Fraction(60))

#: The NTSC family: n * 1000/1001. A probe reports 29.97002997...; these
#: are what it means.
_NTSC = tuple(Fraction(n * 1000, 1001) for n in (24, 30, 48, 60, 120))


def parse_rate(value, default: Fraction | None = DEFAULT_RATE
               ) -> Fraction | None:
    """Any spelling of a frame rate -> an exact ``Fraction``.

    Accepts a Fraction, an int/float (``29.97``, ``29.97002997``) or a
    string (``"30000/1001"``, ``"25"``, ``"29.97"``). Near-NTSC values
    snap to n*1000/1001; anything else keeps at most a 1001 denominator.
    Nonsense (<= 0, > 1000, unparsable) returns ``default``.
    """
    if value is None or value == "":
        return default
    try:
        if isinstance(value, Fraction):
            rate = value
        elif isinstance(value, str) and "/" in value:
            num, den = value.split("/", 1)
            rate = Fraction(int(num.strip()), int(den.strip()))
        else:
            rate = Fraction(float(value))
    except (ValueError, ZeroDivisionError, TypeError, OverflowError):
        return default
    if not (0 < rate <= 1000):
        return default
    for ntsc in _NTSC:
        if abs(float(rate) - float(ntsc)) < 0.006:
            return ntsc
    rate = rate.limit_denominator(1001)
    return rate if rate > 0 else default


def rate_to_str(rate: Fraction) -> str:
    """``"30000/1001"`` / ``"25"``: exact and parseable back."""
    rate = Fraction(rate)
    if rate.denominator == 1:
        return str(rate.numerator)
    return f"{rate.numerator}/{rate.denominator}"


def rate_label(rate: Fraction) -> str:
    """What a person reads: ``29.97``, ``23.976``, ``25``."""
    rate = Fraction(rate)
    if rate.denominator == 1:
        return str(rate.numerator)
    text = f"{float(rate):.3f}".rstrip("0").rstrip(".")
    return text


def to_frames(seconds: float, rate: Fraction) -> int:
    """The frame a time falls on: the NEAREST one, a tie going FORWARD.

    Ties are common, not rare: 0.5 s and 1.5 s sit exactly between two
    frames at 25 fps. Python's round() sends them to the EVEN frame -
    1.5 s forward, 2.5 s back - which reads as random; half-up is the
    same rule everywhere.
    """
    return int(math.floor(float(seconds) * float(rate) + 0.5))


def to_seconds(frames: int, rate: Fraction) -> float:
    """Where frame ``frames`` starts, in seconds."""
    return float(Fraction(int(frames)) / Fraction(rate))


def snap(seconds: float, rate: Fraction) -> float:
    """``seconds`` moved onto the frame grid.

    Idempotent and stable: ``to_frames(snap(s))`` is the frame ``s`` was
    nearest to, for any timeline length a person can edit.
    """
    return to_seconds(to_frames(seconds, rate), rate)


def frame_seconds(rate: Fraction) -> float:
    """The length of one frame, in seconds."""
    return float(1 / Fraction(rate))


def nominal_rate(rate: Fraction) -> int:
    """The frames-per-second a timecode COUNTS: 30 for 29.97."""
    return max(1, int(round(float(rate))))


def is_drop_frame(rate: Fraction) -> bool:
    """29.97 and 59.94 are labelled drop-frame by convention."""
    rate = Fraction(rate)
    return rate in (Fraction(30000, 1001), Fraction(60000, 1001))


def _dropped_per_minute(rate: Fraction) -> int:
    return 2 * nominal_rate(rate) // 30


def format_timecode(frame: int, rate: Fraction,
                    drop: bool | None = None) -> str:
    """``HH:MM:SS:FF`` (``HH:MM:SS;FF`` drop-frame) for a frame index.

    ``drop`` None = the convention of the rate (see ``is_drop_frame``).
    """
    rate = Fraction(rate)
    fps = nominal_rate(rate)
    frame = max(0, int(frame))
    if drop is None:
        drop = is_drop_frame(rate)
    drop = bool(drop) and is_drop_frame(rate)
    if drop:
        dropped = _dropped_per_minute(rate)
        per_ten = fps * 600 - dropped * 9
        per_minute = fps * 60 - dropped
        tens, rest = divmod(frame, per_ten)
        frame += dropped * 9 * tens
        if rest > dropped:
            frame += dropped * ((rest - dropped) // per_minute)
    seconds, ff = divmod(frame, fps)
    sep = ";" if drop else ":"
    return (f"{seconds // 3600:02d}:{(seconds // 60) % 60:02d}:"
            f"{seconds % 60:02d}{sep}{ff:02d}")


def parse_timecode(text: str, rate: Fraction) -> int:
    """``HH:MM:SS:FF`` / ``HH:MM:SS;FF`` -> frame index.

    Fewer fields count from the right (``SS:FF``, ``MM:SS:FF``). A ``;``
    anywhere reads it as drop-frame (only meaningful at 29.97/59.94).
    Raises ``ValueError`` on anything else, including a frame field at
    or past the rate and a drop-frame label that does not exist.
    """
    rate = Fraction(rate)
    raw = str(text).strip()
    drop = ";" in raw and is_drop_frame(rate)
    parts = raw.replace(";", ":").replace(".", ":").split(":")
    if not 1 <= len(parts) <= 4 or not all(p.strip().isdigit() for p in parts):
        raise ValueError(f"Not a timecode: {text!r}")
    values = [int(p) for p in parts]
    values = [0] * (4 - len(values)) + values
    hh, mm, ss, ff = values
    fps = nominal_rate(rate)
    if ff >= fps or ss >= 60 or mm >= 60:
        raise ValueError(f"Field out of range: {text!r}")
    total = ((hh * 60 + mm) * 60 + ss) * fps + ff
    if drop:
        dropped = _dropped_per_minute(rate)
        if ss == 0 and ff < dropped and mm % 10 != 0:
            raise ValueError(f"Drop-frame label does not exist: {text!r}")
        minutes = hh * 60 + mm
        total -= dropped * (minutes - minutes // 10)
    return total
