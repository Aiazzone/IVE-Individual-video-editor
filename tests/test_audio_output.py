"""Does the sound reach the device, on time, at the right pitch?

test_audio_graph.py proved the graph produces the right samples. This test
moves the measuring point PAST the audio sink: it plays the same tone file
through the real transport - graph, read-ahead, take_audio, AudioOutput - and
taps every block the QAudioSink actually accepts. What the tap sees is what
the hardware is given, so a failure anywhere along the chain (blocks lost at a
drop, played twice after a seek, converted wrongly at the edge) shows up here
as a wrong pitch, a wrong length, or a playhead that disagrees with the sound.

Also covered, because they live in the same area:

* per-frame sample counts at fractional rates (the 0.9 s/hour drift);
* the audio buffer's rewind, which must anchor to where the seek LANDED.

The sink section is skipped, not failed, on a machine with no audio device -
the rest still runs.

    python tests/test_audio_output.py
"""

from __future__ import annotations

import os
import sys
import time
from fractions import Fraction
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ive" / "src"))
sys.path.insert(0, str(ROOT / "tests"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("IVE_SETTINGS", str(ROOT / "tests" / "output" / "settings-audio-output"))

from test_audio_graph import LEFT_HZ, RIGHT_HZ, dominant_hz, make_tone_file

results: list[tuple[bool, str]] = []


def check(condition: bool, message: str) -> None:
    results.append((bool(condition), message))
    print(f"  {'OK  ' if condition else 'FAIL'}  {message}")


# ── 1. drift-free sample counts ───────────────────────────────────────


def check_sample_bounds() -> None:
    from ive.engine.frame import AudioFormat, Timebase

    print("\n1. Per-frame sample counts at 29.97 fps")
    fmt = AudioFormat()
    ntsc = Timebase(Fraction(30000, 1001))

    hour = int(3600 * 30000 / 1001)              # frames in one hour
    exact_total = hour * fmt.sample_rate * 1001 // 30000

    total = 0
    counts = set()
    worst = 0.0
    for position in range(0, hour, 997):         # sampled, the hour is long
        start, count = fmt.sample_bounds(position, ntsc)
        counts.add(count)
        worst = max(worst, abs(start - position * fmt.sample_rate * 1001 / 30000))
    # Totals must be checked contiguously; use a shorter contiguous run too.
    run = 10_000
    for position in range(run):
        total += fmt.sample_bounds(position, ntsc)[1]
    run_exact = run * fmt.sample_rate * 1001 // 30000

    check(counts <= {1601, 1602},
          f"counts alternate 1601/1602, never a constant ({sorted(counts)})")
    check(worst < 1.0,
          f"every block starts within one sample of true time "
          f"(worst {worst:.3f})")
    check(total == run_exact,
          f"{run} frames sum to the exact boundary ({total} vs {run_exact}) - "
          f"the old constant-count scheme would be {run * 1602 - run_exact} "
          f"samples long by now")
    end_of_hour = fmt.sample_bounds(hour, ntsc)[0]
    check(end_of_hour == exact_total,
          f"after one hour the boundary is exact ({end_of_hour}), where "
          f"round() per frame drifted ~0.9 s")


def check_silence_sizes() -> None:
    from ive.engine.frame import AudioFormat, Frame, Timebase

    print("\n2. Silence is sized by position, like sound")
    fmt = AudioFormat()
    ntsc = Timebase(Fraction(30000, 1001))
    lengths = {len(Frame(p, ntsc, fmt).silence()) for p in range(300)}
    check(lengths == {1601, 1602},
          f"silent frames alternate lengths too ({sorted(lengths)}) - a gap "
          f"must occupy exactly the samples of the sound it replaces")


# ── 3. the rewind anchors where the seek landed ───────────────────────


def check_rewind(sample: Path) -> None:
    from ive.engine.frame import AudioFormat
    from ive.engine.producer import _AudioTrack

    print("\n3. Rewind lands sample-exact")
    fmt = AudioFormat()
    rate = fmt.sample_rate

    fresh = _AudioTrack(str(sample), fmt)
    fresh.read(0, 1)                             # anchor at zero...
    want = fresh.read(rate, rate // 5)           # ...so this is a pure
    fresh.close()                                # sequential decode: truth

    track = _AudioTrack(str(sample), fmt)
    track.read(int(rate * 2.5), rate // 10)      # far ahead first
    got = track.read(rate, rate // 5)            # now rewind behind the buffer
    track.close()

    diff = float(np.max(np.abs(want - got))) if want.shape == got.shape else 1.0
    check(diff < 1e-3,
          f"the same second reads identically after a rewind (max diff "
          f"{diff:.6f}) - anchoring to the REQUESTED time instead of the "
          f"landing pts shifted everything by up to a packet")

    peak = float(np.abs(got).max())
    check(peak > 0.05, f"the rewound read is not silence (peak {peak:.3f})")


# ── 4. the tone, measured after the sink ──────────────────────────────


def check_through_sink(sample: Path) -> None:
    print("\n4. The tone through the transport and the sink")
    from PySide6.QtGui import QGuiApplication

    from ive.playback.transport import PlaybackService

    app = QGuiApplication.instance() or QGuiApplication([])
    service = PlaybackService()

    accepted: list[np.ndarray] = []
    service._audio.on_write = lambda block: accepted.append(np.array(block))

    if not service.open(str(sample)):
        check(False, "the tone file opens in the transport")
        return
    service.play()

    if not service._audio_ready:
        print("  SKIP  no audio device on this machine; the sink section "
              "cannot run here")
        service.shutdown()
        return

    deadline = time.monotonic() + 25.0
    while time.monotonic() < deadline and service.positionSeconds < 1.6:
        app.processEvents()
        time.sleep(0.004)

    position = service.positionSeconds
    played = sum(len(b) for b in accepted)
    service.pause()
    service.shutdown()

    check(position >= 1.6,
          f"playback advanced on the audio clock ({position:.2f}s)")
    check(played >= service._audio._format.sample_rate,
          f"the sink accepted over a second of sound ({played} samples)")
    if not accepted:
        return

    rate = 48000
    buffer = np.concatenate(accepted, axis=0)
    # The device processes what it was given, minus at most its own buffer.
    gap = abs(len(buffer) / rate - position)
    check(gap < 0.7,
          f"playhead and sound agree (sink got {len(buffer) / rate:.2f}s, "
          f"playhead {position:.2f}s, gap {gap:.2f}s)")

    body = buffer[rate // 5:]                    # skip encoder priming
    left = dominant_hz(body[:, 0], rate)
    right = dominant_hz(body[:, 1], rate)
    print(f"  recovered after the sink: left {left:.1f} Hz, right {right:.1f} Hz")
    check(abs(left - LEFT_HZ) < 15,
          f"left keeps its pitch through the whole chain ({left:.1f} Hz) - "
          f"a lost or doubled block would smear this")
    check(abs(right - RIGHT_HZ) < 15,
          f"right keeps its pitch and is not a copy of the left "
          f"({right:.1f} Hz)")


def main() -> int:
    sample = make_tone_file(ROOT / "tests" / "output" / "tone.mp4")
    if sample is None:
        print("No usable encoder; cannot build the fixture.")
        return 2

    check_sample_bounds()
    check_silence_sizes()
    check_rewind(sample)
    check_through_sink(sample)

    failed = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    for message in failed:
        print("  -", message)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
