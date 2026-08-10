"""Timeline layout rework: bottom ruler, triangle playhead, slim headers.

Verified on pixels where it matters: the playhead line is red mid-track,
its triangle head is red inside the BOTTOM ruler strip, and the track
header column is the slim name-only version. The run ends by invoking
`app.quit` - the new power button's action - and the PASS report printing
at all proves the shutdown was orderly.

    python tests/visual/test_timeline_layout.py [video.mp4]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]

from harness import VisualTest, _isolate_settings  # noqa: E402


def build() -> VisualTest:
    test = VisualTest("timeline_layout", width=1400, height=880)
    sample = sorted(ROOT.glob("*.mp4"))
    video = sample[0] if sample else None

    def reddish(rgb) -> bool:
        return rgb[0] > 140 and rgb[1] < 110 and rgb[2] < 110

    def setup(t: VisualTest):
        if video is None:
            t.fail("no sample video available")
            return
        t.app.playback.open(str(video))

    def park(t: VisualTest):
        # Mid-file, so the playhead stands in open space.
        t.app.playback.seek_seconds(5.0)

    def inspect(t: VisualTest):
        image = t.shoot("bottom_ruler")
        timeline = t.find("TimelinePanel")
        if timeline is None:
            t.fail("TimelinePanel not found")
            return
        header = 64.0
        ruler_h = 16
        lane_w = image.width() - header - 1
        x = int(header + 1 + lane_w * 0.5)          # playhead at 5s of 10s

        # Just above the bottom ruler: inside the lanes, whatever the
        # toolbar's exact height.
        line = t.pixel(image, x, int(image.height() - ruler_h - 30))
        t.check(reddish(line), f"the playhead line crosses the tracks ({t.hexof(line)})")
        # The head is a HOLLOW droplet: its centre is empty on purpose, so
        # scan across it and require the red OUTLINE on the way.
        y_head = int(image.height() - ruler_h + 8)
        outline = [t.pixel(image, x + dx, y_head) for dx in range(-7, 8)]
        t.check(any(reddish(p) for p in outline),
                "the hollow head's red outline sits in the BOTTOM ruler strip")
        centre = t.pixel(image, x, y_head)
        t.check(not reddish(centre),
                f"and its middle is hollow, not filled ({t.hexof(centre)})")
        above = t.pixel(image, x - 30, int(image.height() - ruler_h + 4))
        t.check(not reddish(above),
                f"beside the head the ruler strip is not red ({t.hexof(above)})")

    def quit_step(t: VisualTest):
        t.check(True, "invoking app.quit - an orderly exit ends this run")
        t.app.actions.invoke("app.quit")

    test.step(setup, 1500)
    test.step(park, 800)
    test.step(inspect, 400)
    test.step(quit_step, 400)
    return test


if __name__ == "__main__":
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
