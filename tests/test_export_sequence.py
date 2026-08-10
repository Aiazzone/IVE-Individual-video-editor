"""Does export render the whole SEQUENCE, or just one clip?

It used to render one clip and call it the project. Now it walks the same
graph the preview pulls (docs/ENGINE.md 3), so what you watched is what you
get - and with `use_proxies=False`, from the originals.

Checked by what comes out: the rendered file must be as long as the timeline,
not as long as its first clip.

    python tests/test_export_sequence.py [a.mp4 b.mp4]
"""

from __future__ import annotations

import sys
import time
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

    from ive.export.service import ExportService
    from ive.media.probe import probe
    from ive.playback.transport import PlaybackService

    EACH = 1.0
    clips = [{"path": str(p), "start": EACH * i, "duration": EACH,
              "sourceIn": 0.0} for i, p in enumerate(files[:2])]
    expected = EACH * len(clips)
    print(f"\nTimeline: {len(clips)} clips x {EACH}s = {expected}s")

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    playback = PlaybackService()
    playback.open_sequence(clips)
    check(bool(playback.isSequence), "the transport holds a sequence")
    check(len(playback.sequence_clips()) == len(clips),
          f"the sequence is handed out for export "
          f"({len(playback.sequence_clips())} clips)")

    export = ExportService(playback=playback)
    out = ROOT / "tests" / "output" / "sequence_export.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    state: dict = {}
    export.completed.connect(lambda p: state.__setitem__("done", p))
    export.failed.connect(lambda m: state.__setitem__("error", m))

    started = export.start(str(files[0]), str(out), {
        "width": 640, "height": 360, "video_codec": "h264",
        "container": "mp4", "video_bitrate_kbps": 4000,
    })
    check(bool(started), "the export started")

    deadline = time.monotonic() + 120
    while "done" not in state and "error" not in state:
        app.processEvents()
        if time.monotonic() > deadline:
            break
        time.sleep(0.05)

    export.shutdown()
    playback.shutdown()

    if "error" in state:
        print(f"  export failed: {state['error']}")
        check(False, "the export completed")
        return 1
    check("done" in state, "the export completed")

    if out.is_file():
        info = probe(out)
        print(f"  rendered {out.name}: {info.duration:.2f}s")
        # One clip would be ~1s; the sequence is ~2s. Half a frame of slack.
        check(abs(info.duration - expected) < 0.25,
              f"the file is as long as the TIMELINE, not as its first clip "
              f"({info.duration:.2f}s vs {expected:.2f}s expected)")
    else:
        check(False, "an output file was produced")

    failed = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    for message in failed:
        print("  -", message)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
