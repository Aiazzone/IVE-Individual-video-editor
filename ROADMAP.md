# IVE — Roadmap

The living plan: what is done, what is being built, what comes next.
Updated together with the code, so this file always reflects reality.
(The detailed engineering plan, in Italian, lives in
[`docs/ROADMAP.md`](docs/ROADMAP.md).)

## ✅ Done

- [x] Immersive shell: full-screen video, glass surfaces, tool rail,
      floating panel, dark/light themes, 4 languages (EN/IT/ES/PT)
- [x] Frame-accurate playback engine (MLT-model pull graph): one graph
      for preview and export
- [x] Audio playback with A/V sync driven by the audio clock
- [x] Multi-clip timeline: drag to place and reorder (midpoint rule),
      trim with edge handles and cross-lane snapping, split at playhead
- [x] Per-clip audio: volume slider, mute (state, not volume-zero),
      remove/restore a clip's audio; music (audio-only) clips
- [x] Timeline zoom (wheel, buttons, fit-all) with playhead follow
- [x] Colour effects: JSON recipes in families, live thumbnails on the
      user's own footage, favourites with stars, drag onto a dedicated
      Color lane, ~7 ms/frame grading (compiled LUT/matrix steps);
      12-op vocabulary including shadows/highlights and a whole-recipe
      intensity dial; 29 built-in looks in 8 families
- [x] Export: social presets (YouTube, Instagram, TikTok, ...), custom
      tab (container/codecs/aspect/resolution/bitrate), file name field
- [x] Audio in the export: the mix the graph plays (per-clip volume,
      mute, music tracks, sample-exact silence in holes) is muxed into
      the file — AAC/MP3/Opus/FLAC/PCM per container
- [x] Proxy editing for heavy sources; media pool with real thumbnails
- [x] Keyboard: Space play/pause, Delete removes selection, digit keys
      open panels — all app-wide, text fields keep priority
- [x] Undo/redo for every project edit (Command layer over the model):
      Ctrl+Z / Ctrl+Y, buttons next to the fullscreen toggle, tooltip
      names the step about to be reverted, autosave follows
- [x] Real waveforms on audio clips: true peaks decoded off-thread and
      cached per file; trimming, splitting and zooming slide the same
      strip instead of re-decoding

## 🔨 In progress / next up

- [ ] Text and titles on the timeline

## 🗺️ Planned

- [ ] Stickers (animated overlays as shareable packs) — rail icon already
      in place
- [ ] Transitions between clips (the engine's Transition slot exists)
- [ ] Multi-track timeline (music under video, picture-in-picture)
- [ ] Content packs (`.ivepack`): bundle effects/presets/music with
      author and description
- [ ] Export queue (one edit → YouTube + Reels + LinkedIn in sequence)
- [ ] AI tools: auto-cut, subtitles, background removal (ONNX Runtime)
- [ ] Linux packaging and testing pass; installer/builds via PyInstaller

## 💡 Ideas (not committed)

- LUT file import (`.cube`) as colour effects
- Per-effect intensity slider on the Color lane
- Project templates for social formats
- Beat detection to snap cuts to music

## 🧪 Quality notes

Every feature above ships with script-style and visual test suites that
drive the real application (kept in the private working tree for now).
Known engineering debts are tracked in the session notes.
