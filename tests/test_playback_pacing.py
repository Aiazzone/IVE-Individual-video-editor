"""Why does playback stutter?

The transport asks for the frame that belongs at the current wall-clock time,
one request at a time, and only draws it once the decoder answers. Nothing is
decoded in advance.

That has a failure mode worth measuring rather than arguing about. The decoder
only has a fast path when the frame asked for is exactly the next one
(`decoder.frame_at`: `index == self._cursor + 1`). Any other index seeks. So as
soon as one frame arrives late, the clock has moved on, the next request skips
an index, the skip costs a seek, the seek is far slower than a decode, and the
next request skips further. The stutter feeds itself.

This test plays a file two ways over the same source and compares them:

* **on demand** - what the transport does today: ask at the clock, wait;
* **read ahead** - what MLT's consumer does: a producer thread decodes
  sequentially into a small queue, and the clock takes whatever is ready.

It reports late frames, skipped frames and how often the sequential fast path
was lost, which is the number that explains the feel.

    python tests/test_playback_pacing.py [path/to/video.mp4]
"""

from __future__ import annotations

import queue
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ive" / "src"))

from ive.media.decoder import VideoDecoder      # noqa: E402
from ive.media.probe import probe                # noqa: E402

#: How many frames of the file to play in each run.
FRAMES = 90
#: Read-ahead depth. MLT's consumer defaults to 25 frames.
QUEUE_DEPTH = 12

results: list[tuple[bool, str]] = []


def check(condition: bool, message: str) -> None:
    results.append((bool(condition), message))
    print(f"  {'OK  ' if condition else 'FAIL'}  {message}")


class CountingDecoder:
    """A decoder that records how often a request actually paid a seek.

    Counted by wrapping `_seek_and_decode` rather than by mirroring the fast
    path condition: the decoder now serves repeats from a cache and small
    forward jumps by decode-and-discard, so "index != cursor + 1" no longer
    means a seek happened.
    """

    def __init__(self, path: str) -> None:
        self.decoder = VideoDecoder(path)
        self.seeks = 0
        self.decodes = 0
        inner = self.decoder._seek_and_decode

        def counting(index: int):
            self.seeks += 1
            return inner(index)

        self.decoder._seek_and_decode = counting

    def frame_at(self, index: int):
        self.decodes += 1
        return self.decoder.frame_at(index)

    def close(self) -> None:
        self.decoder.close()


def play_on_demand(path: str, fps: float, frames: int) -> dict:
    """Today's transport: request at the clock, wait for the answer."""
    dec = CountingDecoder(path)
    budget = 1.0 / fps
    started = time.perf_counter()
    shown, late, skipped = 0, 0, 0
    lateness: list[float] = []
    last_index = -1

    dec.frame_at(0)          # prime, as opening the preview does
    while shown < frames:
        elapsed = time.perf_counter() - started
        target = int(elapsed / budget)
        if target >= frames:
            break
        if target == last_index:
            # Same clock slot as the last request: the decoder answers these
            # from its repeat cache for free now, so counting them as shown
            # frames would just measure how fast this loop can spin.
            time.sleep(0.001)
            continue
        if target > last_index + 1 and last_index >= 0:
            skipped += target - last_index - 1
        due = started + target * budget
        dec.frame_at(target)
        delay = time.perf_counter() - due
        lateness.append(delay * 1000.0)
        if delay > budget:
            late += 1
        last_index = target
        shown += 1

    wall = time.perf_counter() - started
    dec.close()
    return {"wall": wall, "shown": shown, "late": late, "skipped": skipped,
            "seeks": dec.seeks, "decodes": dec.decodes, "lateness": lateness}


def play_read_ahead(path: str, fps: float, frames: int) -> dict:
    """MLT's shape: a producer thread fills a queue, the clock drains it."""
    dec = CountingDecoder(path)
    budget = 1.0 / fps
    ready: queue.Queue = queue.Queue(maxsize=QUEUE_DEPTH)
    stop = threading.Event()

    def produce():
        index = 0
        while index < frames and not stop.is_set():
            try:
                frame = dec.frame_at(index)
            except Exception:
                break
            if frame is None:
                break
            while not stop.is_set():
                try:
                    ready.put((index, frame), timeout=0.1)
                    break
                except queue.Full:
                    continue
            index += 1

    thread = threading.Thread(target=produce, name="read-ahead", daemon=True)
    thread.start()

    # Hold the clock until the first frame is ready, as the transport's
    # priming does (and the on-demand run above does with its warm-up call):
    # frames produced while time is already running are late before they
    # exist, and the startup latency is not what this compares.
    while ready.empty() and thread.is_alive():
        time.sleep(0.001)

    started = time.perf_counter()
    shown, late, dropped = 0, 0, 0
    lateness: list[float] = []
    for wanted in range(frames):
        due = started + wanted * budget
        # The clock waits for its slot, exactly as a vsync-driven output does.
        now = time.perf_counter()
        if now < due:
            time.sleep(due - now)
        try:
            index, _frame = ready.get(timeout=2.0)
        except queue.Empty:
            break
        if index < wanted:
            dropped += 1        # queue lagging: this frame is already stale
        delay = time.perf_counter() - due
        lateness.append(delay * 1000.0)
        if delay > budget:
            late += 1
        shown += 1

    wall = time.perf_counter() - started
    stop.set()
    thread.join(timeout=2.0)
    dec.close()
    return {"wall": wall, "shown": shown, "late": late, "skipped": dropped,
            "seeks": dec.seeks, "decodes": dec.decodes, "lateness": lateness}


def report(label: str, run: dict, fps: float) -> None:
    lateness = run["lateness"] or [0.0]
    achieved = run["shown"] / run["wall"] if run["wall"] else 0.0
    print(f"\n  {label}")
    print(f"    {run['shown']} frames in {run['wall']:.2f}s "
          f"-> {achieved:.1f} fps (source is {fps:.1f})")
    print(f"    lateness: median {statistics.median(lateness):6.1f} ms   "
          f"worst {max(lateness):7.1f} ms")
    print(f"    late frames: {run['late']}/{run['shown']}    "
          f"skipped: {run['skipped']}")
    print(f"    decodes: {run['decodes']}   SEEKS: {run['seeks']} "
          f"({100.0 * run['seeks'] / max(1, run['decodes']):.0f}% of them)")


def main() -> int:
    if len(sys.argv) > 1:
        sample = Path(sys.argv[1])
    else:
        candidates = sorted(ROOT.glob("*.mp4"))
        sample = candidates[0] if candidates else None
    if sample is None or not sample.is_file():
        print("No sample found. Pass a video file as an argument.")
        return 2

    info = probe(sample)
    video = info.primary_video
    width, height = video.display_size
    fps = float(video.fps) or 25.0
    print(f"\nSource: {sample.name}  {width}x{height}  {fps:.2f} fps")
    print(f"Frame budget: {1000.0 / fps:.1f} ms")

    demand = play_on_demand(str(sample), fps, FRAMES)
    report("on demand (what the transport does today)", demand, fps)

    ahead = play_read_ahead(str(sample), fps, FRAMES)
    report(f"read ahead (queue of {QUEUE_DEPTH}, MLT's shape)", ahead, fps)

    print()
    check(ahead["seeks"] <= 1,
          f"read-ahead keeps the sequential fast path "
          f"({ahead['seeks']} seek(s), against {demand['seeks']})")
    demand_fps = demand["shown"] / demand["wall"] if demand["wall"] else 0
    ahead_fps = ahead["shown"] / ahead["wall"] if ahead["wall"] else 0
    check(ahead_fps >= demand_fps,
          f"read-ahead is not slower ({ahead_fps:.1f} vs {demand_fps:.1f} fps)")
    check(max(ahead["lateness"] or [0]) <= max(demand["lateness"] or [0]),
          f"read-ahead's worst frame is no worse "
          f"({max(ahead['lateness'] or [0]):.0f} vs "
          f"{max(demand['lateness'] or [0]):.0f} ms)")

    failed = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
