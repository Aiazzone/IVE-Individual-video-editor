"""Two videos placed on the timeline: does play run BOTH, in order?

Reported: "loading one or more videos, play shows only the last one".
This drives the exact flow the user described - new project, import two
videos, place both, press play from the start - and checks the model
(starts must be consecutive, not overlapping), the transport (the sequence
holds both), and what actually plays (the clip under the playhead early on
must be the FIRST video).

    python tests/visual/test_sequence_placement.py
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
    test = VisualTest("sequence_placement", width=1400, height=880)
    videos = sorted(ROOT.glob("*.mp4"))[:2]
    workdir = Path(tempfile.mkdtemp(prefix="ive-placement-"))

    def setup(t: VisualTest):
        if len(videos) < 2:
            t.fail("need two sample videos in the project root")
            return
        t.check(t.app.project.create("placement", str(workdir)), "project open")
        t.app.project.import_paths([str(v) for v in videos])

    def place(t: VisualTest):
        for media in t.app.project.media:
            t.app.project.place_media(media["id"])

    def inspect_model(t: VisualTest):
        placed = clips(t)
        t.check(len(placed) == 2, f"two clips placed ({len(placed)})")
        if len(placed) < 2:
            return
        a, b = placed[0], placed[1]
        t.note(f"clip A: {a['name']} {a['start']:.2f}..{a['end']:.2f}")
        t.note(f"clip B: {b['name']} {b['start']:.2f}..{b['end']:.2f}")
        t.check(abs(b["start"] - a["end"]) < 1e-6,
                "clip B starts where clip A ends - no overlap, no gap")
        t.check(t.app.playback.isSequence, "the transport holds a sequence")
        expected = a["duration"] + b["duration"]
        t.check(abs(t.app.playback.durationSeconds - expected) < 0.5,
                f"the sequence lasts BOTH clips "
                f"({t.app.playback.durationSeconds:.2f}s vs {expected:.2f}s)")

    def play(t: VisualTest):
        t.app.playback.seek_seconds(0.0)
        t.app.playback.play()

    def check_first_clip_plays(t: VisualTest):
        position = t.app.playback.positionSeconds
        name = t.app.playback.currentClipName
        first = clips(t)[0]["name"] if clips(t) else "?"
        t.check(t.app.playback.playing, f"playing ({position:.2f}s)")
        t.check(position < clips(t)[0]["duration"],
                f"still inside clip A's span ({position:.2f}s)")
        t.check(name == first,
                f"what plays first IS the first clip ({name!r} vs {first!r})")
        t.shoot("playing_first")
        t.app.playback.pause()

    # ── the reported bug: drop the new video ONTO the first one ───
    def drop_onto_first(t: VisualTest):
        # A third copy, dropped at 7s: on the RIGHT half of clip A (0..10).
        # The old raw-start sort put any such drop BEFORE clip A, which is
        # why play kept starting with the newest video.
        media = t.app.project.media[0]
        t.app.actions.invoke("timeline.place_media",
                             {"media_id": media["id"], "at": 7.0})

    def drop_check(t: VisualTest):
        placed = clips(t)
        t.check(len(placed) == 3, f"three clips now ({len(placed)})")
        t.check(placed[0]["name"] == videos[0].name
                and abs(placed[0]["start"]) < 1e-6,
                f"clip A is STILL first ({placed[0]['name']} at "
                f"{placed[0]['start']:.2f}s)")
        t.check(abs(placed[1]["start"] - placed[0]["end"]) < 1e-6,
                "the dropped copy landed right after it")

    # ── reorder by dragging with the mouse ────────────────────────
    def drag_reorder(t: VisualTest):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest

        timeline = t.find("TimelinePanel")
        placed = clips(t)
        # The LAST clip (the 20s video, the only one of its duration, so
        # the swap is provable) goes to the front.
        second = placed[2]
        header = 65.0
        lane_w = t.window.width() - header
        duration = t.app.project.timelineDuration
        pps = lane_w / duration
        # Grab the SECOND clip in the middle and drag it left to the very
        # start: its leading edge crosses clip A's midpoint, so they swap.
        y = int(t.window.height() - timeline.height() + 33
                + 64 / 2)                       # toolbar + V1 lane centre
        x_from = int(header + (second["start"] + second["duration"] / 2) * pps)
        x_to = int(header + 5)
        t.note(f"dragging {second['name']} from x={x_from} to x={x_to}")
        QTest.mousePress(t.window, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, QPoint(x_from, y))
        steps = 12
        for i in range(1, steps + 1):
            x = int(x_from + (x_to - x_from) * i / steps)
            QTest.mouseMove(t.window, QPoint(x, y), 18)
        QTest.mouseRelease(t.window, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier, QPoint(x_to, y))

    def drag_check(t: VisualTest):
        placed = clips(t)
        t.check(placed and placed[0]["name"] == videos[1].name
                and abs(placed[0]["start"]) < 1e-6,
                f"the dragged clip is now FIRST "
                f"({placed[0]['name']} {placed[0]['start']:.2f}.."
                f"{placed[0]['end']:.2f})")
        starts_ok = all(abs(placed[i]["start"] - placed[i - 1]["end"]) < 1e-6
                        for i in range(1, len(placed)))
        t.check(starts_ok, "everything reflowed back to back")
        t.shoot("after_drag")

    # ── trim by dragging an edge, and the magnet ──────────────────
    def trim_edge(t: VisualTest):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest

        timeline = t.find("TimelinePanel")
        first = clips(t)[0]
        header = 65.0
        pps = (t.window.width() - header) / t.app.project.timelineDuration
        y = int(t.window.height() - timeline.height() + 33 + 64 / 2)
        # Grab the FIRST clip's right edge (3px inside it) and pull it left
        # by about 5 seconds.
        x_from = int(header + first["end"] * pps - 3)
        x_to = int(header + (first["end"] - 5.0) * pps)
        QTest.mousePress(t.window, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, QPoint(x_from, y))
        for i in range(1, 13):
            x = int(x_from + (x_to - x_from) * i / 12)
            QTest.mouseMove(t.window, QPoint(x, y), 18)
        QTest.mouseRelease(t.window, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier, QPoint(x_to, y))

    def trim_check(t: VisualTest):
        from PySide6.QtCore import QMetaObject, Qt, Q_ARG, Q_RETURN_ARG

        placed = clips(t)
        first = placed[0]
        t.check(abs(first["duration"] - 15.0) < 0.6,
                f"the right edge trimmed the 20s clip to ~15s "
                f"({first['duration']:.2f}s)")
        t.check(all(abs(placed[i]['start'] - placed[i - 1]['end']) < 1e-6
                    for i in range(1, len(placed))),
                "and the timeline reflowed")
        # The magnet itself, on the QML function every handle uses: a time
        # near another clip's edge is pulled exactly onto it.
        timeline = t.find("TimelinePanel")
        boundary = placed[0]["end"]
        result = QMetaObject.invokeMethod(
            timeline, "snapTime", Qt.ConnectionType.DirectConnection,
            Q_RETURN_ARG("QVariant"),
            Q_ARG("QVariant", boundary + 0.12),
            Q_ARG("QVariant", placed[1]["id"]),
            Q_ARG("QVariant", 0.3))
        t.check(result is not None and abs(float(result) - boundary) < 1e-6,
                f"snapTime pulls {boundary + 0.12:.2f}s onto the edge at "
                f"{boundary:.2f}s")
        result = QMetaObject.invokeMethod(
            timeline, "snapTime", Qt.ConnectionType.DirectConnection,
            Q_RETURN_ARG("QVariant"),
            Q_ARG("QVariant", boundary + 2.0),
            Q_ARG("QVariant", placed[1]["id"]),
            Q_ARG("QVariant", 0.3))
        t.check(result is not None and abs(float(result) - boundary - 2.0) < 1e-6,
                "far from any edge the magnet lets go")

    test.step(setup, 1600)
    test.step(place, 1200)
    test.step(inspect_model, 400)
    test.step(play, 1800)
    test.step(check_first_clip_plays, 400)
    test.step(drop_onto_first, 800)
    test.step(drop_check, 400)
    test.step(drag_reorder, 900)
    test.step(drag_check, 500)
    test.step(trim_edge, 900)
    test.step(trim_check, 500)
    return test


if __name__ == "__main__":
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
