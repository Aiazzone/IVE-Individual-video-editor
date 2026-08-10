"""The export file-name field: what a typed name becomes on disk.

The field feeds `_safe_stem` in export_actions.py. What can go wrong is all
input hygiene: a typed extension doubling up ("clip.mp4" -> "clip.mp4.mp4"),
path separators escaping the chosen folder, characters Windows refuses, and
names that reduce to nothing (which must fall back to the automatic name).

    python tests/test_export_filename.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ive" / "src"))

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    print(f"  {'OK  ' if condition else 'FAIL'} {message}")
    if not condition:
        failures.append(message)


def main() -> int:
    from ive.core.actions.builtin.export_actions import _safe_stem

    cases = [
        # (typed, container, expected stem)
        ("My video", "mp4", "My video"),
        ("  My video  ", "mp4", "My video"),
        ("clip.mp4", "mp4", "clip"),                 # typed the extension
        ("clip.MP4", "mp4", "clip"),                 # any case
        ("clip.mkv", "mp4", "clip"),                 # another known container
        ("v1.2.final", "mp4", "v1.2.final"),         # dots, not a file type
        ("archive.backup2026", "mp4", "archive.backup2026"),  # kept whole
        ("a/b\\c", "mp4", "abc"),                    # separators removed
        ('bad<>:"|?*name', "mp4", "badname"),        # forbidden characters
        ("name...", "mp4", "name"),                  # Windows: no dot tail
        ("", "mp4", ""),                             # empty -> automatic
        ("   ", "mp4", ""),
        ("???", "mp4", ""),                          # reduces to nothing
        (".mp4", "mp4", ""),                         # only an extension
    ]
    for typed, container, expected in cases:
        got = _safe_stem(typed, container)
        check(got == expected, f"{typed!r} -> {got!r} (expected {expected!r})")

    print(f"\n{'PASS' if not failures else 'FAIL'} ({len(failures)} problem(s))")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
