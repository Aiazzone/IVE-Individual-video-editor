"""Three interaction requests, verified on the running shell.

1. Option switches sit BEFORE their label (SwitchRow), not under it.
2. The timeline zooms: zoomBy() drives the same path as the wheel and the
   toolbar buttons; zoomed content pans and follows the playhead.
3. Space toggles play/pause app-wide - even after a click moved focus - but
   NEVER while a text field is being typed in.

    python tests/visual/test_ui_interactions.py [video.mp4]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]

from harness import VisualTest, _isolate_settings  # noqa: E402


def build() -> VisualTest:
    test = VisualTest("ui_interactions", width=1400, height=880)
    if len(sys.argv) > 1:
        sample = Path(sys.argv[1])
    else:
        candidates = sorted(ROOT.glob("*.mp4"))
        sample = candidates[0] if candidates else None

    def setup(t: VisualTest):
        if sample is None or not sample.is_file():
            t.fail("no sample video available")
            return
        t.app.settings.set("shell.panel_pinned", True)
        t.app.playback.open(str(sample))

    # ── 1. switches lead their labels ─────────────────────────────
    def open_settings(t: VisualTest):
        from PySide6.QtCore import QMetaObject, Q_ARG

        QMetaObject.invokeMethod(t.window, "openSection",
                                 Q_ARG("QVariant", "settings"))

    def settings_appearance(t: VisualTest):
        item = t.find("SettingsContent")
        if item is None:
            t.fail("SettingsContent not found")
            return
        item.setProperty("tab", "appearance")

    def switches_check(t: VisualTest):
        row = t.find("SwitchRow")
        t.check(row is not None, "SwitchRow is in the scene")
        if row is not None:
            switch = t.find("AppSwitch", row)
            t.check(switch is not None and switch.property("x") == 0,
                    "the switch is the FIRST thing on its row (x == 0)")
        t.shoot("settings_switches")

    def close_settings(t: VisualTest):
        from PySide6.QtCore import QMetaObject, Q_ARG

        QMetaObject.invokeMethod(t.window, "openSection",
                                 Q_ARG("QVariant", "settings"))

    # ── 2. timeline zoom ──────────────────────────────────────────
    def zoom_in(t: VisualTest):
        from PySide6.QtCore import QMetaObject, Q_ARG

        timeline = t.find("TimelinePanel")
        if timeline is None:
            t.fail("TimelinePanel not found")
            return
        t.check(float(timeline.property("zoom")) == 1.0, "zoom starts at 1")
        QMetaObject.invokeMethod(timeline, "zoomBy",
                                 Q_ARG("QVariant", 4.0),
                                 Q_ARG("QVariant", 300.0))

    def zoom_check(t: VisualTest):
        timeline = t.find("TimelinePanel")
        flick = t.find("Flickable", timeline)
        zoom = float(timeline.property("zoom"))
        t.check(zoom == 4.0, f"zoomBy(4) took the zoom to 4 ({zoom})")
        if flick is not None:
            ratio = flick.property("contentWidth") / max(1.0, flick.width())
            t.check(abs(ratio - 4.0) < 0.01,
                    f"the lane content is 4x the viewport ({ratio:.2f})")
        # The playhead follower: park the playhead near the end (the sample
        # videos are 10s) and the view must chase it.
        t.app.playback.seek_seconds(9.0)

    def follow_check(t: VisualTest):
        timeline = t.find("TimelinePanel")
        flick = t.find("Flickable", timeline)
        if flick is not None:
            t.check(flick.property("contentX") > 0,
                    f"the zoomed view followed the playhead "
                    f"(contentX {flick.property('contentX'):.0f})")
        t.shoot("timeline_zoomed")

    def zoom_out_clamp(t: VisualTest):
        from PySide6.QtCore import QMetaObject, Q_ARG

        timeline = t.find("TimelinePanel")
        QMetaObject.invokeMethod(timeline, "zoomBy",
                                 Q_ARG("QVariant", 0.01),
                                 Q_ARG("QVariant", 300.0))

    def clamp_check(t: VisualTest):
        timeline = t.find("TimelinePanel")
        flick = t.find("Flickable", timeline)
        t.check(float(timeline.property("zoom")) == 1.0,
                "zooming far out clamps back to 1 (fit)")
        if flick is not None:
            t.check(flick.property("contentX") == 0,
                    "at fit the view is back at the start")

    # ── 3. space toggles playback ─────────────────────────────────
    def space_play(t: VisualTest):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt

        t.check(not t.app.playback.playing, "starts paused")
        QTest.keyClick(t.window, Qt.Key.Key_Space)

    def space_played(t: VisualTest):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt

        t.check(t.app.playback.playing, "Space started playback")
        QTest.keyClick(t.window, Qt.Key.Key_Space)

    def space_paused(t: VisualTest):
        from PySide6.QtCore import QMetaObject, Q_ARG

        t.check(not t.app.playback.playing, "Space again paused it")
        # Now the counter-case: typing in a text field must NOT toggle.
        QMetaObject.invokeMethod(t.window, "openSection",
                                 Q_ARG("QVariant", "export"))

    def space_in_text_field(t: VisualTest):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt, QMetaObject

        export = t.find("ExportContent")
        field = t.find("TextInput", export) if export is not None else None
        if field is None:
            t.fail("the export file-name field was not found")
            return
        QMetaObject.invokeMethod(field, "forceActiveFocus")
        QTest.keyClick(t.window, Qt.Key.Key_T)
        QTest.keyClick(t.window, Qt.Key.Key_Space)
        QTest.keyClick(t.window, Qt.Key.Key_V)
        t.check(not t.app.playback.playing,
                "typing a space in the file-name field did not toggle playback")
        t.check(str(field.property("text")) == "t v",
                f"the field received the typed text ({field.property('text')!r})")

    test.step(setup, 1400)
    test.step(open_settings, 900)
    test.step(settings_appearance, 500)
    test.step(switches_check, 400)
    test.step(close_settings, 500)
    test.step(zoom_in, 500)
    test.step(zoom_check, 600)
    test.step(follow_check, 400)
    test.step(zoom_out_clamp, 400)
    test.step(clamp_check, 400)
    test.step(space_play, 700)
    test.step(space_played, 700)
    test.step(space_paused, 900)
    test.step(space_in_text_field, 500)
    return test


if __name__ == "__main__":
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
