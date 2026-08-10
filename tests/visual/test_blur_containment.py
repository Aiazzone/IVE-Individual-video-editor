"""Does the blur stay inside its surface?

A glass surface samples a margin of scene BEYOND its own edge, because a blur
kernel at the boundary has nothing to reach into and comes out sharper there.
Sampling wider is correct. **Drawing** wider is not: the effect then paints
over the video around the panel.

The test compares the pixels just outside the tool rail with glass on and with
glass off. If turning glass on changes anything outside the rail, the effect is
escaping its bounds.

    python tests/visual/test_blur_containment.py
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
    test = VisualTest("blur_containment", width=1400, height=800)
    state: dict = {}

    def glass_off(t: VisualTest):
        t.app.settings.set("appearance.glass", "never")

    def capture_off(t: VisualTest):
        state["off"] = t.shoot("glass_off")
        rail = t.find("ToolRail")
        if rail is None:
            t.fail("ToolRail not found")
            return
        state["rail"] = (int(rail.property("x")), int(rail.property("y")),
                         int(rail.property("width")), int(rail.property("height")))
        t.note("rail geometry: x=%d y=%d w=%d h=%d" % state["rail"])

    def glass_on(t: VisualTest):
        t.app.settings.set("appearance.glass", "always")

    def compare(t: VisualTest):
        on = t.shoot("glass_on")
        off = state.get("off")
        rail = state.get("rail")
        if off is None or rail is None:
            return
        x, y, w, h = rail

        # A ring of points just outside the rail, at several distances. The
        # blur radius is what decides how far a leak would reach.
        outside = []
        for gap in (4, 12, 24, 40, 64):
            outside += [
                (x + w + gap, y + h // 2),              # to the right
                (x + w // 2, y - gap),                  # above
                (x + w // 2, y + h + gap),              # below
            ]
        # Only points that are outside EVERY glass surface count. The timeline
        # is glass too, so a sample that lands in it changes for a perfectly
        # good reason - the first version of this test read that as a leak.
        timeline_top = t.height - int(t.app.shell.v.get("timelineHeight", 232))
        panel_left = t.width - 420
        outside = [
            (px, py) for px, py in outside
            if 0 <= px < t.width and 0 <= py < t.height
            and py < timeline_top - 8          # above the timeline
            and px < panel_left                # clear of the floating panel
        ]
        t.note(f"{len(outside)} sample points in open video area "
               f"(timeline starts at y={timeline_top})")

        leaks = []
        for px, py in outside:
            a = t.pixel(off, px, py)
            b = t.pixel(on, px, py)
            delta = max(abs(a[i] - b[i]) for i in range(3))
            if delta > 6:
                leaks.append((px, py, delta, t.hexof(a), t.hexof(b)))

        for px, py, delta, a, b in leaks:
            t.note(f"  LEAK at ({px},{py}): {a} -> {b}  (delta {delta})")

        t.check(not leaks,
                f"nothing outside the rail changes when glass is on "
                f"({len(leaks)}/{len(outside)} points differ)")

        # And the inside must actually change, or the test proves nothing.
        inside = [(x + w // 2, y + h // 2), (x + 8, y + 20)]
        changed = sum(
            1 for px, py in inside
            if max(abs(t.pixel(off, px, py)[i] - t.pixel(on, px, py)[i])
                   for i in range(3)) > 3
        )
        t.check(changed > 0,
                f"the inside of the rail does change ({changed}/{len(inside)}) - "
                f"otherwise the comparison would be meaningless")

        # The pixel comparison above is WEAK: around the toolbars the scene is
        # a slow gradient, and blurring a gradient changes almost nothing, so
        # a real leak can pass unnoticed. The documented cause is checked
        # directly instead.
        #
        # MultiEffect.autoPaddingEnabled defaults to true and pads the item by
        # blurMax so the blur has room to spread - Qt's docs warn the effect
        # then "grows outside the window / screen". Every glass surface must
        # turn it off.
        effects = find_all(t.window, "MultiEffect")
        t.note(f"{len(effects)} MultiEffect instance(s) in the scene")
        padded = [e for e in effects if e.property("autoPaddingEnabled")]
        t.check(bool(effects) and not padded,
                f"every MultiEffect has autoPaddingEnabled false "
                f"({len(effects) - len(padded)}/{len(effects)})")

    return (test
            .step(glass_off, 1200)
            .step(capture_off, 300)
            .step(glass_on, 1500)
            .step(compare, 200))


if __name__ == "__main__":
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
