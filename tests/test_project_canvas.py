"""Does the sequence composite at the PROJECT's canvas, not the first clip's?

A canvas that follows whichever clip happens to be first changes under the
user when the timeline is reordered, and silently reframes everything else.
So the project chooses, and every clip is letterboxed into that choice - bars
included, because bars are the honest result of putting a 16:9 clip in a 9:16
project, and the user picked the project.

    python tests/test_project_canvas.py [video.mp4]
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


class _Settings:
    """Just enough of the settings service to choose a canvas."""

    def __init__(self, canvas: str) -> None:
        self.values = {"project.canvas": canvas, "media.preview_height": 720}

    def get(self, key, default=None):
        return self.values.get(key, default)


def main() -> int:
    files = [Path(a) for a in sys.argv[1:] if Path(a).is_file()]
    if not files:
        files = sorted(ROOT.glob("*.mp4"))[:1]
    if not files:
        print("Need a sample video.")
        return 2
    sample = files[0]

    from PySide6.QtCore import QCoreApplication

    from ive.media.probe import probe
    from ive.playback.transport import PlaybackService

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    native = probe(sample).primary_video.display_size
    print(f"\nSource: {sample.name} {native[0]}x{native[1]}")

    for name, expected in (("16:9", 16 / 9), ("9:16", 9 / 16), ("1:1", 1.0)):
        service = PlaybackService(settings=_Settings(name))
        service.open(sample)
        width, height = service._preview_size
        ratio = width / height
        print(f"  canvas {name:>5}: composites at {width}x{height} "
              f"(ratio {ratio:.3f})")
        check(abs(ratio - expected) < 0.02,
              f"canvas {name} composites at that ratio ({ratio:.3f})")
        check(abs(service.aspect - expected) < 0.02,
              f"canvas {name} is what the VIEW is told to frame "
              f"({service.aspect:.3f})")

        # Only ONE thread may pull on the graph: suspend the read-ahead
        # before touching it from here, or PyAV raises "generator already
        # executing" - the same trap the transport documents.
        service._reader.suspend_stream()
        frame = service._produce(1)
        if frame is not None:
            shape = frame[1].shape
            check((shape[1], shape[0]) == (width, height),
                  f"a produced frame IS the canvas ({shape[1]}x{shape[0]})")
        else:
            check(False, "a frame was produced")
        service.shutdown()

    # "auto" keeps the old behaviour: the first clip decides.
    service = PlaybackService(settings=_Settings("auto"))
    service.open(sample)
    check(abs(service.aspect - native[0] / native[1]) < 0.02,
          f"'auto' still follows the first clip ({service.aspect:.3f})")
    service.shutdown()

    failed = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    for message in failed:
        print("  -", message)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
