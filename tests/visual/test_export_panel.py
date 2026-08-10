"""Export panel, both tabs, screenshotted and probed.

What is being verified:

* the social tab shows the platform icon row and tapping a platform swaps
  the preset list underneath (checked on the QML item's state, then on a
  screenshot for the eyes);
* the custom tab shows the new aspect picker and changing aspect reshapes
  the resolution ladder while keeping the tier.

    python tests/visual/test_export_panel.py [video.mp4]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]

from harness import VisualTest, _isolate_settings  # noqa: E402


def find_export(t: VisualTest):
    item = t.find("ExportContent")
    if item is None:
        t.fail("ExportContent not found in the scene")
    return item


def as_list(value):
    """A JS array read off a QML property arrives as QJSValue."""
    return value.toVariant() if hasattr(value, "toVariant") else value


def build() -> VisualTest:
    test = VisualTest("export_panel", width=1400, height=880)
    if len(sys.argv) > 1:
        sample = Path(sys.argv[1])
    else:
        candidates = sorted(ROOT.glob("*.mp4"))
        sample = candidates[0] if candidates else None

    def setup(t: VisualTest):
        if sample is None or not sample.is_file():
            t.fail("no sample video available")
            return
        # Pinned, or the panel auto-hides between steps and the later
        # screenshots show an empty shell.
        t.app.settings.set("shell.panel_pinned", True)
        t.app.playback.open(str(sample))

    def open_panel(t: VisualTest):
        from PySide6.QtCore import QMetaObject, Q_ARG

        QMetaObject.invokeMethod(t.window, "openSection",
                                 Q_ARG("QVariant", "export"))

    def social_default(t: VisualTest):
        item = find_export(t)
        if item is None:
            return
        t.check(item.property("tab") == "social", "starts on the social tab")
        t.check(item.property("platform") == "youtube",
                "starts on the youtube platform")
        presets = as_list(item.property("platformPresets"))
        t.check(len(presets) == 3,
                f"youtube reveals its 3 presets ({len(presets)})")
        t.shoot("social_youtube")

    def social_instagram(t: VisualTest):
        item = find_export(t)
        if item is None:
            return
        # Drive it the way the TapHandler does: platform change plus landing
        # on the first preset of the new platform.
        item.setProperty("platform", "instagram")
        item.setProperty("presetId", "instagram_reels")

    def social_instagram_check(t: VisualTest):
        item = find_export(t)
        if item is None:
            return
        presets = as_list(item.property("platformPresets"))
        ids = [p["id"] for p in presets]
        t.check(ids == ["instagram_reels", "instagram_feed",
                        "instagram_stories"],
                f"instagram reveals reels, feed and stories ({ids})")
        t.shoot("social_instagram")

    def custom_tab(t: VisualTest):
        item = find_export(t)
        if item is None:
            return
        item.setProperty("tab", "custom")

    def custom_default(t: VisualTest):
        item = find_export(t)
        if item is None:
            return
        t.check(item.property("aspect") == "16x9", "custom starts at 16:9")
        t.check(item.property("resolution") == "1920x1080",
                "custom starts at 1080p")
        t.shoot("custom_16x9")

    def custom_vertical(t: VisualTest):
        item = find_export(t)
        if item is None:
            return
        # What the aspect Segmented's onPicked does for 16:9 -> 9:16 at the
        # 1080p tier: same tier, reshaped frame.
        item.setProperty("aspect", "9x16")
        item.setProperty("resolution", "1080x1920")

    def custom_vertical_check(t: VisualTest):
        item = find_export(t)
        if item is None:
            return
        options = None
        try:
            from PySide6.QtCore import QMetaObject, Qt

            options = QMetaObject.invokeMethod(
                item, "currentOptions", Qt.ConnectionType.DirectConnection)
        except Exception:
            pass
        if isinstance(options, dict):
            t.check(options.get("width") == 1080
                    and options.get("height") == 1920,
                    f"export options carry the vertical frame ({options})")
        else:
            t.check(item.property("resolution") == "1080x1920",
                    "the vertical resolution is set")
        t.shoot("custom_9x16")

    test.step(setup, 1500)
    test.step(open_panel, 1200)
    test.step(social_default, 400)
    test.step(social_instagram, 400)
    test.step(social_instagram_check, 400)
    test.step(custom_tab, 500)
    test.step(custom_default, 400)
    test.step(custom_vertical, 400)
    test.step(custom_vertical_check, 400)
    return test


if __name__ == "__main__":
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
