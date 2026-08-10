"""The Color panel and the Color lane, on the running shell.

Covers: the panel opens with the section cards (it used to be empty), a
section shows the per-effect thumbnails, placing an effect grows a pink
clip on a new "Color" lane, the PREVIEW is really graded (noir = grayscale
centre pixel), and Delete removes the effect clip taking the lane with it.

    python tests/visual/test_color_panel.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]

from harness import VisualTest, _isolate_settings  # noqa: E402


def clips(t: VisualTest) -> list:
    value = t.app.project.timelineClips
    return value.toVariant() if hasattr(value, "toVariant") else value


def build() -> VisualTest:
    test = VisualTest("color_panel", width=1400, height=880)
    sample = sorted(ROOT.glob("*.mp4"))
    video = sample[0] if sample else None
    workdir = Path(tempfile.mkdtemp(prefix="ive-color-"))

    def setup(t: VisualTest):
        if video is None:
            t.fail("no sample video")
            return
        t.app.settings.set("shell.panel_pinned", True)
        t.check(t.app.project.create("colorfx", str(workdir)), "project open")
        t.app.project.import_paths([str(video)])

    def place(t: VisualTest):
        for media in t.app.project.media:
            t.app.project.place_media(media["id"])
        sections = t.app.colorfx.sections
        t.check(len(sections) == 4,
                f"the catalogue reaches QML ({len(sections)} sections)")

    def open_panel(t: VisualTest):
        from PySide6.QtCore import QMetaObject, Q_ARG

        QMetaObject.invokeMethod(t.window, "openSection",
                                 Q_ARG("QVariant", "color"))

    def sections_shot(t: VisualTest):
        item = t.find("ColorContent")
        t.check(item is not None, "the Color panel is no longer empty")
        t.shoot("sections")
        if item is not None:
            item.setProperty("section", "cinema")

    def looks_shot(t: VisualTest):
        t.shoot("cinema_looks")

    def apply_noir(t: VisualTest):
        first = clips(t)[0]
        t.app.actions.invoke("timeline.place_effect", {
            "effect_id": "noir",
            "at": first["start"],
            "duration": first["duration"],
        })

    def lane_check(t: VisualTest):
        placed = clips(t)
        fx = [c for c in placed if c["track"] == 1]
        t.check(len(fx) == 1, f"the effect clip exists ({len(fx)})")
        t.check(fx and fx[0]["effectId"] == "noir"
                and fx[0]["name"] == "Noir",
                "and it knows which look it is")
        # Park mid-clip and look at the picture: noir means grayscale.
        t.app.playback.seek_seconds(2.0)

    def graded_preview(t: VisualTest):
        image = t.shoot("noir_applied")
        x = image.width() // 2
        y = int(image.height() * 0.4)
        rgb = t.pixel(image, x, y)
        spread = max(rgb) - min(rgb)
        t.check(spread <= 6,
                f"the PREVIEW is graded: noir centre pixel is grey "
                f"({t.hexof(rgb)}, spread {spread})")

    # ── the real gesture: drag a thumbnail onto the video track ───
    def drag_thumbnail(t: VisualTest):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtTest import QTest

        from PySide6.QtCore import QObject

        card = t.window.findChild(QObject, "colorLook_teal_orange")
        if card is None:
            # QML delegates hang off childItems(), which does not always
            # mirror the QObject children() tree findChild walks.
            panel = t.find("ColorContent")

            def hunt(item):
                for child in item.childItems():
                    if child.objectName() == "colorLook_teal_orange":
                        return child
                    found = hunt(child)
                    if found is not None:
                        return found
                return None
            card = hunt(panel) if panel is not None else None
        if card is None:
            t.fail("teal_orange thumbnail not found in the panel")
            return
        start = card.mapToScene(QPointF(52, 30))
        timeline = t.find("TimelinePanel")
        target_y = int(t.window.height() - timeline.height() + 33 + 32)
        target_x = int(t.window.width() * 0.3)
        QTest.mousePress(t.window, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier,
                         QPoint(int(start.x()), int(start.y())))
        steps = 14
        for i in range(1, steps + 1):
            x = int(start.x() + (target_x - start.x()) * i / steps)
            y = int(start.y() + (target_y - start.y()) * i / steps)
            QTest.mouseMove(t.window, QPoint(x, y), 16)
        QTest.mouseRelease(t.window, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier,
                           QPoint(target_x, target_y))

    def drag_thumbnail_check(t: VisualTest):
        fx = [c for c in clips(t) if c["track"] == 1]
        t.check(len(fx) == 2,
                f"the DRAG GESTURE placed a second effect ({len(fx)})")
        t.check(any(c["effectId"] == "teal_orange" for c in fx),
                "and it is the dragged look")
        # Dropped over the video clip, so it adopted its exact span.
        teal = next((c for c in fx if c["effectId"] == "teal_orange"), None)
        video_clip = clips(t)[0]
        t.check(teal is not None
                and abs(teal["start"] - video_clip["start"]) < 1e-6
                and abs(teal["duration"] - video_clip["duration"]) < 1e-6,
                "the drop adopted the video clip's span")
        # Clean it up so the noir checks below stay untouched.
        t.app.project.remove_clip(teal["id"])

    # ── favourites: star with a real click, gather in the tab ─────
    def hunt_object(t: VisualTest, name):
        panel = t.find("ColorContent")

        def walk(item):
            for child in item.childItems():
                if child.objectName() == name:
                    return child
                found = walk(child)
                if found is not None:
                    return found
            return None
        return walk(panel) if panel is not None else None

    def star_click(t: VisualTest):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtTest import QTest

        favs = list(t.app.colorfx.favorites)
        t.check(favs == [], f"no favourites at first ({favs})")
        star = hunt_object(t, "star_noir")
        if star is None:
            t.fail("the star on the noir thumbnail was not found")
            return
        centre = star.mapToScene(QPointF(11, 11))
        QTest.mouseClick(t.window, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier,
                         QPoint(int(centre.x()), int(centre.y())))

    def star_check(t: VisualTest):
        favs = list(t.app.colorfx.favorites)
        t.check(favs == ["noir"], f"the CLICK starred the effect ({favs})")
        t.shoot("starred")
        panel = t.find("ColorContent")
        panel.setProperty("tab", "favorites")

    def favorites_tab(t: VisualTest):
        panel = t.find("ColorContent")
        grid = panel.property("gridEffects")
        grid = grid.toVariant() if hasattr(grid, "toVariant") else grid
        t.check(len(grid) == 1 and grid[0]["id"] == "noir",
                f"the Favorites tab shows exactly the starred effect")
        t.shoot("favorites_tab")
        # Unstar via the same action the star invokes; back to colors.
        t.app.actions.invoke("color.toggle_favorite", {"effect_id": "noir"})

    def unstarred(t: VisualTest):
        favs = list(t.app.colorfx.favorites)
        t.check(favs == [], f"a second toggle unstars ({favs})")
        panel = t.find("ColorContent")
        panel.setProperty("tab", "colors")

    def delete_effect(t: VisualTest):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt

        item = t.find("TimelinePanel")
        fx = [c for c in clips(t) if c["track"] == 1][0]
        item.setProperty("selectedClipId", fx["id"])
        item.setProperty("selectedKind", "color")
        QTest.keyClick(t.window, Qt.Key.Key_Delete)

    def deleted(t: VisualTest):
        fx = [c for c in clips(t) if c["track"] == 1]
        t.check(len(fx) == 0, "Delete removed the effect clip")

    test.step(setup, 1600)
    test.step(place, 1000)
    test.step(open_panel, 900)
    test.step(sections_shot, 1600)
    test.step(looks_shot, 1800)
    test.step(apply_noir, 900)
    test.step(lane_check, 1200)
    test.step(graded_preview, 600)
    test.step(drag_thumbnail, 900)
    test.step(drag_thumbnail_check, 600)
    test.step(star_click, 600)
    test.step(star_check, 600)
    test.step(favorites_tab, 700)
    test.step(unstarred, 500)
    test.step(delete_effect, 700)
    test.step(deleted, 400)
    return test


if __name__ == "__main__":
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
