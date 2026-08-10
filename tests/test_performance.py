"""Where does the time go during playback?

Stuttering playback is always a budget problem, and a budget cannot be guessed
at. This measures each stage separately, so the culprit is a number rather
than a hunch.

The reference is the frame interval: at 25 fps a frame must be produced in
under 40 ms, and everything else on the machine has to fit in what is left.

    python tests/test_performance.py [path/to/video.mp4]
"""

from __future__ import annotations

import statistics
import sys
import time
from fractions import Fraction
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ive" / "src"))

from ive.engine.builder import build_from_project        # noqa: E402
from ive.engine.consumer import PullConsumer             # noqa: E402
from ive.engine.frame import AudioFormat, Timebase       # noqa: E402
from ive.engine.producer import ClipProducer             # noqa: E402
from ive.media.decoder import VideoDecoder               # noqa: E402
from ive.media.probe import probe                        # noqa: E402


def timeit(label: str, fn, count: int, budget_ms: float | None = None):
    """Run ``fn`` ``count`` times and report the distribution."""
    samples = []
    for i in range(count):
        start = time.perf_counter()
        fn(i)
        samples.append((time.perf_counter() - start) * 1000.0)
    samples.sort()
    median = statistics.median(samples)
    worst = samples[-1]
    p95 = samples[int(len(samples) * 0.95) - 1]
    verdict = ""
    if budget_ms is not None:
        verdict = "  OK" if p95 <= budget_ms else "  OVER BUDGET"
    print(f"  {label:<44} median {median:6.1f} ms   p95 {p95:6.1f} ms"
          f"   worst {worst:6.1f} ms{verdict}")
    return median, p95


def find_sample() -> Path | None:
    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1])
        if candidate.is_file():
            return candidate
    for pattern in ("_shots/multi/*.mp4", "_shots/*.mp4",
                    "ive/assets/backgrounds/*.mp4"):
        found = sorted(ROOT.glob(pattern))
        if found:
            return found[0]
    return None


def main() -> int:
    sample = find_sample()
    if sample is None:
        print("No sample media found. Pass a video path as an argument.")
        return 2

    info = probe(sample)
    video = info.primary_video
    fps = float(video.fps) if video else 25.0
    budget = 1000.0 / fps
    width, height = video.display_size if video else (1920, 1080)

    print(f"\nSample: {sample.name}  {width}x{height}  {fps:.3f} fps  "
          f"{info.duration:.1f}s  audio={'yes' if info.has_audio else 'no'}")
    print(f"Frame budget at {fps:.0f} fps: {budget:.1f} ms\n")

    # ── 1. the decoder alone ──────────────────────────────────────────
    print("1. Decoder, sequential (the fast path)")
    decoder = VideoDecoder(sample)
    decoder.frame_at(0)
    timeit("decode next frame", lambda i: decoder.frame_at(i + 1),
           min(60, decoder.frame_count - 2), budget)

    print("\n2. Decoder, random access (scrubbing)")
    total = decoder.frame_count
    timeit("seek + decode", lambda i: decoder.frame_at((i * 37) % total),
           min(25, total), budget * 3)
    decoder.close()

    # ── 3. through the graph ──────────────────────────────────────────
    print("\n3. Through the graph (producer -> playlist -> tractor)")
    clips = [{"path": str(sample.resolve()), "start": 0.0,
              "duration": info.duration, "id": "c"}]
    tractor = build_from_project(clips, fps=fps, width=width, height=height)

    video_only = PullConsumer(tractor, want_image=True, want_audio=False)
    timeit("pull frame, picture only", lambda i: video_only.pull(i),
           min(60, tractor.length - 1), budget)

    both = PullConsumer(tractor, want_image=True, want_audio=True)
    timeit("pull frame, picture + sound", lambda i: both.pull(i),
           min(60, tractor.length - 1), budget)

    audio_only = PullConsumer(tractor, want_image=False, want_audio=True)
    timeit("pull frame, sound only", lambda i: audio_only.pull(i),
           min(60, tractor.length - 1), budget)
    tractor.close()

    # ── 4. what the compositor costs ──────────────────────────────────
    print("\n4. Compositing cost at sequence size")
    from ive.engine.producer import ColourProducer
    from ive.engine.tractor import Track, Tractor

    tb = Timebase(Fraction(fps).limit_denominator(1001))
    big = Tractor(tb, AudioFormat(), width, height)
    big.add_track(Track(ColourProducer(width, height, 100, tb, (0, 0, 0))))
    big.add_track(Track(ColourProducer(width, height, 100, tb, (10, 20, 30))))
    one = PullConsumer(big)
    timeit(f"two full tracks at {width}x{height}", lambda i: one.pull(i % 100),
           40, budget)

    over = big.tracks[1]
    over.opacity = 0.5
    timeit("same, with a blend (opacity 0.5)", lambda i: one.pull(i % 100),
           40, budget)

    # scaling: a track whose size differs from the sequence
    mismatched = Tractor(tb, AudioFormat(), width, height)
    mismatched.add_track(Track(ColourProducer(width, height, 100, tb, (0, 0, 0))))
    mismatched.add_track(Track(ColourProducer(width // 2, height // 2, 100, tb,
                                              (10, 20, 30))))
    two = PullConsumer(mismatched)
    timeit("with a track needing scaling (letterbox)",
           lambda i: two.pull(i % 100), 40, budget)

    # ── 5. QImage conversion, which happens per delivered frame ───────
    print("\n5. Handing the frame to Qt")
    try:
        from PySide6.QtGui import QGuiApplication, QImage  # noqa: F401

        app = QGuiApplication.instance() or QGuiApplication([])
        array = np.zeros((height, width, 3), np.uint8)

        from ive.media.reader import _to_qimage

        timeit("numpy -> QImage (includes the mandatory copy)",
               lambda i: _to_qimage(array), 40, budget)
    except Exception as exc:
        print(f"  skipped ({exc})")

    print("\nRead it like this: any stage over its budget cannot keep up on its")
    print("own, never mind sharing the machine with the interface.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
