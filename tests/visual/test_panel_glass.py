"""Is the floating panel glass all the way down?

The panel is one surface. If the blur or the scrim stops part-way, the bottom
band reads as a different material stuck to the same rectangle - which is what
was reported.

The test samples a vertical line through the panel and requires the colour to
stay within a tolerance: on glass the tint is uniform even though what shows
through varies.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import VisualTest  # noqa: E402


def build() -> VisualTest:
    test = VisualTest("panel_glass")

    def open_settings(t: VisualTest):
        t.window.openSection("settings")

    def measure(t: VisualTest):
        image = t.shoot("settings")
        panel = t.find("FloatingPanel")
        if panel is None:
            t.fail("FloatingPanel not found")
            return

        x = int(panel.property("x"))
        y = int(panel.property("y"))
        w = int(panel.property("width"))
        h = int(panel.property("height"))
        t.note(f"panel geometry: x={x} y={y} w={w} h={h}")

        # Sample a column just inside the left edge, clear of the cards.
        column = x + 6
        samples = []
        for fraction in (0.08, 0.25, 0.45, 0.65, 0.85, 0.96):
            py = int(y + h * fraction)
            rgb = t.pixel(image, column, py)
            samples.append((round(fraction, 2), py, rgb))
            t.note(f"  at {int(fraction * 100):>3}% (y={py}): {t.hexof(rgb)}")

        values = [s[2] for s in samples]
        spread = max(
            max(abs(a[i] - b[i]) for i in range(3))
            for a in values for b in values
        )
        t.note(f"maximum channel spread down the panel: {spread}")
        # The backdrop behind the panel is a slow gradient, so some variation
        # is expected; a band with no glass at all jumps far more than this.
        t.check(spread <= 40,
                f"panel tint is uniform top to bottom (spread {spread} <= 40)")

        # The very bottom strip is the status line; check it too.
        bottom = t.pixel(image, column, y + h - 4)
        top = t.pixel(image, column, y + 60)
        delta = max(abs(bottom[i] - top[i]) for i in range(3))
        t.note(f"top vs bottom delta: {delta}  "
               f"({t.hexof(top)} vs {t.hexof(bottom)})")
        t.check(delta <= 40, f"bottom strip matches the panel body ({delta} <= 40)")

    return (test
            .step(open_settings, 900)
            .step(measure, 300))


if __name__ == "__main__":
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
