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
- [x] Sticker catalogue and panel: Static / Animated tabs, families
      (shapes, good morning, greetings, birthday + demos), 15 factory
      SVG stickers, shareable manifest + files like the colour effects
- [x] Stickers ON the video: drag onto a dedicated timeline lane, the
      engine composites them into the frame (same pixels in preview and
      export), undoable; animated Lottie stickers play in a loop via
      rlottie — drop a Lottie JSON in a folder to install more
- [x] Sticker handles in the preview: click a sticker on the paused
      video to select it, drag to move, corner knob to scale, stalk to
      rotate (snapping near right angles) — live while the hand moves,
      one undo step per gesture
- [x] Text and titles: "Add a title" places it at the playhead on a
      dedicated Text lane; edit words, colour, outline, bold/italic
      and font (every family shown in its own face) in the panel with
      the frame updating as you type; grab the title on the video to
      move/scale/rotate it like a sticker — identical in preview and
      export, one undo step per gesture

- [x] Transitions between clips: 16 built-in in 3 families (dissolves,
      wipes, motion), dragged onto the video track — they snap to the
      nearest cut, or to the film's start/end where they play from and
      to black (intro/outro, audio fading with them). A white pill
      over the lane shows each one: drag its edges to change the
      duration, tap it and trash to remove. At a cut the next clip is
      pulled back by the transition's length (no extra source material
      ever needed) and audio crossfades at equal power; preview and
      export blend identically. A transition is a JSON recipe; wipes
      are greyscale LUMA MAPS, so drawing a PNG in any image editor
      creates a new one — shareable like the colour effects. Measured
      1.2–6 ms/frame at 720p (LUT + SIMD blend; the naive path was
      18x slower)

- [x] Content packs (`.ivepack`): one shareable file bundling colour
      effects, transitions (luma maps included) and stickers, with
      author and description. A Packs panel creates one from ticked
      contents (favourites as a shortcut) and manages the installed
      ones as removable units; installing — from file or by dropping
      the .ivepack on the window — always shows a confirmation card
      with the contents and a duplicates warning first. Data only,
      never code; nothing is ever overwritten

## 🔨 In progress / next up

- [ ] Sticker motion presets (bounce, pulse, spin as JSON keyframe
      recipes) and title enter/exit animations — shareable, and they
      slot straight into the packs

## 🗺️ Planned

- [ ] Text style presets as shareable JSON
- [ ] More factory luma maps (star, heart, brush stroke)
- [ ] Export presets as a JSON catalogue, so they join the packs too
- [ ] Multi-track timeline (music under video, picture-in-picture)
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
