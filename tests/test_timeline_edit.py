"""Timeline editing primitives: split, per-clip volume, and their plumbing.

What is covered, bottom-up:
* the MODEL: split_clip cuts in place (second half continues the source via
  source_in), refuses edge misclicks, and volume clamps to [0, 2];
* SERIALISATION: the new fields survive a round-trip and old documents
  without them load with defaults;
* the ENGINE: GainFilter scales sound without forcing the picture, and a
  clip's volume reaches the produced frames through the graph builder.

    python tests/test_timeline_edit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ive" / "src"))

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    print(f"  {'OK  ' if condition else 'FAIL'} {message}")
    if not condition:
        failures.append(message)


def test_model() -> None:
    from ive.core.model.project import Project, MediaItem, TimelineClip

    print("\n--- the model: split and volume ---")
    project = Project(name="t", folder="")
    media = project.add_media(MediaItem(path="a.mp4", duration=10.0))
    clip = project.add_clip(media.id, 10.0)

    second = project.split_clip(clip.id, 4.0)
    check(second is not None, "a mid-clip split succeeds")
    check(clip.duration == 4.0 and second.start == 4.0
          and second.duration == 6.0,
          f"the halves cover the original span exactly "
          f"({clip.duration}+{second.duration})")
    check(second.source_in == 4.0,
          f"the second half continues the source ({second.source_in})")
    check(project.timeline_duration == 10.0, "nothing moved")

    third = project.split_clip(second.id, 4.02)
    check(third is None, "a cut a hair from the edge is refused (misclick)")
    check(project.split_clip("nope", 1.0) is None, "unknown clip refused")

    project.set_clip_volume(second.id, 0.5)
    check(second.volume == 0.5, "volume set")
    project.set_clip_volume(second.id, 99.0)
    check(second.volume == 2.0, "volume clamps high")
    project.set_clip_volume(second.id, -1.0)
    check(second.volume == 0.0, "volume clamps low")

    # A split inherits the first half's volume.
    project.set_clip_volume(clip.id, 0.7)
    half = project.split_clip(clip.id, 2.0)
    check(half is not None and half.volume == 0.7,
          "a split inherits the clip's volume")

    # Removing the audio is NOT removing the clip, and NOT losing the volume.
    check(project.set_clip_audio(second.id, False), "audio removed")
    check(second.audio_enabled is False and second.duration == 6.0,
          "the clip itself is untouched")
    project.set_clip_volume(second.id, 0.8)
    project.set_clip_audio(second.id, True)
    check(second.audio_enabled is True and second.volume == 0.8,
          "restoring the audio brings the remembered volume back")
    project.set_clip_audio(second.id, False)
    muted_half = project.split_clip(second.id, second.start + 2.0)
    check(muted_half is not None and muted_half.audio_enabled is False,
          "a split inherits removed audio too")

    # Muted is a state, not volume 0: the loudness survives the round trip.
    project.set_clip_volume(clip.id, 0.6)
    check(project.set_clip_muted(clip.id, True), "clip muted")
    check(clip.muted is True and clip.volume == 0.6,
          "muting leaves the volume untouched")
    project.set_clip_muted(clip.id, False)
    check(clip.muted is False and clip.volume == 0.6,
          "unmuting brings the same loudness back")
    project.set_clip_muted(clip.id, True)
    muted_split = project.split_clip(clip.id, clip.start + 1.0)
    check(muted_split is not None and muted_split.muted is True,
          "a split inherits the muted state")

    print("\n--- placement: the midpoint rule ---")
    p2 = Project(name="mid", folder="")
    m2 = p2.add_media(MediaItem(path="b.mp4", duration=10.0))
    first = p2.add_clip(m2.id, 10.0)
    # Dropping the NEW clip on the RIGHT half of the existing one puts it
    # AFTER - the reported bug: any drop over the first clip used to land
    # BEFORE it, so play always started with the newest video.
    after = p2.add_clip(m2.id, 4.0, at=7.0)
    order = [c.id for c in p2.ordered_clips()]
    check(order == [first.id, after.id],
          "a drop past the middle of a clip lands after it")
    # And on the LEFT half it goes in front - that part is intentional.
    before = p2.add_clip(m2.id, 2.0, at=1.0)
    order = [c.id for c in p2.ordered_clips()]
    check(order[0] == before.id,
          "a drop before the middle of the first clip lands in front")
    starts = [c.start for c in p2.ordered_clips()]
    check(starts == [0.0, 2.0, 12.0], f"clips lie back to back ({starts})")

    # Reordering by drag: crossing the neighbour's middle swaps, a nudge
    # does not.
    p2.move_clip(before.id, 1.0)
    check([c.id for c in p2.ordered_clips()][0] == before.id,
          "a small nudge does not reorder")
    p2.move_clip(before.id, 6.0)   # centre 7 > first's midpoint (2+5=7)? ...
    order = [c.id for c in p2.ordered_clips()]
    check(order[0] == first.id and order[1] == before.id,
          "dragging past the neighbour's middle swaps the two")

    print("\n--- trim: clamped to the source ---")
    p3 = Project(name="trim", folder="")
    m3 = p3.add_media(MediaItem(path="c.mp4", duration=10.0))
    t1 = p3.add_clip(m3.id, 10.0)
    t2 = p3.add_clip(m3.id, 10.0)
    check(p3.trim_clip(t1.id, 0.0, 6.0), "tail trimmed to 6s")
    check(t2.start == 6.0, "the neighbour reflowed against the new tail")
    check(p3.trim_clip(t1.id, 2.0, 4.0), "head trimmed to 2s in")
    check(t1.source_in == 2.0 and t1.duration == 4.0, "head offset stored")
    p3.trim_clip(t1.id, 2.0, 50.0)
    check(t1.duration == 8.0,
          f"the tail cannot outrun the source (10s - 2s in = {t1.duration}s)")
    p3.trim_clip(t1.id, -5.0, 4.0)
    check(t1.source_in == 0.0, "the head cannot go before the source's start")
    p3.trim_clip(t1.id, 0.0, 0.001)
    check(t1.duration >= 0.1, "a clip never collapses to nothing")

    print("\n--- serialisation ---")
    data = project.to_dict()
    again = Project.from_dict(data, folder="")
    # After the audio checks above, `second` sits at volume 0.8, audio off.
    reloaded = again.find_clip(second.id)
    check(reloaded is not None and reloaded.source_in == 4.0
          and reloaded.volume == 0.8 and reloaded.audio_enabled is False,
          "source_in, volume and audio_enabled survive a round-trip")
    muted_reloaded = again.find_clip(clip.id)
    check(muted_reloaded is not None and muted_reloaded.muted is True,
          "muted survives a round-trip")
    old = TimelineClip.from_dict({"media_id": "m", "start": 0, "duration": 5})
    check(old.source_in == 0.0 and old.volume == 1.0
          and old.audio_enabled is True and old.muted is False,
          "an old document without the fields gets the defaults")


def test_gain_filter() -> None:
    import numpy as np

    from ive.engine.filters import Gain
    from ive.engine.frame import AudioFormat, Frame, Timebase

    print("\n--- the gain filter ---")
    decoded = {"image": 0}

    def image_fn():
        decoded["image"] += 1
        return np.zeros((4, 4, 3), dtype=np.uint8)

    audio = np.full((100, 2), 0.5, dtype=np.float32)
    frame = Frame(0, Timebase(), AudioFormat(),
                  image_fn=image_fn, audio_fn=lambda: audio)

    out = Gain(0.5).process(frame)
    scaled = out.audio()
    check(scaled is not None and abs(float(scaled.max()) - 0.25) < 1e-6,
          "gain 0.5 halves the samples")
    check(scaled.dtype == np.float32, "the engine format is preserved")
    check(decoded["image"] == 0,
          "scaling the sound never decoded the picture (lazy stacks)")
    check(out.image() is not None and decoded["image"] == 1,
          "the picture still arrives when asked for")

    muted = Gain(0.0).process(frame).audio()
    check(muted is not None and float(np.abs(muted).max()) == 0.0,
          "gain 0 is silence")
    same = Gain(1.0).process(frame)
    check(same is frame, "gain 1 passes the frame through untouched")


def test_through_the_graph() -> None:
    import numpy as np

    from ive.engine.builder import build_from_project

    print("\n--- volume through the graph ---")
    tone = ROOT / "tests" / "output" / "tone.mp4"
    if not tone.is_file():
        print("  (tone.mp4 fixture missing - run test_audio_graph.py first; skipping)")
        return

    def peak(volume: float) -> float:
        graph = build_from_project(
            [{"path": str(tone), "start": 0.0, "duration": 1.0,
              "volume": volume, "id": "c1"}],
            fps=25.0, width=320, height=240)
        try:
            total = 0.0
            for index in range(5, 15):     # skip the fade-in, if any
                frame = graph.frame_at(index)
                block = frame.audio() if frame is not None else None
                if block is not None:
                    total = max(total, float(np.abs(block).max()))
            return total
        finally:
            graph.close()

    loud = peak(1.0)
    half = peak(0.5)
    check(loud > 0.1, f"the fixture produces sound at volume 1 ({loud:.3f})")
    check(abs(half - loud / 2) < 0.02,
          f"volume 0.5 through the graph halves the peak "
          f"({half:.3f} vs {loud:.3f})")


def main() -> int:
    test_model()
    test_gain_filter()
    test_through_the_graph()
    print(f"\n{'PASS' if not failures else 'FAIL'} ({len(failures)} problem(s))")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
