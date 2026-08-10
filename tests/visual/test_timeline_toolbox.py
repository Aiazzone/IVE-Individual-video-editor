"""The contextual timeline toolbox, on the running shell.

Covers, in order: no selection = no buttons; selecting a video clip shows
split/delete (screenshot); split at the playhead really cuts the model in
two; selecting the audio lane shows the volume tools (screenshot) and the
volume actions land in the model; the Delete key removes the selected clip
but NEVER while a text field is being typed in; the fit button returns the
zoomed view to "everything visible".

The project lives in a throwaway temp folder - never the user's.

    python tests/visual/test_timeline_toolbox.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]

from harness import VisualTest, _isolate_settings  # noqa: E402


def timeline(t: VisualTest):
    item = t.find("TimelinePanel")
    if item is None:
        t.fail("TimelinePanel not found")
    return item


def clips(t: VisualTest) -> list:
    value = t.app.project.timelineClips
    return value.toVariant() if hasattr(value, "toVariant") else value


def build() -> VisualTest:
    test = VisualTest("timeline_toolbox", width=1400, height=880)
    sample = sorted(ROOT.glob("*.mp4"))
    video = sample[0] if sample else None
    tone = ROOT / "tests" / "output" / "tone.mp4"
    workdir = Path(tempfile.mkdtemp(prefix="ive-toolbox-"))

    def setup(t: VisualTest):
        if video is None or not tone.is_file():
            t.fail("fixtures missing (root mp4 or tests/output/tone.mp4)")
            return
        t.app.settings.set("shell.panel_pinned", True)
        t.check(t.app.project.create("toolbox", str(workdir)),
                "a throwaway project opened")
        t.app.project.import_paths([str(video), str(tone)])

    def place(t: VisualTest):
        for media in t.app.project.media:
            t.app.project.place_media(media["id"])
        t.check(t.app.project.timelineCount == 2,
                f"two clips on the timeline ({t.app.project.timelineCount})")

    def no_selection(t: VisualTest):
        item = timeline(t)
        if item is None:
            return
        t.check(item.property("selectedClipId") == "",
                "nothing is selected at first")
        t.shoot("no_selection")

    def select_video(t: VisualTest):
        item = timeline(t)
        first = clips(t)[0]
        item.setProperty("selectedClipId", first["id"])
        item.setProperty("selectedKind", "video")
        # Park the playhead mid-clip, where the split button wants it.
        t.app.playback.seek_seconds(first["start"] + first["duration"] / 2)

    def video_selected(t: VisualTest):
        t.shoot("video_selected")
        item = timeline(t)
        t.check(item.property("selectedClipData") is not None,
                "the selection resolves to live clip data")

    def split(t: VisualTest):
        first = clips(t)[0]
        t.app.actions.invoke("timeline.split_clip", {
            "clip_id": first["id"],
            "at": first["start"] + first["duration"] / 2,
        })

    def split_check(t: VisualTest):
        t.check(t.app.project.timelineCount == 3,
                f"the split made two clips of one "
                f"({t.app.project.timelineCount})")

    def select_audio(t: VisualTest):
        item = timeline(t)
        # tone.mp4 is the clip with sound; find it by its media name.
        tone_clip = next((c for c in clips(t) if "tone" in c["name"]), None)
        if tone_clip is None:
            t.fail("no audio-capable clip found")
            return
        item.setProperty("selectedClipId", tone_clip["id"])
        item.setProperty("selectedKind", "audio")

    def audio_selected(t: VisualTest):
        t.shoot("audio_selected")
        tone_clip = next((c for c in clips(t) if "tone" in c["name"]), None)
        t.app.actions.invoke("timeline.set_clip_volume",
                             {"clip_id": tone_clip["id"], "volume": 0.5})

    def volume_check(t: VisualTest):
        tone_clip = next((c for c in clips(t) if "tone" in c["name"]), None)
        t.check(tone_clip is not None and abs(tone_clip["volume"] - 0.5) < 1e-6,
                f"the volume action landed in the model "
                f"({tone_clip['volume'] if tone_clip else '?'})")
        t.app.actions.invoke("timeline.set_clip_muted",
                             {"clip_id": tone_clip["id"], "muted": True})

    def mute_check(t: VisualTest):
        tone_clip = next((c for c in clips(t) if "tone" in c["name"]), None)
        t.check(tone_clip is not None and tone_clip["muted"] is True
                and abs(tone_clip["volume"] - 0.5) < 1e-6,
                "muting is a state; the volume stayed put")
        t.shoot("audio_muted")
        t.app.actions.invoke("timeline.set_clip_muted",
                             {"clip_id": tone_clip["id"], "muted": False})

    def unmute_check(t: VisualTest):
        tone_clip = next((c for c in clips(t) if "tone" in c["name"]), None)
        t.check(tone_clip is not None and tone_clip["muted"] is False
                and abs(tone_clip["volume"] - 0.5) < 1e-6,
                "unmuting brings the same loudness back")

    # ── the Delete key: on AUDIO it takes only the sound ──────────
    def delete_key(t: VisualTest):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt

        t.check(t.app.project.timelineCount == 3, "three clips before Delete")
        QTest.keyClick(t.window, Qt.Key.Key_Delete)

    def audio_delete_check(t: VisualTest):
        item = timeline(t)
        tone_clip = next((c for c in clips(t) if "tone" in c["name"]), None)
        t.check(t.app.project.timelineCount == 3,
                f"Delete on the audio lane did NOT remove the clip "
                f"({t.app.project.timelineCount})")
        t.check(tone_clip is not None and tone_clip["audioEnabled"] is False,
                "it removed only the clip's sound")
        t.check(item.property("selectedClipId") == "",
                "the selection cleared with it")
        t.shoot("audio_removed")
        # Restore, the way the video-selection button does it.
        t.app.actions.invoke("timeline.set_clip_audio",
                             {"clip_id": tone_clip["id"], "enabled": True})

    def restore_check(t: VisualTest):
        tone_clip = next((c for c in clips(t) if "tone" in c["name"]), None)
        t.check(tone_clip is not None and tone_clip["audioEnabled"] is True
                and abs(tone_clip["volume"] - 0.5) < 1e-6,
                "restore brings the audio back with its remembered volume")

    # ── the Delete key: on VIDEO it takes the whole clip ──────────
    def delete_video(t: VisualTest):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt

        item = timeline(t)
        tone_clip = next((c for c in clips(t) if "tone" in c["name"]), None)
        item.setProperty("selectedClipId", tone_clip["id"])
        item.setProperty("selectedKind", "video")
        QTest.keyClick(t.window, Qt.Key.Key_Delete)

    def delete_check(t: VisualTest):
        from PySide6.QtCore import QMetaObject, Q_ARG

        item = timeline(t)
        t.check(t.app.project.timelineCount == 2,
                f"Delete on the video lane removed the clip "
                f"({t.app.project.timelineCount})")
        # Counter-case: select a clip, then type in a text field - Backspace
        # must edit the text, not kill the clip.
        item.setProperty("selectedClipId", clips(t)[0]["id"])
        item.setProperty("selectedKind", "video")
        QMetaObject.invokeMethod(t.window, "openSection",
                                 Q_ARG("QVariant", "export"))

    def backspace_in_field(t: VisualTest):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt, QMetaObject

        export = t.find("ExportContent")
        field = t.find("TextInput", export) if export is not None else None
        if field is None:
            t.fail("the export file-name field was not found")
            return
        QMetaObject.invokeMethod(field, "forceActiveFocus")
        QTest.keyClick(t.window, Qt.Key.Key_A)
        QTest.keyClick(t.window, Qt.Key.Key_B)
        QTest.keyClick(t.window, Qt.Key.Key_Backspace)
        t.check(t.app.project.timelineCount == 2,
                "Backspace in a text field left the timeline alone")
        t.check(str(field.property("text")) == "a",
                f"and edited the text instead ({field.property('text')!r})")

    # ── fit ───────────────────────────────────────────────────────
    def fit(t: VisualTest):
        from PySide6.QtCore import QMetaObject, Q_ARG

        item = timeline(t)
        QMetaObject.invokeMethod(item, "zoomBy",
                                 Q_ARG("QVariant", 6.0), Q_ARG("QVariant", 200.0))
        QMetaObject.invokeMethod(item, "fitAll")

    def fit_check(t: VisualTest):
        item = timeline(t)
        flick = t.find("Flickable", item)
        t.check(float(item.property("zoom")) == 1.0, "fitAll returns to zoom 1")
        if flick is not None:
            t.check(flick.property("contentX") == 0, "and to the start")

    # ── pool thumbnails ───────────────────────────────────────────
    def thumbnails(t: VisualTest):
        from PySide6.QtCore import QMetaObject, Q_ARG

        # First ask queues the job on the worker; the URL lands shortly.
        t.app.thumbs.thumb(str(video))
        QMetaObject.invokeMethod(t.window, "openSection",
                                 Q_ARG("QVariant", "project"))

    def thumbnails_shot(t: VisualTest):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QImage

        url = t.app.thumbs.thumb(str(video))
        t.check(url.startswith("file:///"),
                f"the worker produced a thumbnail FILE ({url[:40]}...)")
        if url:
            image = QImage(QUrl(url).toLocalFile())
            t.check(image.width() > 1, f"and it decodes ({image.width()}px)")
            centre = image.pixelColor(image.width() // 2, image.height() // 2)
            t.check(centre.red() + centre.green() + centre.blue() > 0,
                    "and it is a picture, not black")
        t.shoot("media_pool")

    test.step(setup, 1600)
    test.step(place, 900)
    test.step(no_selection, 400)
    test.step(select_video, 500)
    test.step(video_selected, 400)
    test.step(split, 700)
    test.step(split_check, 400)
    test.step(select_audio, 500)
    test.step(audio_selected, 600)
    test.step(volume_check, 500)
    test.step(mute_check, 500)
    test.step(unmute_check, 500)
    test.step(delete_key, 700)
    test.step(audio_delete_check, 700)
    test.step(restore_check, 400)
    test.step(delete_video, 700)
    test.step(delete_check, 900)
    test.step(backspace_in_field, 500)
    test.step(fit, 400)
    test.step(fit_check, 400)
    test.step(thumbnails, 1500)
    test.step(thumbnails_shot, 1200)
    return test


if __name__ == "__main__":
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
