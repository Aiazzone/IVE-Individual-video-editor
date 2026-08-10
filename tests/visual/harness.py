"""Visual test harness: run the real shell, capture it, measure pixels.

Why pixels and not eyeballs: on a video editor the picture dominates
perception. During development a panel that was ``#ffffff`` was read as "dark"
from a screenshot, and a glass surface that sampled the wrong part of the
scene looked perfectly plausible until something recognisable drifted through
it. Colour regressions are found by sampling, not by looking.

Every test here:

* runs the **real application**, not a mock;
* uses an **isolated settings file**, so a test never changes what the user
  sees the next time they launch (``IVE_SETTINGS``);
* saves a PNG next to the assertions, so a failure can also be looked at.

Run them all::

    python tests/visual/run_all.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ive" / "src"))

OUTPUT = ROOT / "tests" / "visual" / "output"


def _isolate_settings() -> None:
    """Never write into the user's real settings file."""
    if not os.environ.get("IVE_SETTINGS"):
        handle = tempfile.NamedTemporaryFile(
            prefix="ive-visual-", suffix=".json", delete=False)
        # An empty file is not valid JSON: the service would quarantine it and
        # log a warning on every single run.
        handle.write(b'{"values": {}}')
        handle.close()
        os.environ["IVE_SETTINGS"] = handle.name


class VisualTest:
    """One scripted run of the application."""

    def __init__(self, name: str, width: int = 1440, height: int = 880,
                 language: str = "en") -> None:
        self.name = name
        self.width = width
        self.height = height
        self.language = language
        self.failures: list[str] = []
        self.notes: list[str] = []
        self._steps: list[tuple[Callable, int]] = []
        self.app = None

    # ── scripting ─────────────────────────────────────────────────────

    def step(self, fn: Callable, delay_ms: int = 600) -> "VisualTest":
        """Queue a step to run ``delay_ms`` after the previous one."""
        self._steps.append((fn, delay_ms))
        return self

    def run(self) -> bool:
        _isolate_settings()
        OUTPUT.mkdir(parents=True, exist_ok=True)

        from PySide6.QtCore import QTimer

        from ive.app import Application
        from ive.utils.logging_setup import setup_logging
        from ive.utils.paths import bootstrap_user_data

        bootstrap_user_data()
        setup_logging()

        self.app = Application([])
        self.app.settings.set("window.fullscreen", False)
        self.app.settings.set("window.geometry", [40, 40, self.width, self.height])
        self.app.settings.set("app.language", self.language)

        queue = list(self._steps)

        def advance():
            if not queue:
                self.app.qt.quit()
                return
            fn, delay = queue.pop(0)
            try:
                fn(self)
            except Exception as exc:  # a failing step must not hang the run
                self.fail(f"step {getattr(fn, '__name__', fn)} raised: {exc}")
            QTimer.singleShot(delay, advance)

        QTimer.singleShot(1600, advance)
        self.app.run()
        return not self.failures

    # ── window access ─────────────────────────────────────────────────

    @property
    def window(self):
        return self.app.engine.rootObjects()[0]

    def find(self, class_fragment: str, root=None):
        """First QML object whose type name contains ``class_fragment``."""
        node = root if root is not None else self.window
        for child in node.children():
            if class_fragment in child.metaObject().className():
                return child
            found = self.find(class_fragment, child)
            if found is not None:
                return found
        return None

    # ── capture and measurement ───────────────────────────────────────

    def shoot(self, label: str = ""):
        """Grab the window and return the QImage, saving it as a PNG.

        NOT ``grabWindow()``. That call blocks the GUI thread on a
        QWaitCondition until the render thread syncs - while this Python
        frame still holds the GIL, which the render thread needs (Python
        paint items, PySide bindings). The result was an intermittent,
        timing-dependent deadlock that froze several test runs (py-spy:
        grabWindow -> QWaitCondition::wait under a QTimer callback).

        ``grabToImage()`` schedules the capture as a render job and calls
        back when done; waiting inside a C++ QEventLoop releases the GIL,
        so the render thread can finish the job. Same picture, no deadly
        embrace.
        """
        from PySide6.QtCore import QEventLoop, QTimer

        grab = self.window.contentItem().grabToImage()
        image = None
        if grab is not None:
            loop = QEventLoop()
            grab.ready.connect(loop.quit)
            QTimer.singleShot(10000, loop.quit)     # never hang a test run
            loop.exec()
            image = grab.image()
        if image is None or image.isNull():
            self.fail(f"screenshot {label!r} could not be captured")
            from PySide6.QtGui import QImage

            image = QImage(1, 1, QImage.Format.Format_ARGB32)
            image.fill(0)
        name = f"{self.name}{('_' + label) if label else ''}.png"
        image.save(str(OUTPUT / name))
        return image

    @staticmethod
    def pixel(image, x: int, y: int) -> tuple[int, int, int]:
        colour = image.pixelColor(int(x), int(y))
        return colour.red(), colour.green(), colour.blue()

    @staticmethod
    def hexof(rgb: tuple[int, int, int]) -> str:
        return "#%02x%02x%02x" % rgb

    # ── assertions ────────────────────────────────────────────────────

    def check(self, condition: bool, message: str) -> bool:
        if condition:
            self.notes.append(f"  OK   {message}")
        else:
            self.failures.append(message)
            self.notes.append(f"  FAIL {message}")
        return condition

    def fail(self, message: str) -> None:
        self.failures.append(message)
        self.notes.append(f"  FAIL {message}")

    def note(self, message: str) -> None:
        self.notes.append(f"       {message}")

    def report(self) -> None:
        print(f"\n=== {self.name} ===")
        for line in self.notes:
            print(line)
        print(f"  -> {'PASS' if not self.failures else 'FAIL'}"
              f" ({len(self.failures)} problem(s))")
