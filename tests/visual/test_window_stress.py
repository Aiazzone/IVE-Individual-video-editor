"""Playback running, window mistreated: does the UI survive?

The reported symptom: "often, while a video is playing, shrinking the window
freezes the whole UI". The root cause found for the fullscreen hang predicts
exactly this shape: during playback ``frameSwapped`` fires 30-60 times a
second on the render thread, and any window-geometry call made while the GUI
thread holds the GIL had a *chance* - not a certainty - of meeting that
emission and deadlocking. Fullscreen-exit met it every time; plain shrinks
met it "molte volte".

So this drives the window through many cycles of resize, minimize/restore
and fullscreen/windowed WHILE PLAYING, tracing every step to a flushed file
(see test_window_shrink.py for why stdout is useless here). If the process
is killed by a timeout, the trace names the exact operation it died in.

    python tests/visual/test_window_stress.py [video.mp4]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "tests" / "output" / "window_stress.trace"

from harness import VisualTest, _isolate_settings  # noqa: E402

CYCLES = 4


def trace(message: str) -> None:
    with open(TRACE, "a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%H:%M:%S')} {message}\n")
        handle.flush()


def build() -> VisualTest:
    test = VisualTest("window_stress", width=1400, height=800)
    if len(sys.argv) > 1:
        sample = Path(sys.argv[1])
    else:
        candidates = sorted(ROOT.glob("*.mp4"))
        sample = candidates[0] if candidates else None

    def setup(t: VisualTest):
        trace("app running")
        if sample is None or not sample.is_file():
            trace("NO SAMPLE VIDEO - aborting")
            t.fail("no sample video to play")
            return
        t.app.playback.open(str(sample))
        t.app.playback.play()
        trace(f"playing {sample.name}")

    def op(label, fn):
        def step(t: VisualTest):
            trace(f">>> {label}")
            fn(t)
            trace(f"    {label} returned; "
                  f"visibility={t.window.property('visibility')} "
                  f"playing={t.app.playback.playing}")
        step.__name__ = label.replace(" ", "_")
        return step

    test.step(setup, 2500)

    for cycle in range(1, CYCLES + 1):
        n = f"[{cycle}/{CYCLES}]"
        test.step(op(f"{n} shrink resize", lambda t: (
            t.window.setWidth(700), t.window.setHeight(420))), 500)
        test.step(op(f"{n} grow resize", lambda t: (
            t.window.setWidth(1400), t.window.setHeight(800))), 500)
        test.step(op(f"{n} minimize", lambda t: t.window.showMinimized()), 600)
        test.step(op(f"{n} restore", lambda t: t.window.showNormal()), 600)
        test.step(op(f"{n} fullscreen", lambda t:
                     t.app.actions.invoke("view.toggle_fullscreen")), 600)
        test.step(op(f"{n} windowed", lambda t:
                     t.app.actions.invoke("view.toggle_fullscreen")), 600)

    def survived(t: VisualTest):
        position = t.app.playback.positionSeconds
        trace(f"event loop alive after {CYCLES} cycles; playhead {position:.2f}s")
        t.check(True, f"survived {CYCLES} full mistreatment cycles")
        t.check(position > 1.0,
                f"playback actually ran through it ({position:.2f}s)")
        t.app.playback.pause()
        trace("DONE")

    test.step(survived, 800)
    return test


if __name__ == "__main__":
    if TRACE.exists():
        TRACE.unlink()
    TRACE.parent.mkdir(parents=True, exist_ok=True)
    trace("=== run start ===")
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
