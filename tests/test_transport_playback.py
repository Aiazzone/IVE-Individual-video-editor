"""Does the real transport keep up now?

tests/test_playback_pacing.py compares two playback *models* on a bare
decoder. This one drives the actual PlaybackService, with its Qt timer, its
worker thread and its read-ahead, and counts the frames that reach the screen.

It checks three things:

* frames arrive at roughly the source rate, not a fraction of it;
* the decoder stays on its sequential fast path (seeks are counted through
  VideoDecoder itself);
* seeking while playing still lands, and playback carries on from there.

    python tests/test_transport_playback.py [path/to/video.mp4]
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
    if len(sys.argv) > 1:
        sample = Path(sys.argv[1])
    else:
        candidates = sorted(ROOT.glob("*.mp4"))
        sample = candidates[0] if candidates else None
    if sample is None or not sample.is_file():
        print("No sample found. Pass a video file as an argument.")
        return 2

    from PySide6.QtCore import QCoreApplication, QElapsedTimer, QTimer

    from ive.media import decoder as decoder_module
    from ive.media.probe import probe
    from ive.playback.transport import PlaybackService

    # Count seeks by wrapping the decoder's own seek path.
    seeks = {"n": 0}
    original_seek = decoder_module.VideoDecoder._seek_and_decode

    def counting_seek(self, index):
        seeks["n"] += 1
        return original_seek(self, index)

    decoder_module.VideoDecoder._seek_and_decode = counting_seek

    info = probe(sample)
    fps = float(info.primary_video.fps) or 25.0
    width, height = info.primary_video.display_size
    print(f"\nSource: {sample.name}  {width}x{height}  {fps:.2f} fps")

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    service = PlaybackService()
    if not service.open(sample):
        print("Could not open the sample.")
        return 1

    delivered = {"n": 0}
    service.frameImage.connect(lambda _img: delivered.__setitem__("n", delivered["n"] + 1))

    PLAY_MS = 3000
    clock = QElapsedTimer()
    state: dict = {}

    def start():
        seeks["n"] = 0
        delivered["n"] = 0
        clock.restart()
        service.play()

    def midpoint():
        # Measure the steady stretch BEFORE touching anything. The transport
        # holds the clock while the read-ahead primes, so frames-per-second-of
        # -wall-clock understates it; frames per second of MEDIA played is the
        # honest number, and the one that describes what the eye sees.
        state["frames"] = delivered["n"]
        state["media"] = service.positionSeconds
        state["seeks"] = seeks["n"]
        state["before_seek"] = delivered["n"]
        service.seek_seconds(min(1.0, service.durationSeconds / 2))

    def finish():
        state["elapsed"] = clock.elapsed() / 1000.0
        state["position"] = service.positionSeconds
        service.pause()
        service.shutdown()
        app.quit()

    QTimer.singleShot(0, start)
    QTimer.singleShot(PLAY_MS // 2, midpoint)
    QTimer.singleShot(PLAY_MS, finish)
    app.exec()

    media = state.get("media") or 0.0
    achieved = state["frames"] / media if media else 0.0
    expected = media * fps
    print(f"\n  steady stretch: {state['frames']} frames for {media:.2f}s of "
          f"media ({expected:.0f} expected) -> {achieved:.1f} fps")
    print(f"  seeks: {state['seeks']}")
    print(f"  total wall time {state['elapsed']:.2f}s, "
          f"playhead ended at {state['position']:.2f}s")

    # Below 90% of the source rate the eye reads it as stutter. Before the
    # read-ahead this whole path ran at 2.1 fps out of 30.
    check(achieved >= fps * 0.90,
          f"almost every frame is shown ({state['frames']} of {expected:.0f})")
    # One seek to start playing. More means the sequential path is being lost,
    # which is the stutter cascade.
    check(state["seeks"] <= 2,
          f"the decoder stays sequential ({state['seeks']} seeks in "
          f"{state['frames']} frames)")
    check(delivered["n"] > state["before_seek"],
          "playback continues after a seek while playing")

    failed = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    for message in failed:
        print("  -", message)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
