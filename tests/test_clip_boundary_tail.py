"""The clip-boundary freeze, pinned down as three separate regressions.

A clip whose container outlives its video stream (the audio tail every
phone recording has) used to freeze playback at the cut: the producer kept
asking for pictures past the last real frame, the decoder clamped the index
and paid a keyframe seek plus a GOP decode for EVERY tail position, and the
read-ahead starved. Three fixes, each checked here on a real file:

* the producer answers positions past the video stream with a hole, not
  with a decode (`ClipProducer.frame_at` vs `source_length`);
* the decoder serves a repeated index from its cache and small forward
  jumps by decode-and-discard - no seeks (`VideoDecoder._last`,
  `_STEP_WINDOW`), which is also what mixed-fps timelines hit on every
  frame;
* a producer that dies mid-stream reports it (`_ReadAhead.on_error`)
  instead of parking silently while the transport waits forever.

    python tests/test_clip_boundary_tail.py
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ive" / "src"))

FPS = 25.0
VIDEO_SECONDS = 1.0
AUDIO_SECONDS = 1.4

results: list[tuple[bool, str]] = []


def check(condition: bool, message: str) -> None:
    results.append((bool(condition), message))
    print(f"  {'OK  ' if condition else 'FAIL'}  {message}")


def make_tailed_file(path: Path) -> Path | None:
    """A file whose audio runs 0.4s past the video - the shape that froze."""
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

    picture = np.zeros((240, 320, 3), dtype=np.uint8)
    for index in range(int(FPS * VIDEO_SECONDS)):
        picture[:] = (index * 9) % 255       # frames must differ
        frame = av.VideoFrame.from_ndarray(picture, format="rgb24")
        frame.pts = index
        for packet in video.encode(frame):
            container.mux(packet)

    total = int(rate * AUDIO_SECONDS)
    t = np.arange(total, dtype=np.float32) / rate
    stereo = np.stack([np.sin(2 * np.pi * 440.0 * t) * 0.5] * 2)
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
    print(f"  built {path.name}: video {VIDEO_SECONDS}s, audio {AUDIO_SECONDS}s")
    return path


def count_seeks(decoder):
    """Wrap the decoder so every real seek is counted."""
    counter = {"seeks": 0}
    inner = decoder._seek_and_decode

    def counting(index: int):
        counter["seeks"] += 1
        return inner(index)

    decoder._seek_and_decode = counting
    return counter


def main() -> int:
    from ive.engine.producer import ClipProducer
    from ive.media.reader import _ReadAhead

    sample = make_tailed_file(ROOT / "tests" / "output" / "audio_tail.mp4")
    if sample is None:
        print("No usable encoder; cannot build the fixture.")
        return 2

    print("\n--- the tail is a hole, not a decode ---")
    producer = ClipProducer(sample)
    check(producer.length > producer.source_length,
          f"the fixture reproduces the shape: sequence length "
          f"{producer.length} > video frames {producer.source_length}")
    seeks = count_seeks(producer._decoder)
    tail_position = producer.source_length + 2
    frame = producer.frame_at(tail_position)
    check(frame is not None and frame.image() is None,
          "a position past the video stream is a hole")
    check(seeks["seeks"] == 0,
          f"and it cost no seek at all ({seeks['seeks']})")

    print("\n--- repeats and small jumps do not seek ---")
    decoder = producer._decoder
    first = decoder.frame_at(10)             # may seek: positions us at 10
    baseline = seeks["seeks"]
    again = decoder.frame_at(10)             # the repeat, free from cache
    check(again is not None and seeks["seeks"] == baseline,
          f"a repeated index is served from cache ({seeks['seeks'] - baseline}"
          f" seek(s))")
    check(first is not None and again is not None
          and np.array_equal(first.array, again.array),
          "and it is the same picture")
    stepped = decoder.frame_at(12)           # +2: a 50fps clip on a 25fps timeline
    check(stepped is not None and seeks["seeks"] == baseline,
          f"a +2 jump decodes-and-discards instead of seeking "
          f"({seeks['seeks'] - baseline} seek(s))")
    producer.close() if hasattr(producer, "close") else decoder.close()

    print("\n--- a dying producer says so ---")
    errors: list[str] = []
    reported = threading.Event()

    def broken_source(index: int):
        raise RuntimeError("decoder exploded")

    ahead = _ReadAhead()
    ahead.on_error = lambda message: (errors.append(message), reported.set())
    ahead.start(broken_source, key="broken", index=0, end=100)
    got = reported.wait(timeout=3.0)
    ahead.shutdown()
    check(got, "the error callback fires instead of a silent park")
    check(bool(errors) and "decoder exploded" in errors[0],
          f"and carries the cause ({errors[0] if errors else 'nothing'})")

    failed = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
