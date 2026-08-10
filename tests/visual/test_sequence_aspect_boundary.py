"""Crossing into a clip with a different aspect AND rate, while playing.

Reported on a real project (16:9 @29.963 followed by 9:16 @29.971): the
moment playback crosses into the vertical clip the preview shows black where
the video should be, and the ambient backdrop - which blurs the on-screen
frame - goes black with it. Seeking to the same spot while paused shows the
frame correctly, which is what points the finger at the streaming path
rather than the graph: both paths pull the same composited canvas.

The fixtures are synthetic (solid orange 16:9 at 30 fps, solid cyan 9:16 at
29.97 fps) so "black" and "correct" are unmistakable colours, not judgment.

    python tests/visual/test_sequence_aspect_boundary.py
"""

from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "tests" / "output"

from harness import VisualTest, _isolate_settings  # noqa: E402

WIDE = OUTPUT / "boundary_wide_30.mp4"     # 848x478, 30 fps, orange
TALL = OUTPUT / "boundary_tall_2997.mp4"   # 478x850, 29.97 fps, cyan
CLIP_SECONDS = 4.0


def make_fixture(path: Path, width: int, height: int, rate: Fraction,
                 rgb: tuple[int, int, int]) -> None:
    if path.is_file():
        return
    import av
    import numpy as np

    OUTPUT.mkdir(parents=True, exist_ok=True)
    container = av.open(str(path), "w")
    stream = container.add_stream("libx264", rate=rate)
    stream.width = width
    stream.height = height
    stream.pix_fmt = "yuv420p"
    frame_count = int(CLIP_SECONDS * float(rate))
    array = np.zeros((height, width, 3), dtype=np.uint8)
    array[:, :] = rgb
    for _ in range(frame_count):
        frame = av.VideoFrame.from_ndarray(array, format="rgb24")
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def centre_sample(t: VisualTest, image) -> tuple[int, int, int]:
    """The pixel at the centre of the window: inside the video, both clips."""
    return t.pixel(image, image.width() // 2, int(image.height() * 0.45))


def side_sample(t: VisualTest, image) -> tuple[int, int, int]:
    """A pixel beside the vertical clip, at video height.

    With viewAspect the video item hugs the 9:16 clip, so this point lies on
    the ambient backdrop. Before the fix it fell on the black pillars the
    compositor bakes into the 16:9 canvas - the reported bug.
    """
    return t.pixel(image, int(image.width() * 0.30), int(image.height() * 0.45))


def build() -> VisualTest:
    test = VisualTest("sequence_aspect_boundary", width=1400, height=880)

    make_fixture(WIDE, 848, 478, Fraction(30, 1), (255, 140, 0))
    make_fixture(TALL, 478, 850, Fraction(30000, 1001), (0, 200, 255))

    def setup(t: VisualTest):
        ok = t.app.playback.open_sequence([
            {"path": str(WIDE), "start": 0.0, "duration": CLIP_SECONDS},
            {"path": str(TALL), "start": CLIP_SECONDS, "duration": CLIP_SECONDS},
        ])
        t.check(ok, "the two-clip sequence loaded")

    def start_before_boundary(t: VisualTest):
        t.app.playback.seek_seconds(CLIP_SECONDS - 1.0)
        t.app.playback.play()

    def while_playing_tall(t: VisualTest):
        position = t.app.playback.positionSeconds
        t.check(t.app.playback.playing, "still playing after the boundary")
        t.check(position > CLIP_SECONDS + 0.5,
                f"the playhead crossed into the tall clip ({position:.2f}s)")
        image = t.shoot("playing_tall")
        rgb = centre_sample(t, image)
        t.note(f"centre while playing: {t.hexof(rgb)} at {position:.2f}s")
        t.check(rgb[2] > 100 and rgb[1] > 80,
                f"the tall clip's cyan is on screen while playing ({t.hexof(rgb)})")
        side = side_sample(t, image)
        t.note(f"beside the clip while playing: {t.hexof(side)}")
        t.check(sum(side) > 24 and side[2] >= side[0],
                f"the ambient backdrop, not black pillars, flanks the clip "
                f"({t.hexof(side)})")

    def pause_and_seek(t: VisualTest):
        t.app.playback.pause()
        t.app.playback.seek_seconds(CLIP_SECONDS + 1.5)

    def paused_check(t: VisualTest):
        image = t.shoot("paused_tall")
        rgb = centre_sample(t, image)
        t.note(f"centre while paused: {t.hexof(rgb)}")
        t.check(rgb[2] > 100 and rgb[1] > 80,
                f"the same frame is right when sought while paused ({t.hexof(rgb)})")
        side = side_sample(t, image)
        t.note(f"beside the clip while paused: {t.hexof(side)}")
        t.check(sum(side) > 24 and side[2] >= side[0],
                f"paused view matches: ambient beside the clip ({t.hexof(side)})")

    test.step(setup, 1200)
    test.step(start_before_boundary, 2600)   # 1s of wide + 1.6s into tall
    test.step(while_playing_tall, 400)
    test.step(pause_and_seek, 900)
    test.step(paused_check, 400)
    return test


if __name__ == "__main__":
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
