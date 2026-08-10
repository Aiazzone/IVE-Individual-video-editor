"""The engine core, exercised without Qt and without an interface.

That this file needs neither is the point: if the graph could only be tested
through the application, the "a filter is a pure function" claim would be
unverifiable, and it is the claim everything else rests on.

    python tests/test_engine.py
"""

from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ive" / "src"))

from ive.engine.consumer import PullConsumer, SequenceWalker      # noqa: E402
from ive.engine.filters import Dissolve, Gain, Grayscale, Opacity  # noqa: E402
from ive.engine.frame import AudioFormat, Frame, Timebase          # noqa: E402
from ive.engine.playlist import Entry, Playlist                    # noqa: E402
from ive.engine.producer import ColourProducer                     # noqa: E402
from ive.engine.tractor import Track, Tractor                      # noqa: E402

TB = Timebase(Fraction(25, 1))
AF = AudioFormat(48000, 2)

results: list[tuple[bool, str]] = []


def check(condition: bool, message: str) -> None:
    results.append((bool(condition), message))
    print(f"  {'OK  ' if condition else 'FAIL'}  {message}")


def section(title: str) -> None:
    print(f"\n--- {title} ---")


# ── laziness ──────────────────────────────────────────────────────────

def test_laziness() -> None:
    section("a frame evaluates nothing until asked")
    calls = {"image": 0, "audio": 0}

    def make_image():
        calls["image"] += 1
        return np.zeros((4, 4, 3), np.uint8)

    def make_audio():
        calls["audio"] += 1
        return np.zeros((1920, 2), np.float32)

    frame = Frame(0, TB, AF, image_fn=make_image, audio_fn=make_audio)
    check(calls == {"image": 0, "audio": 0}, "nothing evaluated on construction")

    frame.image()
    check(calls["image"] == 1 and calls["audio"] == 0,
          "asking for the picture does not decode the sound")

    frame.image()
    check(calls["image"] == 1, "the picture is evaluated once and cached")

    frame.audio()
    check(calls["audio"] == 1, "the sound is evaluated only when asked")


# ── filters are pure ──────────────────────────────────────────────────

def test_filters_are_pure() -> None:
    section("a filter is a pure function of a frame")
    original = np.full((4, 4, 3), 200, np.uint8)
    frame = Frame(7, TB, AF)
    frame.set_image(original)

    out = Grayscale().process(frame)
    check(out is not frame, "the filter returns a new frame")
    check(np.array_equal(frame.image(), original), "the input is left untouched")
    check(out.position == 7, "the position survives the filter")

    # Same input, run twice, in any order: same output.
    a = Opacity(0.5).process(frame).image()
    b = Opacity(0.5).process(frame).image()
    check(np.array_equal(a, b), "the same input always gives the same output")

    audio_frame = Frame(0, TB, AF)
    audio_frame.set_audio(np.full((10, 2), 0.5, np.float32))
    gained = Gain(0.5).process(audio_frame)
    check(abs(float(gained.audio()[0, 0]) - 0.25) < 1e-6,
          "an audio filter uses the same interface as a video one")
    check(abs(float(audio_frame.audio()[0, 0]) - 0.5) < 1e-6,
          "the audio input is left untouched too")


# ── playlist ──────────────────────────────────────────────────────────

def test_playlist() -> None:
    section("a playlist is a producer, and blanks are explicit")
    red = ColourProducer(8, 8, 25, TB, (255, 0, 0), AF, "red")
    green = ColourProducer(8, 8, 25, TB, (0, 255, 0), AF, "green")

    track = Playlist(TB, AF, "V1")
    track.append(Entry(red, length=10))
    track.append_blank(5)
    track.append(Entry(green, length=10))

    check(track.length == 25, f"the length is the sum of the entries ({track.length})")

    def colour_at(pos):
        frame = track.frame_at(pos)
        image = frame.image() if frame else None
        return None if image is None else tuple(int(v) for v in image[0, 0])

    check(colour_at(0) == (255, 0, 0), "frame 0 comes from the first entry")
    check(colour_at(9) == (255, 0, 0), "frame 9 is still the first entry")
    check(colour_at(12) is None, "the blank produces a frame with no picture")
    check(track.frame_at(12).properties.get("blank") is True,
          "the blank says so, instead of being an absence")
    check(colour_at(15) == (0, 255, 0), "frame 15 comes from the second entry")
    check(track.frame_at(25) is None, "past the end there is nothing")

    # The position is rewritten to the track's own timeline.
    check(track.frame_at(15).position == 15,
          "the frame carries the TRACK position, not the source position")


# ── tractor ───────────────────────────────────────────────────────────

def test_tractor() -> None:
    section("the tractor pulls every track at the same position")
    black = ColourProducer(8, 8, 30, TB, (0, 0, 0), AF, "black")
    blue = ColourProducer(8, 8, 30, TB, (0, 0, 255), AF, "blue")

    tractor = Tractor(TB, AF, 8, 8)
    tractor.add_track(Track(black, name="black"))
    top = tractor.add_track(Track(blue, name="V1"))

    def pixel():
        return tuple(int(v) for v in tractor.frame_at(0).image()[0, 0])

    check(pixel() == (0, 0, 255), "the top track wins at full opacity")

    top.opacity = 0.5
    mixed = pixel()
    check(abs(mixed[2] - 127) <= 2 and mixed[0] == 0,
          f"half opacity blends with the track below {mixed}")

    top.hidden = True
    check(pixel() == (0, 0, 0), "a hidden track drops out of the composite")

    top.hidden = False
    top.transition = Dissolve()
    top.opacity = 0.0
    check(pixel() == (0, 0, 0), "a transition at 0 shows only what is below")
    top.opacity = 1.0
    check(pixel() == (0, 0, 255), "a transition at 1 shows only what is above")


def test_audio_mix() -> None:
    section("audio is summed on the same graph as video")
    tractor = Tractor(TB, AF, 8, 8)

    class Tone(ColourProducer):
        def __init__(self, level):
            super().__init__(8, 8, 30, TB, (0, 0, 0), AF, "tone")
            self.level = level

        def frame_at(self, position):
            frame = super().frame_at(position)
            if frame is not None:
                frame.set_audio(np.full((1920, 2), self.level, np.float32))
            return frame

    tractor.add_track(Track(Tone(0.25), name="A1"))
    tractor.add_track(Track(Tone(0.25), video=False, name="A2"))

    audio = tractor.frame_at(0).audio()
    check(abs(float(audio[0, 0]) - 0.5) < 1e-6,
          "two tracks at 0.25 sum to 0.5")

    tractor.tracks[1].muted = True
    check(abs(float(tractor.frame_at(0).audio()[0, 0]) - 0.25) < 1e-6,
          "a muted track is left out of the mix")

    tractor.tracks[1].muted = False
    tractor.tracks[1].gain = 4.0
    check(abs(float(tractor.frame_at(0).audio()[0, 0]) - 1.0) < 1e-6,
          "the mix is clipped instead of wrapping around")


# ── one graph, two consumers ──────────────────────────────────────────

def test_same_graph_two_consumers() -> None:
    section("preview and export pull the SAME graph")
    black = ColourProducer(4, 4, 20, TB, (0, 0, 0), AF, "black")
    grey = ColourProducer(4, 4, 20, TB, (200, 200, 200), AF, "grey")

    tractor = Tractor(TB, AF, 4, 4)
    tractor.add_track(Track(black))
    tractor.add_track(Track(grey))
    tractor.filters.append(Grayscale())

    scrub = PullConsumer(tractor, want_image=True)          # like the preview
    walk = SequenceWalker(tractor, want_image=True, want_audio=False,
                          start=0, end=20)                   # like the export

    scrubbed = {p: scrub.pull(p).image().copy() for p in (0, 7, 19)}
    walked = {f.position: f.image().copy() for f in walk}

    same = all(np.array_equal(scrubbed[p], walked[p]) for p in scrubbed)
    check(same, "a scrubbed frame is identical to the exported one")
    check(len(walked) == 20, f"the walk covers the whole range ({len(walked)})")

    # Audio-only: the picture must not be decoded at all.
    seen = {"image": 0}

    class Counting(ColourProducer):
        def frame_at(self, position):
            frame = super().frame_at(position)

            def image():
                seen["image"] += 1
                return np.zeros((4, 4, 3), np.uint8)

            frame.set_image(None)
            frame._image_fn = image
            return frame

    audio_only = PullConsumer(Counting(4, 4, 10, TB, (0, 0, 0), AF),
                              want_image=False, want_audio=True)
    audio_only.pull(0)
    check(seen["image"] == 0,
          "asking for audio only never decodes the picture")


def main() -> int:
    print("IVE engine core")
    test_laziness()
    test_filters_are_pure()
    test_playlist()
    test_tractor()
    test_audio_mix()
    test_same_graph_two_consumers()

    failed = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("\nFAILURES:")
        for message in failed:
            print("  -", message)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
