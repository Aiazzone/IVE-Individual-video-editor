"""Does the watchdog actually catch a hung GUI thread?

A diagnostic that only works in theory is worse than none, because the next
hang produces silence again and we conclude the hang was somewhere else. So
the GUI thread is deliberately blocked here, and the test requires a dump to
appear naming the function that blocked it.

    python tests/test_watchdog.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ive" / "src"))

results: list[tuple[bool, str]] = []


def check(condition: bool, message: str) -> None:
    results.append((bool(condition), message))
    print(f"  {'OK  ' if condition else 'FAIL'}  {message}")


def the_function_that_hangs(seconds: float) -> None:
    """Named so it can be looked for in the dump."""
    time.sleep(seconds)


def main() -> int:
    from PySide6.QtCore import QCoreApplication, QTimer

    from ive.utils.watchdog import MainThreadWatchdog

    out = ROOT / "tests" / "output" / "watchdog"
    out.mkdir(parents=True, exist_ok=True)
    dump = out / "stall.log"
    if dump.exists():
        dump.unlink()

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    dog = MainThreadWatchdog(app, threshold=1.0, log_dir=out)
    dog.start()

    state: dict = {}

    def healthy():
        # Half a second of a responsive event loop must NOT be reported.
        state["stalls_when_healthy"] = dog.stalls

    def hang():
        the_function_that_hangs(2.5)      # well past the 1.0s threshold

    def finish():
        state["stalls_after_hang"] = dog.stalls
        dog.stop()
        app.quit()

    QTimer.singleShot(600, healthy)
    QTimer.singleShot(900, hang)
    QTimer.singleShot(4200, finish)
    app.exec()

    check(state.get("stalls_when_healthy") == 0,
          f"a responsive event loop is not reported as a stall "
          f"({state.get('stalls_when_healthy')})")
    check(state.get("stalls_after_hang", 0) >= 1,
          f"the 2.5s hang was caught ({state.get('stalls_after_hang')} stall)")
    check(state.get("stalls_after_hang", 0) == 1,
          f"one hang produces ONE dump, not one per poll "
          f"({state.get('stalls_after_hang')})")

    text = dump.read_text(encoding="utf-8") if dump.exists() else ""
    check(bool(text), f"a dump was written to {dump.name}")
    check("the_function_that_hangs" in text,
          "the dump names the function that blocked the GUI thread")
    check("Thread" in text and text.count("File ") >= 1,
          "the dump contains stacks, not just a header")
    if text:
        interesting = [line for line in text.splitlines()
                       if "the_function_that_hangs" in line]
        for line in interesting[:2]:
            print(f"       {line.strip()}")

    # ── the render side ───────────────────────────────────────────────
    # The GUI thread stayed responsive throughout the checks below; what is
    # missing is frames reaching the screen. That combination - application
    # alive, window frozen - is the one the fullscreen hang actually produces,
    # and the one the heartbeat alone cannot see.
    print("\n  render watch")
    dump2 = out / "stall.log"
    quiet = MainThreadWatchdog(app, threshold=1.0, log_dir=out)
    painting = {"expected": False}

    class _FakeWindow:
        class _Signal:
            def connect(self, *_a, **_k):
                pass
        frameSwapped = _Signal()

    quiet.watch_window(_FakeWindow(), lambda: painting["expected"])
    quiet.start()

    time.sleep(1.8)          # nothing swapping, but nothing should be
    check(quiet.render_stalls == 0,
          f"a still window is not reported as frozen ({quiet.render_stalls})")

    painting["expected"] = True
    time.sleep(2.2)          # now frames are expected and none arrive
    check(quiet.render_stalls == 1,
          f"a window that stops painting IS reported ({quiet.render_stalls})")
    quiet.stop()

    text2 = dump2.read_text(encoding="utf-8") if dump2.exists() else ""
    check("WINDOW STOPPED PAINTING" in text2,
          "the dump says the window stopped painting, not that the GUI hung")

    failed = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    for message in failed:
        print("  -", message)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
