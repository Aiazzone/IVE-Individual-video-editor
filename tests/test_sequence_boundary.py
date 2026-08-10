"""Does playback carry on when one clip ends and the next begins?

It did not. The read-ahead read "this frame has no picture" as "the stream is
over" and stopped producing for good, so the preview froze on the last picture
of the first clip while the playhead kept moving. A frame with no picture is a
hole in the middle of a sequence, not its end - where the end is was already
known, from the length handed to start().

The test plays across a real cut and checks that pictures keep arriving on
BOTH sides of it.

    python tests/test_sequence_boundary.py [a.mp4 b.mp4]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ive" / "src"))

results: list[tuple[bool, str]] = []


def check(condition: bool, message: str) -> None:
    results.append((bool(condition), message))
    print(f"  {'OK  ' if condition else 'FAIL'}  {message}")


def main() -> int:
    files = [Path(a) for a in sys.argv[1:] if Path(a).is_file()]
    if len(files) < 2:
        files = sorted(ROOT.glob("*.mp4"))[:2]
    if len(files) < 2:
        print("Need two sample videos.")
        return 2

    from PySide6.QtCore import QCoreApplication, QTimer

    from ive.playback.transport import PlaybackService

    print(f"\nClips: {files[0].name} -> {files[1].name}")
    # Deliberately different aspect ratios if the samples allow it: the cut is
    # where the canvas letterboxing changes, which is where it broke.
    CUT = 1.5
    clips = [{"path": str(files[0]), "start": 0.0, "duration": CUT,
              "sourceIn": 0.0},
             {"path": str(files[1]), "start": CUT, "duration": 1.5,
              "sourceIn": 0.0}]

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    service = PlaybackService()
    if not service.open_sequence(clips):
        print("Could not build the sequence.")
        return 1

    counts = {"before": 0, "after": 0}
    state = {"phase": "before"}
    service.frameImage.connect(
        lambda _img: counts.__setitem__(state["phase"],
                                        counts[state["phase"]] + 1))

    def start():
        service.seek_seconds(CUT - 0.7)
        service.play()

    def cross():
        state["phase"] = "after"

    def finish():
        state["position"] = service.positionSeconds
        service.pause()
        service.shutdown()
        app.quit()

    QTimer.singleShot(0, start)
    QTimer.singleShot(900, cross)        # by now the cut has been passed
    QTimer.singleShot(2100, finish)
    app.exec()

    print(f"\n  pictures before the cut: {counts['before']}")
    print(f"  pictures after the cut:  {counts['after']}")
    print(f"  playhead ended at {state['position']:.2f}s (cut at {CUT:.2f}s)")

    check(counts["before"] > 5, f"the first clip plays ({counts['before']})")
    check(counts["after"] > 5,
          f"playback CONTINUES into the second clip ({counts['after']} "
          f"pictures after the cut)")
    check(state["position"] > CUT,
          f"the playhead passed the cut ({state['position']:.2f} > {CUT})")

    failed = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    for message in failed:
        print("  -", message)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
