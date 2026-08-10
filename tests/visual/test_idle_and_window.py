"""Three things the shell must get right around the idle state and the window.

* the idle waves must actually be DRAWN, and must MOVE. A Repeater that
  creates no delegates fails silently: nothing is drawn, no warning is
  printed, and reading the QML tells you nothing. Only pixels do;
* once a video is loaded they must stop - nobody is looking, and an animation
  nobody sees still costs a scene-graph update every frame;
* leaving fullscreen must not freeze the window, and the ambient backdrop must
  survive a cut between clips of different aspect ratios.

    python tests/visual/test_idle_and_window.py [video.mp4] [other.mp4]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]

from harness import VisualTest, _isolate_settings  # noqa: E402

#: Points across the backdrop, away from rail, panel and timeline.
PROBES = [(220, 180), (420, 300), (700, 240), (900, 380), (1100, 200)]


def samples() -> list[Path]:
    given = [Path(a) for a in sys.argv[1:] if Path(a).is_file()]
    return given or sorted(ROOT.glob("*.mp4"))


def spread(a, b) -> int:
    """Largest per-channel difference between two pixel lists."""
    return max((max(abs(p[i] - q[i]) for i in range(3))
                for p, q in zip(a, b)), default=0)


def build() -> VisualTest:
    test = VisualTest("idle_and_window", width=1400, height=800)
    state: dict = {}
    files = samples()

    def probe(t: VisualTest, image):
        return [t.pixel(image, x, y) for x, y in PROBES]

    # ── the waves, while idle ─────────────────────────────────────────

    def idle_first(t: VisualTest):
        # The bands are checked by COUNT, not by pixels. They are painted at
        # 3-5% alpha over a dark gradient, which is two or three levels out of
        # 255 - below what sampling a handful of points can tell apart. What
        # can be verified is that the Repeater instantiated them: handing it
        # the wrong kind of model creates nothing at all, draws nothing, and
        # prints no warning, which is how this file has failed before.
        backdrop = t.find("IdleBackdrop")
        repeater = None
        if backdrop is not None:
            for child in backdrop.children():
                if "Repeater" in child.metaObject().className():
                    repeater = child
        count = int(repeater.property("count")) if repeater is not None else 0
        t.check(count > 0, f"the idle waves were instantiated ({count} bands)")
        state["idle_a"] = probe(t, t.shoot("idle_a"))

    def idle_second(t: VisualTest):
        moved = spread(state["idle_a"], probe(t, t.shoot("idle_b")))
        t.note(f"idle backdrop changed by {moved} over 900 ms")
        # The bands used to move 31 px a second at 3-5% alpha: measurably
        # animated, visibly a still image. This asserts the motion is one a
        # person can actually see.
        t.check(moved > 2, f"the idle waves visibly move ({moved} levels)")

    # ── the waves, with a video loaded ────────────────────────────────

    def load(t: VisualTest):
        if not files:
            t.fail("no sample video found")
            return
        t.app.playback.open(str(files[0]))

    def loaded_first(t: VisualTest):
        backdrop = t.find("IdleBackdrop")
        t.check(backdrop is not None and not backdrop.property("visible"),
                "the idle backdrop is hidden once a video is loaded")
        state["load_a"] = probe(t, t.shoot("loaded_a"))

    def loaded_second(t: VisualTest):
        moved = spread(state["load_a"], probe(t, t.shoot("loaded_b")))
        t.note(f"backdrop changed by {moved} over 900 ms with a video loaded")
        t.check(moved <= 2,
                f"nothing keeps animating behind a loaded video ({moved})")

    # ── the window ────────────────────────────────────────────────────

    def go_fullscreen(t: VisualTest):
        t.window.showFullScreen()

    def leave_fullscreen(t: VisualTest):
        t.window.showNormal()

    def still_alive(t: VisualTest):
        # Reaching this step means the event loop survived the round trip: a
        # freeze would have stopped the timers driving these steps.
        image = t.shoot("after_fullscreen")
        t.check(image is not None and not image.isNull(),
                "the window still renders after leaving fullscreen")
        t.check(str(t.window.property("visibility")) != "Visibility.FullScreen",
                "the window really left fullscreen")

    # ── the ambient backdrop across a cut ─────────────────────────────

    def load_mixed(t: VisualTest):
        if len(files) < 2:
            t.note("only one sample: skipping the mixed-aspect cut")
            return
        clips = [{"path": str(path), "start": 1.5 * i, "duration": 1.5,
                  "sourceIn": 0.0} for i, path in enumerate(files[:2])]
        state["mixed"] = t.app.playback.open_sequence(clips)
        t.app.playback.seek_seconds(0.8)          # well inside the first clip

    def before_cut(t: VisualTest):
        if state.get("mixed"):
            state["before"] = probe(t, t.shoot("before_cut"))

    def after_cut(t: VisualTest):
        if state.get("mixed"):
            t.app.playback.seek_seconds(1.9)      # well inside the second

    def backdrop_survives(t: VisualTest):
        if not state.get("mixed"):
            return
        after = probe(t, t.shoot("after_cut"))
        before = state.get("before") or after
        bright_before = max(max(p) for p in before)
        bright_after = max(max(p) for p in after)
        t.note(f"backdrop brightness before the cut {bright_before}, "
               f"after {bright_after}")
        t.check(bright_after > 12,
                f"the ambient backdrop is not black after a cut between "
                f"different aspect ratios (peak {bright_after})")

    return (test
            .step(idle_first, 900)
            .step(idle_second, 300)
            .step(load, 1500)
            .step(loaded_first, 900)
            .step(loaded_second, 300)
            .step(go_fullscreen, 1200)
            .step(leave_fullscreen, 1500)
            .step(still_alive, 400)
            .step(load_mixed, 1500)
            .step(before_cut, 400)
            .step(after_cut, 1500)
            .step(backdrop_survives, 300))


if __name__ == "__main__":
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
