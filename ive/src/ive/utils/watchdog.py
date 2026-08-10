"""Catches the GUI thread when it stops responding, and says where.

A hang is the worst kind of bug to diagnose from a log, because a hung
program writes nothing. The window stops repainting, the user reports "it
froze", and the log simply ends - which is exactly what happened when leaving
fullscreen with animations disabled: the action was logged, the visibility
change that follows it never was, and no crash dump was written because the
process had not crashed.

So: the GUI thread stamps a heartbeat, and a plain daemon thread watches it.
When the stamp goes stale the watcher dumps the stack of EVERY thread. The
watcher is the only one that can do this, because by then the GUI thread is
the one stuck.

**Not** ``faulthandler.dump_traceback_later``. It does the same job and would
be less code, but docs/CODING_STANDARDS.md forbids it: heap corruption was
observed with native video libraries on Windows, which is precisely the
company this program keeps. ``dump_traceback`` called from our own thread has
no timer inside the C runtime and does not have that problem.

The cost is one timer at 4 Hz and one sleeping thread.
"""

from __future__ import annotations

import faulthandler
import logging
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer

log = logging.getLogger(__name__)

__all__ = ["MainThreadWatchdog"]

#: How often the GUI thread says it is alive.
_BEAT_MS = 250
#: How often the watcher looks. Shorter than the threshold, or a stall could
#: start and end between two checks.
_POLL_SECONDS = 0.5


class MainThreadWatchdog(QObject):
    """Dumps every thread's stack when the GUI thread stops answering."""

    def __init__(self, parent: QObject | None = None, *,
                 threshold: float = 2.0,
                 log_dir: Path | None = None) -> None:
        super().__init__(parent)
        self.threshold = float(threshold)
        self._path = Path(log_dir) / "stall.log" if log_dir else None
        self._beat = time.monotonic()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        #: True while a stall is in progress, so one hang writes one dump
        #: rather than one every half second for as long as it lasts.
        self._stalled = False
        self._stalls = 0

        # ── the render side ───────────────────────────────────────────
        # A window that stops PAINTING while the event loop keeps running
        # looks exactly like a frozen application, and the heartbeat above
        # cannot see it: that is how the fullscreen hang escaped both this
        # watchdog and every test that only checked the GUI thread was alive.
        self._swap = time.monotonic()
        self._swaps = 0
        self._render_stalled = False
        self._render_stalls = 0
        self._watching_window = False
        #: Answers "should this window be painting right now?". Qt only
        #: presents a frame when something changed, so an idle window
        #: legitimately swaps nothing for minutes - without this the check
        #: would cry wolf every time the user stopped touching anything.
        self._expected = None
        #: Frames are also expected until this moment, regardless of what
        #: `_expected` says. Set on every user gesture: a gesture that paints
        #: nothing IS the freeze. Gating only on playback made the check inert
        #: exactly when the hang was reproduced - with no video loaded.
        self._expect_until = 0.0

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._timer.setInterval(_BEAT_MS)
        self._timer.timeout.connect(self._tick)

    # ── control ───────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None:
            return
        self._beat = time.monotonic()
        self._timer.start()
        self._thread = threading.Thread(target=self._watch, name="watchdog",
                                        daemon=True)
        self._thread.start()
        log.info("Main-thread watchdog armed (%.1fs threshold, dumps to %s)",
                 self.threshold, self._path or "the log")

    def stop(self) -> None:
        self._stop.set()
        self._timer.stop()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=1.0)

    def watch_window(self, window, expected=None) -> None:
        """Also watch that ``window`` keeps presenting frames.

        ``expected()`` must return True only while the window is supposed to
        be painting continuously - during playback, typically. Qt presents a
        frame only when something changed, so without that guard a still
        window would be reported as frozen every few seconds.
        """
        self._expected = expected
        self._watching_window = True
        with self._lock:
            self._swap = time.monotonic()
        # QueuedConnection, never Direct: frameSwapped is emitted on the
        # render thread, and calling a Python slot there needs the GIL. When
        # the GUI thread blocks inside a native Qt call while holding the GIL
        # (QWindow::setVisibility waiting for the render thread to sync, as
        # leaving fullscreen does), a direct connection deadlocks the process:
        # GUI waits for render, render waits for the GIL, the GIL is the
        # GUI's. A queued emit posts the event from pure C++ and runs
        # _on_swap on the GUI thread instead.
        window.frameSwapped.connect(self._on_swap,
                                    Qt.ConnectionType.QueuedConnection)

    @property
    def stalls(self) -> int:
        """How many GUI-thread stalls have been seen. For tests."""
        return self._stalls

    @property
    def render_stalls(self) -> int:
        """How many times the window stopped painting while it should not."""
        return self._render_stalls

    def _on_swap(self) -> None:
        """A frame reached the screen. Called on the render thread."""
        with self._lock:
            self._swap = time.monotonic()
            self._swaps += 1

    # ── the heartbeat, on the GUI thread ──────────────────────────────

    def _tick(self) -> None:
        with self._lock:
            self._beat = time.monotonic()

    # ── the watcher, on its own thread ────────────────────────────────

    def _watch(self) -> None:
        while not self._stop.wait(_POLL_SECONDS):
            with self._lock:
                age = time.monotonic() - self._beat
            if age >= self.threshold:
                if not self._stalled:
                    self._stalled = True
                    self._stalls += 1
                    self._dump(age)
            elif self._stalled:
                self._stalled = False
                log.warning("GUI thread responding again after a stall")

            self._check_render()

    def expect_frames(self, seconds: float = 4.0) -> None:
        """Something just happened that must repaint. Watch for that long."""
        with self._lock:
            self._expect_until = time.monotonic() + float(seconds)
            self._swap = time.monotonic()

    def _check_render(self) -> None:
        """The window stopped painting while it should have been painting."""
        if not self._watching_window:
            return
        with self._lock:
            gesture = time.monotonic() < self._expect_until
        expected = gesture
        if not expected and self._expected is not None:
            try:
                expected = bool(self._expected())
            except Exception:
                return
        if not expected:
            # Nothing should be moving, so nothing swapping proves nothing.
            self._render_stalled = False
            with self._lock:
                self._swap = time.monotonic()
            return

        with self._lock:
            age = time.monotonic() - self._swap
            swaps = self._swaps
        if age >= self.threshold:
            if not self._render_stalled:
                self._render_stalled = True
                self._render_stalls += 1
                log.error("RENDER STALLED: no frame presented for %.1fs while "
                          "the GUI thread is still responding (%d frames so "
                          "far). The window is frozen, the application is not.",
                          age, swaps)
                self._dump(age, kind="render")
        elif self._render_stalled:
            self._render_stalled = False
            log.warning("Frames are being presented again after %.1fs", age)

    def _dump(self, age: float, kind: str = "gui") -> None:
        """Write every thread's stack. Runs on the watchdog thread."""
        if kind == "gui":
            log.error("GUI THREAD STALLED for %.1fs - dumping all thread "
                      "stacks", age)
        if self._path is None:
            faulthandler.dump_traceback(all_threads=True)
            return
        try:
            # Appended, never truncated: a second stall in the same session is
            # usually the one that explains the first.
            with open(self._path, "a", encoding="utf-8") as handle:
                what = ("GUI thread stalled" if kind == "gui" else
                        "WINDOW STOPPED PAINTING while the GUI thread is "
                        "still responding")
                handle.write(
                    f"\n{'=' * 70}\n"
                    f"{what} for {age:.1f}s at "
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"{'=' * 70}\n")
                handle.flush()
                faulthandler.dump_traceback(file=handle, all_threads=True)
            log.error("Stack dump written to %s", self._path)
        except Exception:
            # A watchdog that raises is worse than no watchdog.
            log.exception("Could not write the stall dump")
