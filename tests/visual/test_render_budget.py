"""What does the interface itself cost to draw?

The engine can meet its budget and the application still stutter, because the
shell is composited too: several glass surfaces, an ambient backdrop and the
preview all want the same GPU.

**Measuring frames-per-second here would be wrong.** Qt only presents a frame
when something changed, so switching every effect off makes the counter drop -
not because it got slower, but because nothing is moving. What matters is
**how long one render pass takes**. That is measured between
``beforeRendering`` and ``afterFrameEnd``.

The idle clip is left running in every case, so there is always a steady
stream of new frames to draw and the comparison is like for like.

    python tests/visual/test_render_budget.py
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import VisualTest, _isolate_settings  # noqa: E402

#: A 60 Hz screen leaves 16.7 ms per frame. Anything close to that is the
#: interface alone eating the whole budget, before playback asks for anything.
BUDGET_MS = 16.7


class RenderTimer:
    """Times the render pass of each presented frame."""

    def __init__(self, window) -> None:
        self.samples: list[float] = []
        self._start = 0.0
        window.beforeRendering.connect(self._begin, type=0)   # DirectConnection
        window.afterRendering.connect(self._end, type=0)

    def _begin(self) -> None:
        self._start = time.perf_counter()

    def _end(self) -> None:
        if self._start:
            self.samples.append((time.perf_counter() - self._start) * 1000.0)

    def reset(self) -> None:
        self.samples.clear()

    def stats(self) -> tuple[float, float, int]:
        if not self.samples:
            return 0.0, 0.0, 0
        ordered = sorted(self.samples)
        median = statistics.median(ordered)
        p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
        return median, p95, len(ordered)


def build() -> VisualTest:
    test = VisualTest("render_budget", width=1600, height=900)
    state: dict = {}

    def prepare(t: VisualTest):
        # The idle clip stays on throughout: it guarantees a constant stream of
        # new frames, so every configuration is measured under the same load.
        t.app.settings.set("appearance.idle_background", True)
        state["timer"] = RenderTimer(t.window)

    def configure(label: str, glass: str, ambient: bool):
        def run(t: VisualTest):
            t.app.settings.set("appearance.glass", glass)
            t.app.settings.set("shell.ambient_backdrop", ambient)
            state["label"] = label
            state["timer"].reset()
        return run

    def record(t: VisualTest):
        median, p95, count = state["timer"].stats()
        state.setdefault("results", []).append((state["label"], median, p95, count))
        t.note(f"{state['label']:<34} median {median:5.2f} ms   "
               f"p95 {p95:5.2f} ms   ({count} frames)")

    def open_panel(t: VisualTest):
        t.window.openSection("settings")
        state["timer"].reset()
        state["label"] = "everything on + panel open"

    def verdict(t: VisualTest):
        results = state.get("results", [])
        t.note("")
        table = {label: (median, p95) for label, median, p95, _ in results}

        full = table.get("everything on", (0, 0))
        bare = table.get("no glass, no ambient", (0, 0))
        if bare[0] > 0:
            t.note(f"the shell effects add {full[0] - bare[0]:.2f} ms per frame "
                   f"({full[0]:.2f} vs {bare[0]:.2f})")

        for label, (median, p95) in table.items():
            verdict_text = "OK" if p95 <= BUDGET_MS else "OVER 16.7 ms"
            t.note(f"  {label:<34} p95 {p95:5.2f} ms  {verdict_text}")

        t.check(full[1] <= BUDGET_MS,
                f"a full render pass fits in one 60 Hz frame "
                f"(p95 {full[1]:.2f} ms <= {BUDGET_MS} ms)")

    return (test
            .step(prepare, 800)
            .step(configure("everything on", "always", True), 2500)
            .step(record, 100)
            .step(configure("glass off", "never", True), 2500)
            .step(record, 100)
            .step(configure("ambient off", "always", False), 2500)
            .step(record, 100)
            .step(configure("no glass, no ambient", "never", False), 2500)
            .step(record, 100)
            .step(configure("everything on", "always", True), 300)
            .step(open_panel, 2500)
            .step(record, 100)
            .step(verdict, 200))


if __name__ == "__main__":
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
