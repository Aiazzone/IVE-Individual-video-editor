"""Does leaving fullscreen freeze the window while a video is playing?

Reported against a real project, and only while playing - which is the detail
that matters, because it points at the read-ahead rather than at the window.

The test opens a project, starts playback, goes fullscreen, comes back, and
then checks that the application is still ALIVE: that timers still fire, that
the playhead is still advancing, and that the window still paints. A freeze
stops all three, so the steps after it simply never run and the process has to
be killed - which is itself the result.

    python tests/visual/test_fullscreen_freeze.py [project.iveproj]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import VisualTest, _isolate_settings  # noqa: E402

DEFAULT_PROJECT = Path(r"C:\Users\Administrador\Downloads\test\Test.iveproj")


def build() -> VisualTest:
    test = VisualTest("fullscreen_freeze", width=1400, height=800)
    state: dict = {}
    project = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PROJECT

    def open_project(t: VisualTest):
        if not project.is_file():
            t.fail(f"project not found: {project}")
            return
        ok = t.app.project.open(str(project))
        t.check(bool(ok), f"opened {project.name}")

    def start(t: VisualTest):
        t.app.playback.play()
        t.check(bool(t.app.playback.playing), "playback started")
        state["pos_before"] = t.app.playback.positionSeconds

    def enter(t: VisualTest):
        state["moved_before"] = (
            t.app.playback.positionSeconds - state.get("pos_before", 0.0))
        t.note(f"playhead advanced {state['moved_before']:.2f}s before going "
               f"fullscreen")
        state["t_enter"] = time.perf_counter()
        t.window.showFullScreen()

    def leave(t: VisualTest):
        t.note(f"fullscreen entered and held "
               f"{time.perf_counter() - state['t_enter']:.2f}s")
        state["pos_fs"] = t.app.playback.positionSeconds
        state["t_leave"] = time.perf_counter()
        t.window.showNormal()

    def alive(t: VisualTest):
        # Getting here at all proves the event loop kept running.
        elapsed = time.perf_counter() - state["t_leave"]
        t.note(f"came back from fullscreen {elapsed:.2f}s ago and the event "
               f"loop is still running")
        moved = t.app.playback.positionSeconds - state.get("pos_fs", 0.0)
        t.note(f"playhead advanced {moved:.2f}s since leaving fullscreen")
        t.check(moved > 0.05,
                f"the playhead is still moving after leaving fullscreen "
                f"({moved:.2f}s)")
        image = t.shoot("after_fullscreen")
        t.check(image is not None and not image.isNull(),
                "the window still paints")
        state["shot"] = image

    def repaints(t: VisualTest):
        image = t.shoot("after_fullscreen_2")
        before, after = state.get("shot"), image
        if before is None or after is None:
            return
        # A frozen window keeps presenting the same buffer.
        points = [(400, 300), (700, 350), (1000, 300)]
        moved = max(
            (max(abs(t.pixel(before, x, y)[i] - t.pixel(after, x, y)[i])
                 for i in range(3)) for x, y in points), default=0)
        t.note(f"picture changed by {moved} between two grabs 700 ms apart")
        t.check(moved > 1, f"the picture is still updating ({moved})")

    def stop(t: VisualTest):
        t.app.playback.pause()

    return (test
            .step(open_project, 2500)
            .step(start, 1500)
            .step(enter, 1500)
            .step(leave, 1500)
            .step(alive, 700)
            .step(repaints, 300)
            .step(stop, 200))


if __name__ == "__main__":
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
