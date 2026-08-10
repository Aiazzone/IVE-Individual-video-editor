"""Replay of the user session that froze on 2026-08-09 11:18.

The log of that session: no project, no playback; four fullscreen toggles
succeed; ``appearance.reduce_motion`` is set to true; the NEXT toggle never
logs its visibility change. No stall.log despite a working watchdog, so the
GIL was held - the same deadlock family as the watchdog bug, through some
other Python that runs on the render thread.

This drives many toggle cycles with the same settings shape, tracing each to
a flushed file. A kill by timeout leaves the trace pointing at the exact
cycle that died.

    python tests/visual/test_fullscreen_cycles.py [cycles]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "tests" / "output" / "fullscreen_cycles.trace"

from harness import VisualTest, _isolate_settings  # noqa: E402

CYCLES = int(sys.argv[1]) if len(sys.argv) > 1 else 15


def trace(message: str) -> None:
    with open(TRACE, "a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%H:%M:%S')} {message}\n")
        handle.flush()


def build() -> VisualTest:
    test = VisualTest("fullscreen_cycles", width=1400, height=800)

    def setup(t: VisualTest):
        trace("app running; no project, no playback - as in the session")

    def toggle(label):
        def step(t: VisualTest):
            trace(f">>> {label} toggle_fullscreen")
            t.app.actions.invoke("view.toggle_fullscreen")
            trace(f"    {label} returned; "
                  f"visibility={t.window.property('visibility')}")
        step.__name__ = f"toggle_{label.replace('/', '_')}"
        return step

    def reduce_motion(t: VisualTest):
        trace(">>> settings.set reduce_motion=true (as the session did)")
        t.app.actions.invoke("settings.set",
                             {"key": "appearance.reduce_motion",
                              "value": "true"})
        trace("    set")

    test.step(setup, 1200)
    # The four toggles that succeeded in the session.
    for i in range(4):
        test.step(toggle(f"warmup {i + 1}/4"), 700)
    test.step(reduce_motion, 700)
    # ...and then the ones like the toggle that froze it.
    for i in range(CYCLES):
        test.step(toggle(f"{i + 1}/{CYCLES}"), 700)

    def survived(t: VisualTest):
        trace(f"event loop alive after {CYCLES} post-reduce-motion toggles")
        t.check(True, f"survived 4 + {CYCLES} fullscreen toggles")
        trace("DONE")

    test.step(survived, 500)
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
