"""An audio-only file (music) as a first-class timeline clip.

The pool already accepted mp3/wav; what used to break was everything after:
the transport skipped clips with no video stream, the V1 lane drew a
picture pill for a file with no picture, and Delete on the audio lane
left an invisible zombie. This drives the whole path: import, place,
lanes, playback across the video->music boundary, and Delete semantics.

The fixture is an mp3 when this FFmpeg build can write one, else a wav -
both are in MEDIA_SUFFIXES, and DECODING mp3 is always available, which
is what the user-facing question is about.

    python tests/visual/test_audio_clip.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "tests" / "output"


from harness import VisualTest, _isolate_settings  # noqa: E402


def make_music() -> Path | None:
    """A 2-second stereo tone; mp3 preferred, wav as the safe fallback."""
    import numpy as np

    for suffix, codec in ((".mp3", "libmp3lame"), (".mp3", "mp3"),
                          (".wav", "pcm_s16le")):
        target = OUTPUT / f"music{suffix}"
        if target.is_file():
            return target
        try:
            import av

            OUTPUT.mkdir(parents=True, exist_ok=True)
            container = av.open(str(target), "w")
            stream = container.add_stream(codec, rate=48000)
            tone = (0.4 * np.sin(2 * np.pi * 440
                                 * np.arange(96000) / 48000))
            samples = (tone * 32767).astype(np.int16)
            interleaved = np.repeat(samples, 2).reshape(1, -1)
            chunk = 1152 * 2
            for start in range(0, interleaved.shape[1], chunk):
                part = interleaved[:, start:start + chunk]
                frame = av.AudioFrame.from_ndarray(part, format="s16",
                                                   layout="stereo")
                frame.sample_rate = 48000
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
            container.close()
            return target
        except Exception:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
    return None


def clips(t: VisualTest) -> list:
    value = t.app.project.timelineClips
    return value.toVariant() if hasattr(value, "toVariant") else value


def build() -> VisualTest:
    test = VisualTest("audio_clip", width=1400, height=880)
    sample = sorted(ROOT.glob("*.mp4"))
    video = sample[0] if sample else None
    music = make_music()
    workdir = Path(tempfile.mkdtemp(prefix="ive-audioclip-"))

    def setup(t: VisualTest):
        if video is None or music is None:
            t.fail("fixtures missing (video or encodable music)")
            return
        t.note(f"music fixture: {music.name}")
        t.check(t.app.project.create("audioclip", str(workdir)),
                "a throwaway project opened")
        added = t.app.project.import_paths([str(video), str(music)])
        t.check(added == 2, f"video AND music imported ({added})")

    def place(t: VisualTest):
        for media in t.app.project.media:
            t.app.project.place_media(media["id"])
        t.check(t.app.project.timelineCount == 2, "both placed")
        music_clip = next((c for c in clips(t)
                           if Path(music.name).stem in c["name"]), None)
        t.check(music_clip is not None and music_clip["hasVideo"] is False,
                "the music clip knows it has no picture")
        t.check(music_clip is not None and music_clip["hasAudio"] is True,
                "and that it has sound")

    def play_into_music(t: VisualTest):
        # Start just before the video->music boundary (video is 10s).
        t.app.playback.seek_seconds(9.5)
        t.app.playback.play()

    def crossed(t: VisualTest):
        position = t.app.playback.positionSeconds
        t.check(t.app.playback.playing,
                f"playback survived crossing into the music ({position:.2f}s)")
        t.check(position > 10.2,
                f"the playhead is inside the music clip ({position:.2f}s)")
        t.app.playback.pause()
        t.shoot("music_on_timeline")

    def delete_music(t: VisualTest):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt

        item = t.find("TimelinePanel")
        music_clip = next((c for c in clips(t)
                           if Path(music.name).stem in c["name"]), None)
        item.setProperty("selectedClipId", music_clip["id"])
        item.setProperty("selectedKind", "audio")
        QTest.keyClick(t.window, Qt.Key.Key_Delete)

    def delete_check(t: VisualTest):
        t.check(t.app.project.timelineCount == 1,
                f"Delete on a music clip removes the CLIP, not just its "
                f"sound - no invisible zombie ({t.app.project.timelineCount})")

    test.step(setup, 1600)
    test.step(place, 1000)
    test.step(play_into_music, 2200)
    test.step(crossed, 500)
    test.step(delete_music, 700)
    test.step(delete_check, 500)
    return test


if __name__ == "__main__":
    _isolate_settings()
    t = build()
    t.run()
    t.report()
    sys.exit(0 if not t.failures else 1)
