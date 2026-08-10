"""Does audio survive the trip through the graph?

None of the sample videos have an audio track, so this makes its own: a file
carrying a 440 Hz tone on the left channel and 880 Hz on the right. A known
signal is the point - it turns "the audio sounds right" into a number, and it
catches the failures that a listening test misses: channels swapped, sample
rate wrong by a factor, resampling that halves the pitch.

The frequency is recovered with a plain DFT bin search, so numpy is all it
needs.

    python tests/test_audio_graph.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ive" / "src"))

LEFT_HZ = 440.0
RIGHT_HZ = 880.0
SECONDS = 3.0
FPS = 30.0

results: list[tuple[bool, str]] = []


def check(condition: bool, message: str) -> None:
    results.append((bool(condition), message))
    print(f"  {'OK  ' if condition else 'FAIL'}  {message}")


def dominant_hz(samples: np.ndarray, rate: int) -> float:
    """The strongest frequency in a mono buffer."""
    if samples.size < 64:
        return 0.0
    windowed = samples * np.hanning(samples.size)
    spectrum = np.abs(np.fft.rfft(windowed))
    spectrum[0] = 0.0                       # ignore DC
    return float(np.fft.rfftfreq(samples.size, 1.0 / rate)[spectrum.argmax()])


def make_tone_file(path: Path) -> Path | None:
    """A video with a known stereo tone. Built once, then reused."""
    if path.is_file():
        print(f"  (reusing {path.name})")
        return path
    import av

    from ive.export.service import encoder_for

    rate = 48000
    encoder = encoder_for("h264", 320, 240, "yuv420p", FPS)
    if encoder is None:
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    container = av.open(str(path), "w", format="mp4")
    video = container.add_stream(encoder, rate=int(FPS))
    video.width, video.height = 320, 240
    video.pix_fmt = "yuv420p"
    audio = container.add_stream("aac", rate=rate)
    audio.layout = "stereo"

    total = int(rate * SECONDS)
    t = np.arange(total, dtype=np.float32) / rate
    stereo = np.stack([np.sin(2 * np.pi * LEFT_HZ * t) * 0.5,
                       np.sin(2 * np.pi * RIGHT_HZ * t) * 0.5])

    picture = np.zeros((240, 320, 3), dtype=np.uint8)
    for index in range(int(FPS * SECONDS)):
        frame = av.VideoFrame.from_ndarray(picture, format="rgb24")
        frame.pts = index
        for packet in video.encode(frame):
            container.mux(packet)

    block = 1024
    pts = 0
    for start in range(0, total - block, block):
        chunk = np.ascontiguousarray(stereo[:, start:start + block])
        frame = av.AudioFrame.from_ndarray(chunk, format="fltp",
                                           layout="stereo")
        frame.sample_rate = rate
        frame.pts = pts
        pts += block
        for packet in audio.encode(frame):
            container.mux(packet)
    for packet in audio.encode():
        container.mux(packet)
    for packet in video.encode():
        container.mux(packet)
    container.close()
    print(f"  built {path.name}: {LEFT_HZ:.0f} Hz left, {RIGHT_HZ:.0f} Hz right")
    return path


def main() -> int:
    from ive.engine.builder import build_from_project
    from ive.engine.frame import AudioFormat
    from ive.media.probe import probe

    sample = make_tone_file(ROOT / "tests" / "output" / "tone.mp4")
    if sample is None:
        print("No usable encoder; cannot build the fixture.")
        return 2

    info = probe(sample)
    check(bool(info.has_audio), "the fixture carries an audio stream")

    fmt = AudioFormat()
    graph = build_from_project([{"path": str(sample), "start": 0.0,
                                 "duration": 2.0, "id": "c"}],
                               fps=FPS, width=320, height=240)

    # Collect a second of audio the way a consumer would: frame by frame.
    blocks = []
    for index in range(int(FPS)):
        frame = graph.frame_at(index)
        if frame is None:
            break
        audio = frame.audio()
        if audio is not None and len(audio):
            blocks.append(audio)
    graph.close()

    check(bool(blocks), f"the graph produced audio blocks ({len(blocks)})")
    if not blocks:
        return 1

    buffer = np.concatenate(blocks, axis=0)
    peak = float(np.abs(buffer).max())
    print(f"  {buffer.shape[0]} samples, {buffer.shape[1]} channels, "
          f"peak {peak:.3f}")
    check(buffer.shape[1] == fmt.channels,
          f"the engine format is respected ({buffer.shape[1]} channels)")
    check(peak > 0.05,
          f"the audio is not silence (peak {peak:.3f}) - a graph that returns "
          f"zeros looks identical to one that works, until you listen")

    # Skip the first block: the encoder's priming samples are not the tone.
    body = buffer[fmt.sample_rate // 10:]
    left = dominant_hz(body[:, 0], fmt.sample_rate)
    right = dominant_hz(body[:, 1], fmt.sample_rate)
    print(f"  recovered: left {left:.1f} Hz, right {right:.1f} Hz")
    check(abs(left - LEFT_HZ) < 15,
          f"the left channel keeps its pitch ({left:.1f} vs {LEFT_HZ:.0f} Hz)")
    check(abs(right - RIGHT_HZ) < 15,
          f"the right channel keeps its pitch ({right:.1f} vs {RIGHT_HZ:.0f} "
          f"Hz) - and is not a copy of the left")

    failed = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    for message in failed:
        print("  -", message)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
