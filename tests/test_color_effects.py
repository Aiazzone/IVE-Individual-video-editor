"""Colour effects, bottom-up: the ops, the catalogue, the graph.

* apply_colour_ops - each primitive does what its name promises, and an
  unknown op degrades instead of breaking (recipes from newer versions);
* the factory catalogue loads, with its sections in display order;
* TimedColor grades only the frames inside its span;
* a colour span handed to the graph builder reaches the produced frames -
  the same graph the preview and the export pull.

    python tests/test_color_effects.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ive" / "src"))

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    print(f"  {'OK  ' if condition else 'FAIL'} {message}")
    if not condition:
        failures.append(message)


def test_ops() -> None:
    from ive.engine.filters import apply_colour_ops

    print("\n--- the primitive ops ---")
    base = np.zeros((8, 8, 3), dtype=np.uint8)
    base[:, :] = (200, 120, 60)

    gray = apply_colour_ops(base, [{"op": "saturation", "amount": 0.0}])
    check(int(gray[0, 0, 0]) == int(gray[0, 0, 1]) == int(gray[0, 0, 2]),
          "saturation 0 makes every channel equal")

    brighter = apply_colour_ops(base, [{"op": "brightness", "amount": 0.2}])
    check(int(brighter[0, 0, 0]) > 200, "brightness lifts")

    warm = apply_colour_ops(base, [{"op": "temperature", "amount": 0.8}])
    check(int(warm[0, 0, 0]) > 200 and int(warm[0, 0, 2]) < 60,
          "warm temperature pushes red up and blue down")

    vignetted = apply_colour_ops(base, [{"op": "vignette", "strength": 0.8}])
    centre = int(vignetted[4, 4, 0])
    corner = int(vignetted[0, 0, 0])
    check(corner < centre, f"vignette darkens the corners ({corner} < {centre})")

    same = apply_colour_ops(base, [{"op": "from_the_future", "x": 1}])
    check(np.array_equal(same, base),
          "an unknown op is skipped, not an explosion")

    untouched = base.copy()
    apply_colour_ops(base, [{"op": "contrast", "amount": 1.5}])
    check(np.array_equal(base, untouched), "the input frame is never mutated")


def test_catalogue() -> None:
    from ive.color import library

    print("\n--- the factory catalogue ---")
    library.reload()
    effects = library.list_effects()
    check(len(effects) >= 14, f"factory effects loaded ({len(effects)})")
    order = library.sections()
    check(order[:4] == ["nostalgia", "cyberpunk", "cinema", "base"],
          f"sections in display order ({order})")
    noir = library.effect_by_id("noir")
    check(noir is not None and noir["names"].get("it") == "Noir",
          "an effect resolves with its localised names")
    check(library.ops_for("does_not_exist") == [],
          "an unknown id yields an empty recipe, so old projects still load")


def test_timed_color() -> None:
    from ive.engine.filters import TimedColor
    from ive.engine.frame import AudioFormat, Frame, Timebase

    print("\n--- TimedColor: grade only inside the span ---")
    filt = TimedColor([{"start": 10, "end": 20,
                        "ops": [{"op": "saturation", "amount": 0.0}]}])

    def frame_at(position):
        frame = Frame(position, Timebase(), AudioFormat())
        array = np.zeros((4, 4, 3), dtype=np.uint8)
        array[:, :] = (200, 40, 40)
        frame.set_image(array)
        return filt.process(frame)

    inside = frame_at(15).image()
    outside = frame_at(5).image()
    check(int(inside[0, 0, 0]) == int(inside[0, 0, 1]),
          "a frame inside the span is graded")
    check(int(outside[0, 0, 0]) == 200 and int(outside[0, 0, 2]) == 40,
          "a frame outside passes untouched")


def test_fast_path() -> None:
    import time

    from ive.color.library import ops_for, reload
    from ive.engine.filters import ColorGrade, apply_colour_ops

    print("\n--- the baked-LUT fast path ---")
    reload()
    ops = ops_for("vhs_80s")            # colour ops AND a vignette
    rng = np.random.default_rng(7)
    frame = rng.integers(0, 256, size=(720, 1280, 3), dtype=np.uint8)

    grade = ColorGrade(ops)
    fast = grade.apply(frame)           # first call pays the bake
    reference = apply_colour_ops(frame, ops, {})
    error = int(np.abs(fast.astype(int) - reference.astype(int)).max())
    check(error <= 6,
          f"the LUT matches the reference chain (max channel error {error})")

    # The no-OpenCV fallback (baked 3D LUT) must stay faithful too.
    fallback = ColorGrade(ops)
    fallback._steps = False
    error2 = int(np.abs(fallback.apply(frame).astype(int)
                        - reference.astype(int)).max())
    check(error2 <= 6,
          f"the no-OpenCV fallback matches as well (max error {error2})")

    runs = 8
    start = time.perf_counter()
    for _ in range(runs):
        grade.apply(frame)
    per_frame = (time.perf_counter() - start) / runs * 1000
    start = time.perf_counter()
    apply_colour_ops(frame, ops, {})
    slow = (time.perf_counter() - start) * 1000
    check(per_frame < 25.0,
          f"720p grading fits the frame budget ({per_frame:.1f} ms/frame, "
          f"was {slow:.1f} ms with the op chain)")


def test_through_the_graph() -> None:
    from ive.engine.builder import build_from_project

    print("\n--- a colour span through the graph ---")
    sample = sorted(ROOT.glob("*.mp4"))
    if not sample:
        print("  (no sample video; skipping)")
        return
    clip = {"path": str(sample[0]), "start": 0.0, "duration": 2.0, "id": "c1"}
    span = [{"start": 0.0, "end": 2.0,
             "ops": [{"op": "saturation", "amount": 0.0}]}]

    plain = build_from_project([dict(clip)], fps=25.0, width=320, height=180)
    graded = build_from_project([dict(clip)], fps=25.0, width=320, height=180,
                                color_spans=span)
    try:
        a = plain.frame_at(10).image()
        b = graded.frame_at(10).image()
        check(a is not None and b is not None, "both graphs produce the frame")
        if a is not None and b is not None:
            spread_a = float(np.abs(a[..., 0].astype(int)
                                    - a[..., 2].astype(int)).mean())
            spread_b = float(np.abs(b[..., 0].astype(int)
                                    - b[..., 2].astype(int)).mean())
            check(spread_b < 1.0 <= spread_a + 1.0,
                  f"the graded graph is grayscale, the plain one is not "
                  f"(channel spread {spread_b:.2f} vs {spread_a:.2f})")
    finally:
        plain.close()
        graded.close()


def main() -> int:
    test_ops()
    test_catalogue()
    test_timed_color()
    test_fast_path()
    test_through_the_graph()
    print(f"\n{'PASS' if not failures else 'FAIL'} ({len(failures)} problem(s))")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
