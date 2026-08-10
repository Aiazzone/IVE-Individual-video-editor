"""The idle waves: endless phase, no loop seam, and they really move.

The old implementation translated a periodic shape and wrapped - a loop
with a restart the eye could find. The new one advances a phase inside the
sines (the HMI wave technique): there is no wrap to see because the
animation never passes through the same state twice. What a test CAN
verify: the phase grows, the pixels actually change between two moments,
and reduce-motion freezes it.

    python tests/visual/test_idle_waves.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]

from harness import VisualTest, _isolate_settings  # noqa: E402


def band_pixels(image) -> list:
    """Samples along the wave region (no project open, mid-window)."""
    return [image.pixelColor(x, int(image.height() * 0.55)).rgb()
            for x in range(100, image.width() - 100, 60)]


def build() -> VisualTest:
    test = VisualTest("idle_waves", width=1400, height=880)
    state = {}

    def first_shot(t: VisualTest):
        idle = t.find("IdleBackdrop")
        t.check(idle is not None, "the idle backdrop is on show")
        if idle is not None:
            state["phase0"] = float(idle.property("phase"))
        state["shot0"] = band_pixels(t.shoot("waves_a"))

    def second_shot(t: VisualTest):
        idle = t.find("IdleBackdrop")
        phase = float(idle.property("phase")) if idle is not None else 0.0
        t.check(phase > state.get("phase0", 0.0) + 0.3,
                f"the phase advances endlessly ({state.get('phase0', 0):.2f} "
                f"-> {phase:.2f})")
        shot1 = band_pixels(t.shoot("waves_b"))
        moved = sum(1 for a, b in zip(state["shot0"], shot1) if a != b)
        t.check(moved >= 3,
                f"the water visibly moved ({moved} of {len(shot1)} samples)")
        # Freeze it the accessible way.
        t.app.settings.set("appearance.reduce_motion", True)

    def frozen(t: VisualTest):
        idle = t.find("IdleBackdrop")
        state["frozen_phase"] = float(idle.property("phase"))

    def frozen_check(t: VisualTest):
        idle = t.find("IdleBackdrop")
        phase = float(idle.property("phase"))
        t.check(abs(phase - state.get("frozen_phase", -1)) < 1e-6,
                "reduce-motion stops the water")

    # 2.5s, not less: grabbing the window while the wave shader is still
    # compiling deadlocked the grab (observed once, py-spy stack in shoot).
    test.step(first_shot, 2500)
    test.step(second_shot, 700)
    test.step(frozen, 700)
    test.step(frozen_check, 400)
    return test


if __name__ == "__main__":
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
