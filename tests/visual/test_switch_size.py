"""Do the controls in the settings panel keep their own size?

SettingRow anchors its control to both sides of the row, because a slider or a
segmented control is meaningless at its implicit width. A switch is the
exception: it is a pill with an intrinsic 40x22, and stretching it across a
392 px panel turns it into a bar that no longer reads as a switch.

The test walks the live object tree and compares each switch's width with its
implicitWidth.

    python tests/visual/test_switch_size.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import VisualTest, _isolate_settings  # noqa: E402


def find_all(node, fragment, out=None):
    """Every QML object whose type name contains ``fragment``."""
    out = [] if out is None else out
    for child in node.children():
        if fragment in child.metaObject().className():
            out.append(child)
        find_all(child, fragment, out)
    return out


def build() -> VisualTest:
    test = VisualTest("switch_size")

    def open_settings(t: VisualTest):
        t.window.openSection("settings")

    def measure(t: VisualTest):
        t.shoot("settings")

        switches = find_all(t.window, "AppSwitch")
        if not switches:
            t.fail("no AppSwitch found in the settings panel")
            return
        t.note(f"{len(switches)} switch(es) in the panel")

        stretched = []
        for s in switches:
            width = float(s.property("width"))
            implicit = float(s.property("implicitWidth"))
            if width > implicit + 1:
                stretched.append((width, implicit))
        for width, implicit in stretched:
            t.note(f"  STRETCHED: {width:.0f} px wide, implicit {implicit:.0f}")
        t.check(not stretched,
                f"every switch keeps its implicit width "
                f"({len(switches) - len(stretched)}/{len(switches)})")

        # The row-filling controls must NOT have been broken by the same fix:
        # a slider that stopped filling would be the opposite bug.
        sliders = find_all(t.window, "AppSlider") + find_all(t.window, "Segmented")
        wide = [s for s in sliders if float(s.property("width")) > 200]
        t.check(not sliders or wide,
                f"sliders and segmented controls still fill the row "
                f"({len(wide)}/{len(sliders)} wider than 200 px)")

    return test.step(open_settings, 1200).step(measure, 400)


if __name__ == "__main__":
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
