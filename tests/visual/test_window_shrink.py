"""Drive the fullscreen -> windowed transition and see if the app survives it.

Every previous attempt at this reported success and told us nothing, because a
hang kills the process and a killed process flushes no output: the run looked
identical to a clean one that printed nothing.

So this writes a **trace file, flushed after every line**. If the process is
killed the trace still says exactly which step it reached, which is the whole
point. The verdict is read from that file afterwards, not from stdout.

    python tests/visual/test_window_shrink.py [project.iveproj]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "tests" / "output" / "window_shrink.trace"

from harness import VisualTest, _isolate_settings  # noqa: E402

DEFAULT_PROJECT = Path(r"C:\Users\Administrador\Downloads\test\Test.iveproj")


def trace(message: str) -> None:
    """Append to the trace and flush. Survives a kill; print() does not."""
    with open(TRACE, "a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%H:%M:%S')} {message}\n")
        handle.flush()


def build() -> VisualTest:
    test = VisualTest("window_shrink", width=1400, height=800)
    project = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PROJECT

    def setup(t: VisualTest):
        trace("app running")
        if project.is_file():
            t.app.project.open(str(project))
            trace(f"project opened: {project.name}")
        else:
            trace(f"NO PROJECT at {project}")

    def play(t: VisualTest):
        pass  # NOT playing: does the hang need frames flowing?
        trace(f"playing={t.app.playback.playing}")

    def go_fullscreen(t: VisualTest):
        trace(f"visibility before: {t.window.property('visibility')}")
        trace(">>> invoking toggle_fullscreen (to FULLSCREEN)")
        t.app.actions.invoke("view.toggle_fullscreen")
        trace(f"returned; visibility now: {t.window.property('visibility')}")

    def shrink(t: VisualTest):
        trace(f"playhead {t.app.playback.positionSeconds:.2f}s")
        trace(">>> invoking toggle_fullscreen (SHRINK to windowed) <<<")
        t.app.actions.invoke("view.toggle_fullscreen")
        # If the app hangs inside the assignment, the trace stops right here
        # and the next line never appears. That IS the result.
        trace(f"SHRINK RETURNED; visibility now: {t.window.property('visibility')}")

    def survived(t: VisualTest):
        trace("event loop still alive after the shrink")
        trace(f"playhead {t.app.playback.positionSeconds:.2f}s")
        dog = getattr(t.app, "watchdog", None)
        if dog is not None:
            trace(f"watchdog: gui stalls={dog.stalls} "
                  f"render stalls={dog.render_stalls}")
        t.check(True, "reached the end without hanging")

    def finish(t: VisualTest):
        t.app.playback.pause()
        trace("DONE")

    return (test
            .step(setup, 2500)
            .step(play, 1500)
            .step(go_fullscreen, 2000)
            .step(shrink, 2500)
            .step(survived, 1500)
            .step(finish, 300))


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
