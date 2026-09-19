// The timeline: a glass slab across the full width of the window.
//
// Glass at the TEXT threshold (scrimText) because it carries the ruler,
// track names and timecode.
//
// The clips are sample data until stage 3. What is real here is the layout:
// the padding that leaves glass visible around every clip, which is what makes
// this timeline breathe instead of reading as one black block.
import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Effects
import components
import IVE

Item {
    id: root

    property Item sceneSource: null
    property real position: 0        // seconds
    property real duration: 32       // seconds

    /*! 1 = the whole duration fits the lane width; above that the view pans.
        Wheel over the lanes and the toolbar buttons drive it. */
    property real zoom: 1.0

    /*! Zoom by `factor` keeping the time under `anchorX` (in viewport
        coordinates) where it is. The wheel, the toolbar buttons and the
        tests all come through here. */
    function zoomBy(factor, anchorX) {
        var target = Math.max(1, Math.min(64, zoom * factor));
        if (target === zoom)
            return;
        var seconds = (scroller.contentX + anchorX) / lanes.pps;
        zoom = target;
        scroller.contentX = Math.max(0, Math.min(
            scroller.contentWidth - scroller.width,
            seconds * lanes.pps - anchorX));
    }

    /*! Back to "everything visible": zoom 1, view at the start. */
    function fitAll() {
        zoom = 1;
        scroller.contentX = 0;
    }

    // Everything drawn on the glass takes its colour from here, so the
    // timeline stays legible when the theme flips. Hardcoded white would be
    // invisible on a light theme.
    readonly property color onGlass: Theme.c.glassOn

    signal seekRequested(real seconds)

    /*! Name of the media loaded in the preview; empty means none. */
    property string mediaName: ""

    signal mediaDropped(string mediaId, real seconds)
    /*! Asks the shell to open a floating-panel section (the motion
        button on a selected sticker opens the Stickers panel there). */
    signal panelRequested(string key)

    /*! The floating-panel section that edits a lane's clips. Tapping a
        clip on the timeline opens it, so the tool for what was just
        selected is already on screen: a title's words, a sticker's
        catalogue and animation, a colour look, the media bin. */
    readonly property var panelForKind: ({
        video: "project", audio: "audio", music: "audio", color: "color",
        fx: "effects",
        sticker: "stickers", text: "text", transition: "transitions"
    })
    function openPanelFor(kind) {
        var key = panelForKind[kind];
        if (key !== undefined)
            root.panelRequested(key);
    }

    /*! Window coordinates -> seconds on the timeline, scroll and zoom
        included. The window-wide file drop asks this when the release
        happens over the lanes, so an external file lands exactly where
        the pointer says. */
    function secondsAtWindow(wx, wy) {
        var local = content.mapFromItem(null, wx, wy);
        return local.x / lanes.pps;
    }

    // The timeline shows the PROJECT, not whatever is in the preview. Those
    // are different things, and conflating them hid the fact that a project
    // holds many clips.
    readonly property var tracks: projectTracks

    readonly property var projectTracks: {
        var clips = Project.isOpen ? Project.timelineClips : [];
        var lanes = [
            { name: "V1", kind: "video", audio: false,
              height: Theme.m.trackHeightVideo,
              clips: clips.filter(function (c) {
                  return c.track === 0 && c.hasVideo;
              }).map(function (c) {
                  return { from: c.start, to: c.end, color: Theme.c.clipVideo,
                           name: c.name, film: true, id: c.id, wave: false,
                           // Diamond markers: clip-local pin times.
                           keys: (c.keyframes || []).map(function (k) {
                               return k.t;
                           }) };
              }) },
            { name: "A1", kind: "audio", audio: true,
              height: Theme.m.trackHeightAudio,
              clips: clips.filter(function (c) {
                  return c.track === 0 && c.hasAudio && c.audioEnabled;
              }).map(function (c) {
                  // path/sourceIn/mediaDuration feed the waveform strip:
                  // the PNG covers the WHOLE file, the clip shows its slice.
                  return { from: c.start, to: c.end, color: Theme.c.clipAudio,
                           name: c.name, film: false, id: c.id, wave: true,
                           path: c.path, sourceIn: c.sourceIn,
                           mediaDuration: c.mediaDuration,
                           speed: c.speed || 1,
                           fadeIn: c.fadeIn, fadeOut: c.fadeOut,
                           effect: c.audioEffectId };
              }) }
        ];
        // The Color and Sticker lanes exist only while something sits on
        // them: an empty permanent lane would just be chrome.
        var col = clips.filter(function (c) { return c.track === 1; });
        if (col.length > 0)
            lanes.push({ name: "Color", kind: "color", audio: false,
                         height: Theme.m.trackHeightAudio,
                         clips: col.map(function (c) {
                             return { from: c.start, to: c.end,
                                      color: Theme.c.clipEffect,
                                      name: c.name, film: false,
                                      id: c.id, wave: false };
                         }) });
        // Track 5 is the Effects lane (fx catalogue: subject, artistic).
        // Where it overlaps the Color lane, the LAST-inserted clip wins.
        var sfx = clips.filter(function (c) { return c.track === 5; });
        if (sfx.length > 0)
            lanes.push({ name: "Effects", kind: "fx", audio: false,
                         height: Theme.m.trackHeightAudio,
                         clips: sfx.map(function (c) {
                             return { from: c.start, to: c.end,
                                      color: Theme.c.clipFx
                                             || Theme.c.clipEffect,
                                      name: c.name, film: false,
                                      id: c.id, wave: false };
                         }) });
        var st = clips.filter(function (c) { return c.track === 2; });
        if (st.length > 0)
            lanes.push({ name: "Sticker", kind: "sticker", audio: false,
                         height: Theme.m.trackHeightAudio,
                         clips: st.map(function (c) {
                             return { from: c.start, to: c.end,
                                      color: Theme.c.clipSticker,
                                      name: c.name, film: false,
                                      id: c.id, wave: false };
                         }) });
        var mu = clips.filter(function (c) { return c.track === 4; });
        if (mu.length > 0)
            lanes.push({ name: "Music", kind: "music", audio: true,
                         height: Theme.m.trackHeightAudio,
                         clips: mu.map(function (c) {
                             return { from: c.start, to: c.end,
                                      color: Theme.c.clipMusic,
                                      name: c.name, film: false,
                                      id: c.id, wave: true,
                                      path: c.path, sourceIn: c.sourceIn,
                                      mediaDuration: c.mediaDuration,
                                      fadeIn: c.fadeIn, fadeOut: c.fadeOut,
                                      effect: c.audioEffectId,
                                      duck: c.duck };
                         }) });
        var tx = clips.filter(function (c) { return c.track === 3; });
        if (tx.length > 0)
            lanes.push({ name: "Text", kind: "text", audio: false,
                         height: Theme.m.trackHeightAudio,
                         clips: tx.map(function (c) {
                             return { from: c.start, to: c.end,
                                      color: Theme.c.clipText,
                                      name: c.name, film: false,
                                      id: c.id, wave: false };
                         }) });
        return lanes;
    }

    // Empty until a media file is opened. Fake clips were useful while the
    // layout was being built; leaving them in would be lying about what the
    // application currently holds.
    readonly property var sampleTracks: [
        { name: "V1", audio: false, height: Theme.m.trackHeightVideo, clips: [] },
        { name: "A1", audio: true,  height: Theme.m.trackHeightAudio, clips: [] }
    ]

    // ── selection ──────────────────────────────────────────────────
    // By clip ID, never by name: two cuts of the same file share a name.
    // `selectedKind` records WHICH lane was tapped ("video"/"audio"), so
    // the contextual toolbox can offer picture tools on one and sound
    // tools on the other for the same underlying clip.
    property string selectedClipId: ""
    property string selectedKind: ""
    /*! Ids Ctrl+clicked ONTO the primary selection: the rest of a
        multi-selection. Delete and Ctrl+C act on primary + these. */
    property var extraSelected: []
    onExtraSelectedChanged: Shell.set_extra_selected(extraSelected)

    /*! Ctrl+click: grow or shrink the multi-selection. The primary
        stays what it is - the toolbox needs ONE clip to describe. */
    function toggleExtra(clipId, kind) {
        if (selectedClipId === "") {
            selectedClipId = clipId;
            selectedKind = kind;
            return;
        }
        if (clipId === selectedClipId)
            return;
        var list = extraSelected.slice();
        var found = list.indexOf(clipId);
        if (found >= 0)
            list.splice(found, 1);
        else
            list.push(clipId);
        extraSelected = list;
    }

    // Mirrored into the shell state, so the on-video handles and the Text
    // panel see the SAME selection the timeline does (and back: selecting
    // a title on the video opens its words in the panel).
    onSelectedClipIdChanged: Shell.set_selected_clip(selectedClipId,
                                                     selectedKind)
    onSelectedKindChanged: Shell.set_selected_clip(selectedClipId,
                                                   selectedKind)
    Connections {
        target: Shell
        function onChanged() {
            if (Shell.v.selectedClipId !== root.selectedClipId) {
                root.selectedClipId = Shell.v.selectedClipId;
                root.selectedKind = Shell.v.selectedKind;
            }
        }
    }

    /*! The selected clip's data, live from the project; null when nothing
        is selected or the clip was deleted under the selection. */
    readonly property var selectedClipData: {
        if (selectedClipId === "")
            return null;
        var clips = Project.timelineClips;
        for (var i = 0; i < clips.length; i++)
            if (clips[i].id === selectedClipId)
                return clips[i];
        return null;
    }

    function clearSelection() {
        selectedClipId = "";
        selectedKind = "";
        selectedTransition = null;
        extraSelected = [];
    }

    /*! Live clip data by id, for handlers that need sourceIn/mediaDuration
        rather than the lane model's reduced {from, to} shape. */
    function clipDataFor(clipId) {
        var clips = Project.timelineClips;
        for (var i = 0; i < clips.length; i++)
            if (clips[i].id === clipId)
                return clips[i];
        return null;
    }

    /*! Delete what is SELECTED - which depends on the lane. On the audio
        lane only the clip's sound goes (the video stays); on the video lane
        the whole clip goes. The Delete key (Main.qml) and the trash button
        both land here. */
    function deleteSelected() {
        // A multi-selection goes WHOLE: every selected clip is removed
        // in one undo step (the audio-lane subtlety below is a
        // single-selection nicety; picking many means "take them away").
        if (extraSelected.length > 0) {
            var ids = extraSelected.slice();
            if (selectedClipId !== "" && ids.indexOf(selectedClipId) < 0)
                ids.unshift(selectedClipId);
            clearSelection();
            Actions.invoke("timeline.remove_clips", { clip_ids: ids });
            return;
        }
        // A selected transition pill deletes the TRANSITION, never the
        // clip it happens to reference.
        if (selectedKind === "transition" && selectedTransition !== null) {
            var picked = selectedTransition;
            clearSelection();
            Actions.invoke("timeline.set_transition", {
                clip_id: picked.clipId, transition_id: "",
                duration: 0.5, edge: picked.edge
            });
            return;
        }
        if (selectedClipData === null)
            return;
        var id = selectedClipId;
        var kind = selectedKind;
        // A music clip lives ONLY on the audio lane: stripping its sound
        // would leave an invisible zombie, so there Delete takes the clip.
        var soundOnly = !selectedClipData.hasVideo;
        clearSelection();
        if (kind === "audio" && !soundOnly)
            Actions.invoke("timeline.set_clip_audio",
                           { clip_id: id, enabled: false });
        else
            Actions.invoke("timeline.remove_clip", { clip_id: id });
    }

    // ── transitions on V1 ──────────────────────────────────────────
    /*! The video clips, sorted - the raw material for cuts and pills. */
    function videoClips() {
        var clips = Project.isOpen ? Project.timelineClips : [];
        return clips.filter(function (c) {
            return c.track === 0 && c.hasVideo;
        }).sort(function (a, b) { return a.start - b.start; });
    }

    /*! Where a dropped transition can land: every cut between two
        clips, plus the very head of the first clip (the intro from
        black) and the very tail of the last (the outro to black). */
    function transitionTargetNear(seconds) {
        var video = videoClips();
        if (video.length === 0)
            return null;
        var candidates = [];
        for (var i = 0; i + 1 < video.length; i++)
            candidates.push({ at: (video[i].end + video[i + 1].start) / 2,
                              clipId: video[i].id, edge: "out" });
        candidates.push({ at: video[0].start,
                          clipId: video[0].id, edge: "in" });
        candidates.push({ at: video[video.length - 1].end,
                          clipId: video[video.length - 1].id, edge: "out" });
        var best = null;
        var bestDistance = 1e9;
        for (var k = 0; k < candidates.length; k++) {
            var d = Math.abs(candidates[k].at - seconds);
            if (d < bestDistance) {
                bestDistance = d;
                best = candidates[k];
            }
        }
        return best;
    }

    /*! The placed transitions, as pills: the pill's span IS the blend
        window, so its width is the duration the user can trim. */
    readonly property var transitionPills: {
        var video = videoClips();
        var out = [];
        for (var i = 0; i + 1 < video.length; i++) {
            var left = video[i];
            if (left.transitionId
                    && video[i + 1].start < left.end - 1e-4)
                out.push({ kind: "cut", clipId: left.id,
                           tid: left.transitionId,
                           from: video[i + 1].start, to: left.end });
        }
        if (video.length > 0) {
            var first = video[0];
            if (first.transitionInId)
                out.push({ kind: "in", clipId: first.id,
                           tid: first.transitionInId,
                           from: first.start,
                           to: first.start + Math.min(
                               first.transitionInDuration,
                               first.duration / 2) });
            var last = video[video.length - 1];
            if (last.transitionId)
                // The LAST clip's outgoing transition has no next clip:
                // it plays as the outro towards black (a junction never
                // consumes it - there is no junction after the last).
                out.push({ kind: "out", clipId: last.id,
                           tid: last.transitionId,
                           from: last.end - Math.min(
                               last.transitionDuration, last.duration / 2),
                           to: last.end });
        }
        return out;
    }

    /*! The pill selected for deletion, {clipId, edge} or null. */
    property var selectedTransition: null

    /*! Whether any clip covers this point in time. */
    function clipAt(seconds) {
        var clips = Project.timelineClips;
        for (var i = 0; i < clips.length; i++)
            if (seconds >= clips[i].start && seconds < clips[i].end)
                return true;
        return false;
    }

    /*! The magnet: ``seconds`` pulled onto the nearest OTHER clip's edge
        when within ``threshold`` (seconds), else returned untouched. Every
        trim handle comes through here, so a video edge snaps to an audio
        clip's end and the other way round. */
    function snapTime(seconds, excludeId, threshold) {
        var clips = Project.timelineClips;
        var best = seconds;
        var bestDistance = threshold;
        for (var i = 0; i < clips.length; i++) {
            if (clips[i].id === excludeId)
                continue;
            var edges = [clips[i].start, clips[i].end];
            for (var k = 0; k < 2; k++) {
                var d = Math.abs(seconds - edges[k]);
                if (d < bestDistance) {
                    bestDistance = d;
                    best = edges[k];
                }
            }
        }
        return best;
    }

    // ── contextual toolbox ─────────────────────────────────────────
    // One entry per tool; the toolbar builds itself from this list.
    // `kinds` says which selection shows the button, `show` (optional)
    // hides it from clips it does not apply to, `can` (optional) gates
    // it, `run` acts on the selected clip's data. Adding a tool for a
    // future selection kind = adding an entry here.
    readonly property var contextActions: [
        { icon: Icons.split,
          label: Tr.s["timeline.split"] || "",
          kinds: ["video", "audio", "music", "color", "sticker", "text"],
          can: function (clip) {
              return root.position > clip.start + 0.05
                  && root.position < clip.end - 0.05;
          },
          run: function (clip) {
              Actions.invoke("timeline.split_clip",
                             { clip_id: clip.id, at: root.position });
          } },
        { icon: Icons.volumeOff,
          label: Tr.s["timeline.mute_clip"] || "",
          kinds: ["audio", "music"],
          // `active` lights the button (accent) while the state is on -
          // without it a toggle gives no clue about which way it stands.
          active: function (clip) { return clip.muted === true; },
          run: function (clip) {
              Actions.invoke("timeline.set_clip_muted",
                             { clip_id: clip.id, muted: !clip.muted });
          } },
        { icon: Icons.volume,
          label: Tr.s["timeline.restore_audio"] || "",
          kinds: ["video"],
          show: function (clip) {
              return clip.hasAudio && !clip.audioEnabled;
          },
          run: function (clip) {
              Actions.invoke("timeline.set_clip_audio",
                             { clip_id: clip.id, enabled: true });
          } },
        { icon: Icons.motion,
          label: Tr.s["motion.set"] || "",
          kinds: ["sticker", "text"],
          // The Stickers (or Text) panel becomes the selected clip's
          // animation editor (the selection is already shared through
          // Shell).
          run: function () {
              root.panelRequested(root.selectedKind === "text"
                                  ? "text" : "stickers");
          } },
        { icon: Icons.trash,
          label: Tr.s["timeline.delete"] || "",
          kinds: ["video", "music", "color", "sticker", "text", "transition"],
          run: function () { root.deleteSelected(); } },
        { icon: Icons.trash,
          label: Tr.s["timeline.remove_audio"] || "",
          kinds: ["audio"],
          run: function () { root.deleteSelected(); } }
    ]

    GlassSurface {
        anchors.fill: parent
        sceneSource: root.sceneSource
        originX: root.x
        originY: root.y
        radius: 0
        scrim: Theme.m.scrimText
        showBorder: false
    }

    Rectangle {                    // hairline on the edge facing the video
        anchors.top: parent.top
        width: parent.width
        height: 1
        color: Theme.c.glassBorder
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── toolbar ───────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.m.timelineToolbarHeight
            Layout.leftMargin: Theme.m.space3
            Layout.rightMargin: Theme.m.space3
            spacing: Theme.m.space1

            // The left side belongs to the SELECTION: no clip, no buttons.
            // The row builds itself from `contextActions` above.
            Repeater {
                model: root.contextActions
                delegate: IconButton {
                    required property var modelData
                    size: 26; iconSize: 15
                    icon: modelData.icon
                    label: modelData.label
                    visible: root.selectedClipData !== null
                             && modelData.kinds.indexOf(root.selectedKind) >= 0
                             && (!modelData.show
                                 || modelData.show(root.selectedClipData))
                    enabled: root.selectedClipData !== null
                             && (!modelData.can
                                 || modelData.can(root.selectedClipData))
                    checked: root.selectedClipData !== null
                             && modelData.active !== undefined
                             && modelData.active(root.selectedClipData)
                    onTriggered: modelData.run(root.selectedClipData)
                }
            }

            // The selected clip's loudness: a slider, committed on release
            // (every commit rebuilds the graph, so live-updating would
            // rebuild it continuously mid-drag), with the live value beside
            // it so the drag still reads instantly.
            Text {
                visible: clipVolume.visible
                text: Tr.s["audio.volume"] || ""
                color: Qt.alpha(root.onGlass, 0.72)
                font.pixelSize: Theme.m.fontSizeXs
            }
            AppSlider {
                id: clipVolume
                visible: (root.selectedKind === "audio"
                          || root.selectedKind === "music")
                         && root.selectedClipData !== null
                Layout.preferredWidth: 120
                from: 0
                to: 2
                stepSize: 0.05
                label: Tr.s["timeline.volume"] || ""
                value: root.selectedClipData !== null
                    ? root.selectedClipData.volume : 1
                onCommitted: function (v) {
                    if (root.selectedClipData !== null)
                        Actions.invoke("timeline.set_clip_volume", {
                            clip_id: root.selectedClipData.id,
                            volume: Math.round(v * 100) / 100
                        });
                }
            }
            Text {
                visible: clipVolume.visible
                Layout.preferredWidth: 34
                text: Math.round(clipVolume.effectiveValue * 100) + "%"
                color: Qt.alpha(root.onGlass, 0.72)
                font.pixelSize: Theme.m.fontSizeXs
                font.family: "monospace"
            }

            // The selected sound's fades, right where the eye is: the
            // shades on the clip grow and shrink with these.
            Text {
                visible: clipVolume.visible
                text: Tr.s["audio.fade_in"] || ""
                color: Qt.alpha(root.onGlass, 0.72)
                font.pixelSize: Theme.m.fontSizeXs
            }
            AppSlider {
                id: fadeInLength
                objectName: "timeline_fade_in_slider"
                visible: clipVolume.visible
                Layout.preferredWidth: 110
                from: 0
                to: root.selectedClipData !== null
                    ? Math.max(0.5, Math.min(10, (root.selectedClipData.end
                                                  - root.selectedClipData.start) / 2))
                    : 5
                stepSize: 0.1
                label: Tr.s["audio.fade_in"] || ""
                value: root.selectedClipData !== null
                    ? root.selectedClipData.fadeIn : 0
                onCommitted: function (v) {
                    if (root.selectedClipData !== null)
                        Actions.invoke("timeline.set_clip_fades", {
                            clip_id: root.selectedClipData.id,
                            fade_in: Math.round(v * 10) / 10,
                            fade_out: root.selectedClipData.fadeOut
                        });
                }
            }
            Text {
                visible: clipVolume.visible
                Layout.preferredWidth: 30
                text: fadeInLength.effectiveValue.toFixed(1) + "s"
                color: Qt.alpha(root.onGlass, 0.72)
                font.pixelSize: Theme.m.fontSizeXs
                font.family: "monospace"
            }
            Text {
                visible: clipVolume.visible
                text: Tr.s["audio.fade_out"] || ""
                color: Qt.alpha(root.onGlass, 0.72)
                font.pixelSize: Theme.m.fontSizeXs
            }
            AppSlider {
                id: fadeOutLength
                objectName: "timeline_fade_out_slider"
                visible: clipVolume.visible
                Layout.preferredWidth: 110
                from: 0
                to: fadeInLength.to
                stepSize: 0.1
                label: Tr.s["audio.fade_out"] || ""
                value: root.selectedClipData !== null
                    ? root.selectedClipData.fadeOut : 0
                onCommitted: function (v) {
                    if (root.selectedClipData !== null)
                        Actions.invoke("timeline.set_clip_fades", {
                            clip_id: root.selectedClipData.id,
                            fade_in: root.selectedClipData.fadeIn,
                            fade_out: Math.round(v * 10) / 10
                        });
                }
            }
            Text {
                visible: clipVolume.visible
                Layout.preferredWidth: 30
                text: fadeOutLength.effectiveValue.toFixed(1) + "s"
                color: Qt.alpha(root.onGlass, 0.72)
                font.pixelSize: Theme.m.fontSizeXs
                font.family: "monospace"
            }

            // The selected VIDEO clip's opacity: 1 opaque, towards 0 it
            // dissolves into what sits underneath. Committed on release.
            Text {
                visible: clipOpacity.visible
                text: Tr.s["video.opacity"] || ""
                color: Qt.alpha(root.onGlass, 0.72)
                font.pixelSize: Theme.m.fontSizeXs
            }
            AppSlider {
                id: clipOpacity
                objectName: "timeline_opacity_slider"
                visible: root.selectedKind === "video"
                         && root.selectedClipData !== null
                Layout.preferredWidth: 90
                from: 0
                to: 1
                stepSize: 0.05
                label: Tr.s["video.opacity"] || ""
                value: root.selectedClipData !== null
                       && root.selectedClipData.opacity !== undefined
                    ? root.selectedClipData.opacity : 1
                onCommitted: function (v) {
                    if (root.selectedClipData !== null)
                        Actions.invoke("timeline.set_clip_opacity", {
                            clip_id: root.selectedClipData.id,
                            opacity: Math.round(v * 100) / 100
                        });
                }
            }
            Text {
                visible: clipOpacity.visible
                Layout.preferredWidth: 30
                text: Math.round(clipOpacity.effectiveValue * 100) + "%"
                color: Qt.alpha(root.onGlass, 0.72)
                font.pixelSize: Theme.m.fontSizeXs
                font.family: "monospace"
            }

            // The keyframe diamond: lit when a pin stands at the
            // playhead. Tap = pin the clip's current transform and
            // opacity there; tap again = take the pin away. Between
            // pins the values run linearly (utils/keyframes.py).
            IconButton {
                id: kfButton
                objectName: "timeline_keyframe_button"
                visible: root.selectedKind === "video"
                         && root.selectedClipData !== null
                         && root.position >= root.selectedClipData.start
                         && root.position < root.selectedClipData.end
                size: 26; iconSize: 15
                icon: Icons.keyframe
                label: Tr.s["video.keyframe"] || ""
                readonly property real localT:
                    root.selectedClipData !== null
                    ? root.position - root.selectedClipData.start : 0
                checked: {
                    if (root.selectedClipData === null)
                        return false;
                    var keys = root.selectedClipData.keyframes || [];
                    for (var i = 0; i < keys.length; i++)
                        if (Math.abs(keys[i].t - localT) <= 0.05)
                            return true;
                    return false;
                }
                onTriggered: {
                    var clip = root.selectedClipData;
                    if (clip === null)
                        return;
                    if (checked) {
                        Actions.invoke("timeline.remove_clip_keyframe", {
                            clip_id: clip.id, t: localT });
                        return;
                    }
                    // Capture what is ON SCREEN at the playhead: the
                    // interpolated values when pins exist, the statics
                    // otherwise - and for a clip still following the
                    // canvas fit, the fit's own geometry, so the first
                    // pin changes nothing until the next one moves.
                    var v = Project.clip_keyframe_values(clip.id, localT);
                    if (!clip.placed
                            && (clip.keyframes || []).length === 0) {
                        v.x = 0.5;
                        v.y = 0.5;
                        v.rotation = 0;
                        v.scale = Math.min(1, Playback.aspect
                            / Math.max(0.05,
                                       Project.overlay_aspect(clip.id)));
                    }
                    Actions.invoke("timeline.set_clip_keyframe", {
                        clip_id: clip.id, t: localT,
                        x: v.x, y: v.y, scale: v.scale,
                        rotation: v.rotation, opacity: v.opacity
                    });
                }
            }

            // How the values ARRIVE at the pin under the playhead:
            // shown only while the diamond is lit. "Spring" overshoots
            // and settles, like something with mass; linear is the
            // unmarked default.
            Row {
                id: easingChips
                visible: kfButton.visible && kfButton.checked
                spacing: 2

                readonly property string current: {
                    if (root.selectedClipData === null)
                        return "linear";
                    var keys = root.selectedClipData.keyframes || [];
                    for (var i = 0; i < keys.length; i++)
                        if (Math.abs(keys[i].t - kfButton.localT) <= 0.05)
                            return keys[i].easing || "linear";
                    return "linear";
                }

                Repeater {
                    model: ["linear", "smooth", "ease_in", "ease_out",
                            "spring"]
                    delegate: Rectangle {
                        id: easeChip
                        required property var modelData
                        objectName: "timeline_ease_" + modelData
                        readonly property bool current:
                            easingChips.current === modelData
                        width: easeText.implicitWidth + 10
                        height: 20
                        radius: 999
                        color: current ? Qt.alpha(Theme.c.accent, 0.25)
                             : Qt.alpha(root.onGlass, 0.08)
                        border.width: 1
                        border.color: current ? Theme.c.accent
                            : Qt.alpha(root.onGlass, 0.16)
                        Text {
                            id: easeText
                            anchors.centerIn: parent
                            text: Tr.s["video.ease." + easeChip.modelData]
                                  || easeChip.modelData
                            color: easeChip.current
                                ? root.onGlass
                                : Qt.alpha(root.onGlass, 0.72)
                            font.pixelSize: Theme.m.fontSizeXs
                            font.bold: easeChip.current
                        }
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        TapHandler {
                            onTapped: {
                                if (root.selectedClipData !== null)
                                    Actions.invoke(
                                        "timeline.set_keyframe_easing", {
                                            clip_id:
                                                root.selectedClipData.id,
                                            t: kfButton.localT,
                                            easing: easeChip.modelData
                                        });
                            }
                        }
                    }
                }
            }

            // The selected VIDEO clip's pace: preset chips, CapCut's
            // set. Committed at once (a deliberate choice, one undo
            // each); the clip's timeline length follows the pace, the
            // track reflows.
            Text {
                visible: speedChips.visible
                text: Tr.s["timeline.speed"] || ""
                color: Qt.alpha(root.onGlass, 0.72)
                font.pixelSize: Theme.m.fontSizeXs
            }
            Row {
                id: speedChips
                visible: root.selectedKind === "video"
                         && root.selectedClipData !== null
                spacing: 2
                Repeater {
                    model: [0.25, 0.5, 1, 1.5, 2, 4]
                    delegate: Rectangle {
                        id: speedChip
                        required property var modelData
                        objectName: "timeline_speed_" + modelData
                        readonly property bool current:
                            root.selectedClipData !== null
                            && Math.abs((root.selectedClipData.speed || 1)
                                        - modelData) < 0.011
                        width: speedText.implicitWidth + 10
                        height: 20
                        radius: 999
                        color: current ? Qt.alpha(Theme.c.accent, 0.25)
                             : Qt.alpha(root.onGlass, 0.08)
                        border.width: 1
                        border.color: current ? Theme.c.accent
                            : Qt.alpha(root.onGlass, 0.16)
                        Text {
                            id: speedText
                            anchors.centerIn: parent
                            text: speedChip.modelData + "x"
                            color: speedChip.current
                                ? root.onGlass
                                : Qt.alpha(root.onGlass, 0.72)
                            font.pixelSize: Theme.m.fontSizeXs
                            font.bold: speedChip.current
                        }
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        TapHandler {
                            onTapped: {
                                if (root.selectedClipData !== null)
                                    Actions.invoke("timeline.set_clip_speed", {
                                        clip_id: root.selectedClipData.id,
                                        speed: speedChip.modelData
                                    });
                            }
                        }
                    }
                }
            }

            // The selected TRANSITION's duration. At default zoom a pill
            // can be a handful of pixels wide, far too small to trim by
            // its edges - this slider is the reliable way to stretch it.
            // Committed on release: every commit reflows the timeline.
            AppSlider {
                id: transitionLength
                objectName: "transition_duration_slider"
                visible: root.selectedKind === "transition"
                         && root.selectedTransition !== null
                         && root.selectedClipData !== null
                Layout.preferredWidth: 140
                from: 0.1
                to: 3.0
                stepSize: 0.1
                label: Tr.s["transition.duration"] || ""
                value: {
                    if (root.selectedClipData === null
                            || root.selectedTransition === null)
                        return 0.5;
                    return root.selectedTransition.edge === "in"
                        ? root.selectedClipData.transitionInDuration
                        : root.selectedClipData.transitionDuration;
                }
                onCommitted: function (v) {
                    if (root.selectedClipData === null
                            || root.selectedTransition === null)
                        return;
                    var tid = root.selectedTransition.edge === "in"
                        ? root.selectedClipData.transitionInId
                        : root.selectedClipData.transitionId;
                    if (tid === "")
                        return;
                    Actions.invoke("timeline.set_transition", {
                        clip_id: root.selectedTransition.clipId,
                        transition_id: tid,
                        duration: Math.round(v * 10) / 10,
                        edge: root.selectedTransition.edge
                    });
                }
            }
            Text {
                visible: transitionLength.visible
                Layout.preferredWidth: 34
                text: transitionLength.effectiveValue.toFixed(1) + "s"
                color: Qt.alpha(root.onGlass, 0.72)
                font.pixelSize: Theme.m.fontSizeXs
                font.family: "monospace"
            }

            Item { Layout.fillWidth: true }

            IconButton { size: 26; iconSize: 15; icon: Icons.zoomOut
                         label: Tr.s["timeline.zoom_out"] || ""; tipSide: "left"
                         enabled: root.zoom > 1
                         onTriggered: root.zoomBy(1 / 1.4, lanes.width / 2) }
            IconButton { size: 26; iconSize: 15; icon: Icons.zoomIn
                         label: Tr.s["timeline.zoom_in"] || ""; tipSide: "left"
                         enabled: root.zoom < 64
                         onTriggered: root.zoomBy(1.4, lanes.width / 2) }
            IconButton { size: 26; iconSize: 15; icon: Icons.zoomFit
                         label: Tr.s["timeline.fit"] || ""; tipSide: "left"
                         enabled: root.zoom > 1
                         onTriggered: root.fitAll() }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Qt.alpha(root.onGlass, 0.10)
        }

        // ── headers + lanes ───────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // track headers
            //
            // fillWidth must be set to false explicitly: a layout nested in
            // another layout defaults it to TRUE, which silently overrides
            // preferredWidth. Without this the headers eat the whole row and
            // the lanes end up a few pixels wide.
            Item {
                Layout.fillWidth: false
                Layout.preferredWidth: Theme.m.trackHeaderWidth
                Layout.minimumWidth: Theme.m.trackHeaderWidth
                Layout.maximumWidth: Theme.m.trackHeaderWidth
                Layout.fillHeight: true

                // Only the track NAME: the eye/lock/mute buttons that used
                // to sit here were placeholders wired to nothing, and dead
                // chrome teaches the user to ignore this column. They come
                // back one by one WITH their behaviour (hide/lock/mute per
                // track), which is what this column is for in every editor.
                //
                // The names ride the SAME vertical scroll as the lanes
                // (y: -contentY), clipped above the ruler strip: a header
                // that stays put while its track slides away would label
                // the wrong lane.
                Item {
                    anchors.fill: parent
                    anchors.bottomMargin: Theme.m.rulerHeight
                    clip: true

                    Column {
                        y: -scroller.contentY
                        width: parent.width

                        Repeater {
                            model: root.tracks
                            delegate: Item {
                                id: laneHeader
                                required property var modelData
                                width: parent.width
                                height: modelData.height

                                HoverHandler { id: headerHover }

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    x: Theme.m.space2
                                    text: laneHeader.modelData.name
                                    color: Qt.alpha(root.onGlass, 0.72)
                                    font.pixelSize: Theme.m.fontSizeSm
                                    font.letterSpacing: 0.5
                                }

                                // One gesture empties the whole lane -
                                // otherwise clearing means selecting and
                                // deleting the clips one by one. Revealed
                                // on hover, one undo step brings it back.
                                IconButton {
                                    objectName: "lane_clear_"
                                        + laneHeader.modelData.kind
                                    visible: laneHeader.modelData.clips.length > 0
                                             && headerHover.hovered
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.right: parent.right
                                    anchors.rightMargin: Theme.m.space2
                                    size: 22
                                    iconSize: 13
                                    icon: Icons.trash
                                    label: Tr.s["timeline.clear_lane"] || ""
                                    onTriggered: Actions.invoke(
                                        "timeline.clear_lane",
                                        { kind: laneHeader.modelData.kind })
                                }
                            }
                        }
                    }
                }

                // Wheel over the names scrolls the tracks - the wheel over
                // the lanes belongs to zoom.
                WheelHandler {
                    onWheel: function (event) {
                        scroller.contentY = Math.max(0, Math.min(
                            Math.max(0, scroller.contentHeight - scroller.height),
                            scroller.contentY - event.angleDelta.y));
                    }
                }
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.fillHeight: true
                color: Qt.alpha(root.onGlass, 0.10)
            }

            // lanes
            //
            // Positioned explicitly rather than through nested layouts: the
            // ruler and the tracks must line up with the headers to the pixel,
            // and explicit y offsets are both easier to reason about and
            // cheaper than a layout pass per track.
            Item {
                id: lanes
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true

                // On the SCROLLER width, not the lanes': when the vertical
                // scrollbar is up, the scroller leaves it a gutter, and the
                // seconds-to-pixels scale must follow or the last clip ends
                // underneath the bar - where its trim handle cannot be
                // grabbed.
                readonly property real pps:
                    scroller.width * root.zoom / Math.max(0.001, root.duration)
                readonly property real rulerH: Theme.m.rulerHeight
                /*! Every track stacked: what the vertical scroll covers. */
                readonly property real tracksH: {
                    var h = 0;
                    for (var i = 0; i < root.tracks.length; i++)
                        h += root.tracks[i].height;
                    return h;
                }

                /*! Top edge of track `i`. Tracks start at the very top:
                    the ruler sits at the BOTTOM of the lanes. */
                function trackY(i) {
                    var y = 0;
                    for (var k = 0; k < i; k++)
                        y += root.tracks[k].height;
                    return y;
                }

                // Keep the advancing playhead in sight: a zoomed view would
                // otherwise just watch it walk out of the frame.
                Connections {
                    target: root
                    function onPositionChanged() {
                        if (root.zoom <= 1)
                            return;
                        var px = root.position * lanes.pps;
                        if (px < scroller.contentX
                                || px > scroller.contentX + scroller.width - 24)
                            scroller.contentX = Math.max(0, Math.min(
                                scroller.contentWidth - scroller.width,
                                px - scroller.width * 0.2));
                    }
                }

                // The ruler is NOT inside this Flickable: the time must
                // stay on screen whatever the tracks do. The Flickable
                // scrolls the TRACKS both ways (the ruler strip below
                // follows contentX so the ticks stay under the clips).
                Flickable {
                    id: scroller
                    objectName: "timeline_tracks_scroller"
                    anchors.fill: parent
                    anchors.bottomMargin: lanes.rulerH
                    // The vertical scrollbar gets a GUTTER, not an overlay:
                    // laid over the tracks it sat exactly on the right trim
                    // handle of any clip ending at the timeline's edge (a
                    // music track covering the cut always does) and stole
                    // the grab.
                    anchors.rightMargin: vbar.visible ? 12 : 0
                    contentWidth: width * root.zoom
                    contentHeight: Math.max(lanes.tracksH, height)
                    interactive: root.zoom > 1 || contentHeight > height + 1
                    flickableDirection: Flickable.HorizontalAndVerticalFlick
                    boundsBehavior: Flickable.StopAtBounds
                    // A lane that disappears (undo, delete) must not leave
                    // the view parked past the new bottom.
                    onContentHeightChanged: returnToBounds()

                Item {
                    id: content
                    width: scroller.contentWidth
                    height: scroller.contentHeight

                TapHandler {
                    onTapped: function (point) {
                        var seconds = point.position.x / lanes.pps;
                        root.seekRequested(seconds);
                        // Decided from the DATA, not from handler ordering:
                        // this handler fires for taps on clips too, and
                        // clearing here would race the clip's own handler.
                        if (!root.clipAt(seconds))
                            root.clearSelection();
                    }
                }

                // Plain wheel over the lanes: zoom around the cursor, the
                // editor meaning of the wheel. Shift+wheel scrolls the
                // tracks vertically instead. On the CONTENT item, not on
                // `lanes`: once interactive, the Flickable would swallow
                // the wheel for panning before an outer handler saw it.
                WheelHandler {
                    target: null
                    onWheel: function (event) {
                        if (event.modifiers & Qt.ShiftModifier) {
                            scroller.contentY = Math.max(0, Math.min(
                                Math.max(0, scroller.contentHeight
                                            - scroller.height),
                                scroller.contentY - event.angleDelta.y));
                            return;
                        }
                        root.zoomBy(event.angleDelta.y > 0 ? 1.25 : 0.8,
                                    event.x - scroller.contentX);
                    }
                }

                // Media dragged out of the project panel lands here, and so
                // do colour effects from the Color panel. The drop x is the
                // point in time, so clips can go before, between or after
                // the ones already down.
                DropArea {
                    id: laneDrop
                    anchors.fill: parent
                    keys: ["ive-media", "ive-effect", "ive-sticker",
                           "ive-transition", "ive-music"]
                    onDropped: function (drop) {
                        var seconds = drop.x / lanes.pps;
                        var music = (drop.source && drop.source.musicTrackId)
                            ? drop.source.musicTrackId : "";
                        if (music !== "") {
                            // A library track dropped anywhere lands on the
                            // Music lane at the drop time; the "cover the
                            // cut" switch of the Audio panel rides along.
                            Actions.invoke("timeline.place_music", {
                                track_id: music,
                                at: Math.max(0, seconds),
                                cover: drop.source.musicCover === true
                            });
                            drop.accept();
                            return;
                        }
                        var transition = (drop.source
                                          && drop.source.transitionId)
                            ? drop.source.transitionId : "";
                        if (transition !== "") {
                            // A transition belongs to an EDGE: the drop
                            // snaps to the nearest cut between two clips,
                            // or to the head/tail of the timeline (the
                            // intro from black / the outro to black).
                            var target = root.transitionTargetNear(seconds);
                            if (target !== null)
                                Actions.invoke("timeline.set_transition", {
                                    clip_id: target.clipId,
                                    transition_id: transition,
                                    duration: Transitions.default_duration(
                                        transition),
                                    edge: target.edge
                                });
                            drop.accept();
                            return;
                        }
                        var sticker = (drop.source && drop.source.stickerId)
                            ? drop.source.stickerId : "";
                        if (sticker !== "") {
                            Actions.invoke("timeline.place_sticker", {
                                sticker_id: sticker,
                                at: Math.max(0, seconds),
                                duration: 3.0
                            });
                            drop.accept();
                            return;
                        }
                        var effect = (drop.source && drop.source.effectId)
                            ? drop.source.effectId : "";
                        if (effect !== "") {
                            // Dropped over a video clip, the effect adopts
                            // its exact span - the common intent. On empty
                            // ground it covers three seconds and the trim
                            // handles take it from there.
                            var target = null;
                            var clips = Project.timelineClips;
                            for (var i = 0; i < clips.length; i++)
                                if (clips[i].track === 0 && clips[i].hasVideo
                                        && seconds >= clips[i].start
                                        && seconds < clips[i].end) {
                                    target = clips[i];
                                    break;
                                }
                            Actions.invoke("timeline.place_effect", {
                                effect_id: effect,
                                at: target !== null ? target.start : seconds,
                                duration: target !== null ? target.duration : 3.0
                            });
                            drop.accept();
                            return;
                        }
                        var id = (drop.source && drop.source.mediaId)
                            ? drop.source.mediaId : "";
                        if (id)
                            root.mediaDropped(id, seconds);
                        drop.accept();
                    }
                }

                // Insertion marker, so the landing point is never a guess.
                Rectangle {
                    visible: laneDrop.containsDrag
                    x: laneDrop.drag.x - 1
                    width: 2
                    height: content.height
                    color: Theme.c.accent
                    z: 6
                }

                Text {
                    visible: Project.isOpen && Project.timelineCount === 0
                    anchors.centerIn: parent
                    text: Tr.s["timeline.drop_hint"] || ""
                    color: Qt.alpha(root.onGlass, 0.45)
                    font.pixelSize: Theme.m.fontSizeSm
                }

                // ── tracks ────────────────────────────────────────
                Repeater {
                    model: root.tracks
                    delegate: Item {
                        id: lane
                        required property var modelData
                        required property int index
                        x: 0
                        y: lanes.trackY(index)
                        width: content.width
                        height: modelData.height

                        Rectangle {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: 1
                            color: Qt.alpha(root.onGlass, 0.10)
                        }

                        Repeater {
                            model: lane.modelData.clips
                            delegate: Rectangle {
                                id: clip
                                required property var modelData
                                /*! Pixels of drag in progress; back to 0 when
                                    the model answers the move. */
                                property real dragOffsetX: 0
                                /*! Live trim previews, in pixels: the pill
                                    reshapes under the pointer and the MODEL
                                    is asked once, on release. */
                                property real trimLeftPx: 0
                                property real trimRightPx: 0
                                readonly property bool dragging: clipDrag.active
                                // The padding that leaves glass visible around
                                // every clip - docs/UI_SHELL.md section 5.
                                x: modelData.from * lanes.pps + Theme.m.clipGap / 2
                                   + dragOffsetX + trimLeftPx
                                y: Theme.m.trackLanePadding
                                z: dragging ? 10 : 0
                                opacity: dragging ? 0.85 : 1.0
                                width: Math.max(2, (modelData.to - modelData.from) * lanes.pps
                                                   - Theme.m.clipGap
                                                   - trimLeftPx + trimRightPx)
                                height: lane.height - Theme.m.trackLanePadding * 2
                                radius: Theme.m.clipRadius
                                color: modelData.color
                                // NOT clipped: the selection glow and the
                                // drop shadow live just outside the pill.
                                // Whatever can overflow (wave, name) clips
                                // itself instead.
                                clip: false

                                readonly property bool selected:
                                    (root.selectedClipId === modelData.id
                                     && root.selectedKind
                                        === (lane.modelData.kind))
                                    || root.extraSelected.indexOf(
                                           modelData.id) >= 0

                                border.width: selected ? 2 : 1
                                border.color: selected
                                    ? Theme.c.clipSelected
                                    : Qt.rgba(1, 1, 1, 0.15)

                                // The clip sits ON the lane, not printed on
                                // it: a soft shade pooling under its foot.
                                Rectangle {
                                    anchors.top: parent.bottom
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.leftMargin: 3
                                    anchors.rightMargin: 3
                                    height: 3
                                    gradient: Gradient {
                                        GradientStop { position: 0
                                                       color: "#38000000" }
                                        GradientStop { position: 1
                                                       color: "#00000000" }
                                    }
                                }

                                // Selection glow: three fading halo rings,
                                // cheap borders instead of a shader - at a
                                // full timeline the selected clip must be
                                // findable at a glance.
                                Repeater {
                                    model: clip.selected ? 3 : 0
                                    delegate: Rectangle {
                                        required property int index
                                        anchors.fill: parent
                                        anchors.margins: -(2 + index * 2)
                                        radius: Theme.m.clipRadius
                                                + 2 + index * 2
                                        color: "transparent"
                                        border.width: 2
                                        border.color: Qt.alpha(
                                            Theme.c.clipSelected,
                                            0.28 - index * 0.09)
                                    }
                                }

                                // Thumbnail strip stand-in; real frames in stage 3.
                                Row {
                                    visible: clip.modelData.film
                                    anchors.fill: parent
                                    anchors.leftMargin: 3
                                    clip: true
                                    Repeater {
                                        model: Math.max(1, Math.floor(clip.width / 34))
                                        delegate: Item {
                                            width: 34
                                            height: clip.height
                                            Rectangle {
                                                anchors.right: parent.right
                                                width: 1
                                                height: parent.height
                                                color: Qt.alpha(root.onGlass, 0.12)
                                            }
                                        }
                                    }
                                }

                                // Film-strip perforations along the top and
                                // bottom edges: video clips only - "this is
                                // footage" readable at any zoom.
                                Row {
                                    objectName: "film_perfs_top"
                                    visible: clip.modelData.film
                                             && clip.height > 30
                                    x: 5
                                    y: 3
                                    spacing: 6
                                    Repeater {
                                        model: Math.max(0, Math.floor(
                                            (clip.width - 10) / 10))
                                        delegate: Rectangle {
                                            width: 4
                                            height: 4
                                            radius: 1
                                            color: "#4D000000"
                                        }
                                    }
                                }
                                Row {
                                    objectName: "film_perfs_bottom"
                                    visible: clip.modelData.film
                                             && clip.height > 30
                                    x: 5
                                    y: clip.height - 7
                                    spacing: 6
                                    Repeater {
                                        model: Math.max(0, Math.floor(
                                            (clip.width - 10) / 10))
                                        delegate: Rectangle {
                                            width: 4
                                            height: 4
                                            radius: 1
                                            color: "#4D000000"
                                        }
                                    }
                                }

                                Text {
                                    x: 7
                                    y: clip.modelData.film ? 9 : 4
                                    width: Math.max(0, clip.width - 14)
                                    elide: Text.ElideRight
                                    text: clip.modelData.name
                                    color: "#EAFFFFFF"
                                    font.pixelSize: Theme.m.fontSizeXs
                                    style: Text.Raised
                                    styleColor: "#99000000"
                                }

                                // The REAL waveform. The strip PNG covers
                                // the whole source file (Waves renders it
                                // once, off the GUI thread); this viewport
                                // shows the clip's slice by stretching the
                                // strip to the file's length at the current
                                // zoom and sliding it by sourceIn - so
                                // trim, split and zoom never re-decode.
                                Item {
                                    id: waveBox
                                    visible: clip.modelData.wave === true
                                    anchors.fill: parent
                                    anchors.topMargin: 3
                                    anchors.bottomMargin: 3
                                    clip: true
                                    readonly property real clipSeconds:
                                        Math.max(0.001, clip.modelData.to
                                                        - clip.modelData.from)
                                    // In TIMELINE seconds: a sped-up clip
                                    // squeezes the whole file into fewer
                                    // of them, and the strip follows.
                                    readonly property real paceOf:
                                        clip.modelData.speed || 1
                                    readonly property real mediaSeconds:
                                        clip.modelData.mediaDuration > 0
                                            ? clip.modelData.mediaDuration
                                              / paceOf
                                            : clipSeconds

                                    // The wave wears the clip's own colour, a
                                    // lighter shade: the strip is rendered white
                                    // once per file and tinted here, so A1 and
                                    // Music share one cache.
                                    readonly property color waveColor:
                                        Qt.lighter(clip.modelData.color, 1.75)

                                    Image {
                                        id: waveImage
                                        visible: false
                                        asynchronous: true
                                        fillMode: Image.Stretch
                                        smooth: true
                                        height: parent.height
                                        width: parent.width
                                               * waveBox.mediaSeconds
                                               / waveBox.clipSeconds
                                        x: -parent.width
                                           * ((clip.modelData.sourceIn || 0)
                                              / waveBox.paceOf)
                                           / waveBox.clipSeconds
                                        source: {
                                            Waves.rev;   // re-ask on arrival
                                            return waveBox.visible
                                                   && clip.modelData.path
                                                ? Waves.wave(clip.modelData.path)
                                                : "";
                                        }
                                    }

                                    // The fades, drawn as what they do: a
                                    // dark shade swallowing the wave, rising
                                    // out of it at the head and sinking back
                                    // into it at the tail. Its width IS the
                                    // fade's length at the current zoom.
                                    readonly property real fadeInPx:
                                        Math.min(width, width
                                            * (clip.modelData.fadeIn || 0)
                                            / clipSeconds)
                                    readonly property real fadeOutPx:
                                        Math.min(width, width
                                            * (clip.modelData.fadeOut || 0)
                                            / clipSeconds)
                                    // The audio effect on this clip, named on
                                    // the clip itself: a small tag in the top
                                    // right corner (it hides when the clip is
                                    // too narrow to carry words).
                                    Rectangle {
                                        objectName: "audio_effect_tag"
                                        visible: !!clip.modelData.effect
                                                 && waveBox.width > effectTag.implicitWidth + 40
                                        anchors.top: parent.top
                                        anchors.right: parent.right
                                        anchors.margins: 2
                                        width: effectTag.implicitWidth + 10
                                        height: effectTag.implicitHeight + 4
                                        radius: height / 2
                                        color: Qt.rgba(0, 0, 0, 0.55)
                                        z: 2
                                        Text {
                                            id: effectTag
                                            anchors.centerIn: parent
                                            text: clip.modelData.effect
                                                ? "fx · " + AudioFx.effect_name(clip.modelData.effect)
                                                : ""
                                            color: "#FFFFFF"
                                            font.pixelSize: Theme.m.fontSizeXs
                                        }
                                    }
                                    Shape {
                                        objectName: "fade_in_shade"
                                        visible: waveBox.fadeInPx > 0.5
                                        anchors.fill: parent
                                        preferredRendererType: Shape.CurveRenderer
                                        ShapePath {
                                            strokeWidth: 1.5
                                            strokeColor: Qt.rgba(0, 0, 0, 0.85)
                                            fillColor: Qt.rgba(0, 0, 0, 0.55)
                                            startX: 0; startY: 0
                                            PathLine { x: waveBox.fadeInPx; y: 0 }
                                            // A quarter-sine curve: the
                                            // equal-power ramp the engine plays.
                                            PathQuad {
                                                x: 0; y: waveBox.height
                                                controlX: waveBox.fadeInPx * 0.45
                                                controlY: waveBox.height * 0.9
                                            }
                                            PathLine { x: 0; y: 0 }
                                        }
                                    }
                                    Shape {
                                        objectName: "fade_out_shade"
                                        visible: waveBox.fadeOutPx > 0.5
                                        anchors.fill: parent
                                        preferredRendererType: Shape.CurveRenderer
                                        ShapePath {
                                            strokeWidth: 1.5
                                            strokeColor: Qt.rgba(0, 0, 0, 0.85)
                                            fillColor: Qt.rgba(0, 0, 0, 0.55)
                                            startX: waveBox.width; startY: 0
                                            PathLine {
                                                x: waveBox.width - waveBox.fadeOutPx
                                                y: 0
                                            }
                                            PathQuad {
                                                x: waveBox.width; y: waveBox.height
                                                controlX: waveBox.width
                                                          - waveBox.fadeOutPx * 0.45
                                                controlY: waveBox.height * 0.9
                                            }
                                            PathLine { x: waveBox.width; y: 0 }
                                        }
                                    }

                                    MultiEffect {
                                        source: waveImage
                                        x: waveImage.x
                                        width: waveImage.width
                                        height: waveImage.height
                                        visible: waveImage.status === Image.Ready
                                        colorization: 1.0
                                        colorizationColor: waveBox.waveColor
                                    }

                                    // WHERE the ducking presses the bed
                                    // down: a dark strip whose opacity
                                    // follows the engine's own envelope
                                    // (DuckShade runs it offline). Music
                                    // lane only, and only when ducked.
                                    Image {
                                        objectName: "duck_shade"
                                        visible: status === Image.Ready
                                        anchors.fill: parent
                                        fillMode: Image.Stretch
                                        smooth: true
                                        asynchronous: true
                                        z: 1
                                        source: {
                                            DuckShade.rev;   // re-ask on arrival
                                            return clip.modelData.duck === true
                                                ? DuckShade.shade(clip.modelData.id)
                                                : "";
                                        }
                                    }

                                    // Stand-in bars ONLY while the strip is
                                    // being rendered for the first time.
                                    Row {
                                        visible: waveImage.status !== Image.Ready
                                        anchors.fill: parent
                                        spacing: 1
                                        Repeater {
                                            model: Math.max(1, Math.floor(clip.width / 4))
                                            delegate: Rectangle {
                                                required property int index
                                                width: 3
                                                height: parent.height *
                                                    (0.22 + 0.72 * Math.abs(
                                                        Math.sin(index * 0.7)
                                                        * Math.cos(index * 0.13)))
                                                anchors.verticalCenter: parent.verticalCenter
                                                color: Qt.alpha(waveBox.waveColor, 0.45)
                                                radius: 1
                                            }
                                        }
                                    }
                                }

                                // Keyframe diamonds, along the pill's foot:
                                // one per pin, at its clip-local time.
                                Repeater {
                                    model: clip.modelData.keys || []
                                    delegate: Rectangle {
                                        required property var modelData
                                        width: 7
                                        height: 7
                                        rotation: 45
                                        z: 4
                                        color: "#FFFFFF"
                                        border.width: 1
                                        border.color: "#59000000"
                                        x: modelData / Math.max(0.001,
                                               clip.modelData.to
                                               - clip.modelData.from)
                                           * clip.width - 3.5
                                        y: clip.height - 11
                                    }
                                }

                                // Tap selects (and the content handler under
                                // this one moves the playhead there, which is
                                // exactly where a split wants it). Double-tap
                                // keeps the old "open this file in the
                                // preview" behaviour.
                                TapHandler {
                                    acceptedModifiers: Qt.NoModifier
                                    onTapped: {
                                        root.extraSelected = [];
                                        root.selectedClipId = clip.modelData.id;
                                        root.selectedKind =
                                            lane.modelData.kind;
                                        root.openPanelFor(lane.modelData.kind);
                                    }
                                    onDoubleTapped: {
                                        if (clip.modelData.id)
                                            Actions.invoke("timeline.preview_clip",
                                                           { clip_id: clip.modelData.id });
                                    }
                                }
                                // Ctrl+click grows the selection instead
                                // of replacing it.
                                TapHandler {
                                    acceptedModifiers: Qt.ControlModifier
                                    onTapped: root.toggleExtra(
                                        clip.modelData.id,
                                        lane.modelData.kind)
                                }

                                // Reorder by dragging. The clip follows the
                                // pointer; on release the MODEL decides the
                                // order (midpoint rule in project.py) and the
                                // rebuilt timeline snaps everything in place.
                                DragHandler {
                                    id: clipDrag
                                    target: null
                                    xAxis.enabled: true
                                    yAxis.enabled: false
                                    // A drag born on a trim handle is a
                                    // resize, never a move.
                                    enabled: !leftTrim.active && !rightTrim.active
                                    // The lanes live inside a Flickable;
                                    // without this, panning steals the
                                    // gesture and no clip ever moves.
                                    grabPermissions:
                                        PointerHandler.CanTakeOverFromAnything
                                    onTranslationChanged: {
                                        if (active)
                                            clip.dragOffsetX = translation.x;
                                    }
                                    onActiveChanged: {
                                        if (active) {
                                            root.selectedClipId = clip.modelData.id;
                                            root.selectedKind =
                                                lane.modelData.kind;
                                            return;
                                        }
                                        var moved = clip.dragOffsetX / lanes.pps;
                                        clip.dragOffsetX = 0;
                                        if (Math.abs(moved) < 0.05)
                                            return;   // a twitch, not a move
                                        Actions.invoke("timeline.move_clip", {
                                            clip_id: clip.modelData.id,
                                            to: Math.max(0, clip.modelData.from + moved)
                                        });
                                    }
                                }
                                HoverHandler {
                                    cursorShape: clipDrag.active
                                        ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                                }

                                // ── trim handles ──────────────────────
                                // 8px zones on either edge: the pointer
                                // becomes a resize arrow, dragging reshapes
                                // the pill live, and the release asks the
                                // model for the real trim - clamped to the
                                // source there, snapped to neighbours here
                                // (snapTime: the magnet across lanes).
                                Item {
                                    id: leftHandle
                                    width: 8
                                    height: parent.height
                                    anchors.left: parent.left
                                    visible: clip.width > 26
                                    z: 5
                                    HoverHandler { cursorShape: Qt.SizeHorCursor }
                                    DragHandler {
                                        id: leftTrim
                                        target: null
                                        xAxis.enabled: true
                                        yAxis.enabled: false
                                        grabPermissions:
                                            PointerHandler.CanTakeOverFromAnything
                                        onTranslationChanged: {
                                            if (!active)
                                                return;
                                            // New head position, snapped and
                                            // clamped: never before the
                                            // source's own start, never past
                                            // the tail.
                                            var proposed = clip.modelData.from
                                                + translation.x / lanes.pps;
                                            proposed = root.snapTime(
                                                proposed, clip.modelData.id,
                                                8 / lanes.pps);
                                            var clipData = root.clipDataFor(
                                                clip.modelData.id);
                                            // A clip WITH a source cannot show
                                            // material before its own frame 0;
                                            // one without (sticker, text,
                                            // effect) grows left freely. The
                                            // source is consumed at the clip's
                                            // PACE: at 2x, one second of head
                                            // room is half a timeline second.
                                            var minStart = clipData
                                                && clipData.mediaDuration > 0
                                                ? clip.modelData.from
                                                  - clipData.sourceIn
                                                    / (clipData.speed || 1)
                                                : 0;
                                            proposed = Math.max(minStart,
                                                Math.min(clip.modelData.to - 0.1,
                                                         proposed));
                                            clip.trimLeftPx =
                                                (proposed - clip.modelData.from)
                                                * lanes.pps;
                                        }
                                        onActiveChanged: {
                                            if (active) {
                                                root.selectedClipId = clip.modelData.id;
                                                root.selectedKind =
                                                    lane.modelData.kind;
                                                return;
                                            }
                                            var delta = clip.trimLeftPx / lanes.pps;
                                            clip.trimLeftPx = 0;
                                            if (Math.abs(delta) < 0.02)
                                                return;
                                            var clipData = root.clipDataFor(
                                                clip.modelData.id);
                                            if (clipData === null)
                                                return;
                                            Actions.invoke("timeline.trim_clip", {
                                                clip_id: clipData.id,
                                                source_in: clipData.sourceIn
                                                    + delta * (clipData.speed
                                                               || 1),
                                                duration: clipData.duration - delta,
                                                // The LEFT edge is the one
                                                // moving: free lanes take the
                                                // new start (track 0 reflows
                                                // over it anyway).
                                                start: clipData.start + delta
                                            });
                                        }
                                    }
                                }

                                Item {
                                    id: rightHandle
                                    width: 8
                                    height: parent.height
                                    anchors.right: parent.right
                                    visible: clip.width > 26
                                    z: 5
                                    HoverHandler { cursorShape: Qt.SizeHorCursor }
                                    DragHandler {
                                        id: rightTrim
                                        target: null
                                        xAxis.enabled: true
                                        yAxis.enabled: false
                                        grabPermissions:
                                            PointerHandler.CanTakeOverFromAnything
                                        onTranslationChanged: {
                                            if (!active)
                                                return;
                                            var proposed = clip.modelData.to
                                                + translation.x / lanes.pps;
                                            proposed = root.snapTime(
                                                proposed, clip.modelData.id,
                                                8 / lanes.pps);
                                            var clipData = root.clipDataFor(
                                                clip.modelData.id);
                                            // The tail cannot outrun the
                                            // source material - which lasts
                                            // fewer timeline seconds the
                                            // faster the clip plays.
                                            var maxEnd = clip.modelData.from
                                                + (clipData && clipData.mediaDuration > 0
                                                   ? (clipData.mediaDuration
                                                      - clipData.sourceIn)
                                                     / (clipData.speed || 1)
                                                   : 1e9);
                                            proposed = Math.min(maxEnd,
                                                Math.max(clip.modelData.from + 0.1,
                                                         proposed));
                                            clip.trimRightPx =
                                                (proposed - clip.modelData.to)
                                                * lanes.pps;
                                        }
                                        onActiveChanged: {
                                            if (active) {
                                                root.selectedClipId = clip.modelData.id;
                                                root.selectedKind =
                                                    lane.modelData.kind;
                                                return;
                                            }
                                            var delta = clip.trimRightPx / lanes.pps;
                                            clip.trimRightPx = 0;
                                            if (Math.abs(delta) < 0.02)
                                                return;
                                            var clipData = root.clipDataFor(
                                                clip.modelData.id);
                                            if (clipData === null)
                                                return;
                                            Actions.invoke("timeline.trim_clip", {
                                                clip_id: clipData.id,
                                                source_in: clipData.sourceIn,
                                                duration: clipData.duration + delta
                                            });
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // ── transition pills on V1 ────────────────────────
                // One WHITE pill per placed transition, sitting over
                // the video lane, a little shorter than the clips so it
                // reads as "between them". Its span IS the blend
                // window: trim either edge to change the duration, tap
                // to select (the toolbox trash removes it).
                Repeater {
                    model: root.transitionPills
                    delegate: Item {
                        id: pill
                        required property var modelData
                        objectName: "transition_pill_" + modelData.kind
                                    + "_" + modelData.clipId
                        /*! Live trim previews, in pixels; the MODEL is
                            asked once, on release - the pill's width in
                            seconds becomes the new duration. */
                        property real trimLeftPx: 0
                        property real trimRightPx: 0
                        // At default zoom a short transition is only a
                        // handful of pixels: the pill keeps a minimum
                        // width so it stays visible and TAPPABLE (the
                        // toolbar slider handles the duration there).
                        readonly property real spanPx:
                            (modelData.to - modelData.from) * lanes.pps
                        readonly property bool wide: spanPx > 46
                        x: modelData.from * lanes.pps + trimLeftPx
                           - (width - (spanPx - trimLeftPx + trimRightPx)) / 2
                        y: lanes.trackY(0) + Theme.m.trackLanePadding + 5
                        width: Math.max(26, spanPx - trimLeftPx + trimRightPx)
                        height: (root.tracks.length > 0
                                 ? root.tracks[0].height : 64)
                                - Theme.m.trackLanePadding * 2 - 10
                        z: 8

                        readonly property bool selected:
                            root.selectedKind === "transition"
                            && root.selectedTransition !== null
                            && root.selectedTransition.clipId
                               === modelData.clipId
                            && root.selectedTransition.edge
                               === (modelData.kind === "in" ? "in" : "out")

                        function commitTrim() {
                            var seconds = pill.width / lanes.pps;
                            pill.trimLeftPx = 0;
                            pill.trimRightPx = 0;
                            Actions.invoke("timeline.set_transition", {
                                clip_id: pill.modelData.clipId,
                                transition_id: pill.modelData.tid,
                                duration: Math.round(seconds * 100) / 100,
                                edge: pill.modelData.kind === "in"
                                    ? "in" : "out"
                            });
                        }

                        Rectangle {
                            anchors.fill: parent
                            radius: Theme.m.clipRadius
                            color: "#FFFFFF"
                            border.width: pill.selected ? 2 : 1
                            border.color: pill.selected
                                ? Theme.c.clipSelected : "#40000000"
                        }
                        // The mark inside: the SAME icon the tool rail
                        // uses for transitions, so the pill and the
                        // panel that edits it read as one thing (the
                        // old diamond now belongs to the keyframes).
                        Glyph {
                            anchors.centerIn: parent
                            width: Math.min(22, parent.height * 0.8,
                                            parent.width * 0.8)
                            height: width
                            path: Icons.transition
                            color: "#88333333"
                        }

                        // MouseAreas rather than handlers, DELIBERATELY:
                        // a MouseArea consumes the press, so the clip
                        // underneath never sees the tap - with handlers
                        // both fired, the clip stole the selection and
                        // the trash then deleted the CLIP, not the
                        // transition.
                        MouseArea {
                            anchors.fill: parent
                            // On a narrow pill the WHOLE surface selects;
                            // the trim zones only exist when there is
                            // room for them too.
                            anchors.leftMargin: pill.wide ? 8 : 0
                            anchors.rightMargin: pill.wide ? 8 : 0
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                root.selectedClipId = pill.modelData.clipId;
                                root.selectedKind = "transition";
                                root.selectedTransition = {
                                    clipId: pill.modelData.clipId,
                                    edge: pill.modelData.kind === "in"
                                        ? "in" : "out"
                                };
                            }
                        }

                        // ── trim: either edge resizes the window ──
                        MouseArea {
                            visible: pill.wide
                            width: 8
                            height: parent.height
                            anchors.left: parent.left
                            cursorShape: Qt.SizeHorCursor
                            // The clip's own DragHandler underneath is
                            // allowed to take over from anything; without
                            // this it steals the trim mid-drag and moves
                            // the CLIP instead.
                            preventStealing: true
                            property real pressX: 0
                            onPressed: function (mouse) {
                                pressX = mapToItem(content, mouse.x, 0).x;
                            }
                            onPositionChanged: function (mouse) {
                                if (pressed)
                                    pill.trimLeftPx = mapToItem(
                                        content, mouse.x, 0).x - pressX;
                            }
                            onReleased: pill.commitTrim()
                        }
                        MouseArea {
                            visible: pill.wide
                            width: 8
                            height: parent.height
                            anchors.right: parent.right
                            cursorShape: Qt.SizeHorCursor
                            preventStealing: true
                            property real pressX: 0
                            onPressed: function (mouse) {
                                pressX = mapToItem(content, mouse.x, 0).x;
                            }
                            onPositionChanged: function (mouse) {
                                if (pressed)
                                    pill.trimRightPx = mapToItem(
                                        content, mouse.x, 0).x - pressX;
                            }
                            onReleased: pill.commitTrim()
                        }
                    }
                }

                }   // content
                }   // scroller

                // ── ruler, PINNED along the bottom edge ───────────
                // Outside the Flickable on purpose: the time stays on
                // screen however many lanes stack up - only the tracks
                // scroll vertically. The tick strip follows contentX so
                // the numbers stay under their clips, and tapping it
                // still moves the playhead.
                Item {
                    id: ruler
                    objectName: "timeline_ruler"
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: lanes.rulerH
                    clip: true

                    // The scale ADAPTS to what a label needs to stay
                    // readable: one tick a second with a label every five
                    // is right for a 30 s clip and a solid smear for an
                    // hour-long one. Each rung is [seconds between labels,
                    // minor ticks per label]; the first rung whose labels
                    // land at least minLabelPx apart wins, so zooming in
                    // walks down the ladder and zooming out climbs it.
                    readonly property real minLabelPx: 110
                    readonly property var ladder: [
                        [1, 2], [2, 2], [5, 5], [10, 5], [15, 3], [30, 6],
                        [60, 6], [120, 4], [300, 5], [600, 5], [900, 3],
                        [1800, 6], [3600, 6], [7200, 4], [14400, 4],
                        [21600, 6], [43200, 6], [86400, 6]]
                    readonly property var rung: {
                        for (var i = 0; i < ladder.length; i++)
                            if (ladder[i][0] * lanes.pps >= minLabelPx)
                                return ladder[i];
                        return ladder[ladder.length - 1];
                    }
                    readonly property real majorStep: rung[0]
                    readonly property int minorPerMajor: rung[1]
                    readonly property real minorStep: majorStep / minorPerMajor
                    // Only the ticks under the viewport exist (plus one
                    // label's worth on the left, so a label whose tick has
                    // scrolled out still shows): the delegate count follows
                    // the WIDTH, never the duration.
                    readonly property int firstTick: Math.max(0, Math.floor(
                        scroller.contentX / lanes.pps / minorStep) - minorPerMajor)
                    readonly property int tickCount: Math.ceil(
                        scroller.width / lanes.pps / minorStep) + minorPerMajor + 2

                    function label(seconds) {
                        var s = Math.round(seconds);
                        return "%1:%2:%3"
                            .arg(String(Math.floor(s / 3600)).padStart(2, "0"))
                            .arg(String(Math.floor(s / 60) % 60).padStart(2, "0"))
                            .arg(String(s % 60).padStart(2, "0"));
                    }

                    Item {
                        width: scroller.contentWidth
                        height: parent.height
                        x: -scroller.contentX

                        Repeater {
                            model: ruler.tickCount
                            delegate: Item {
                                id: tick
                                required property int index
                                readonly property int n: ruler.firstTick + index
                                readonly property real seconds: n * ruler.minorStep
                                readonly property bool major: n % ruler.minorPerMajor === 0
                                visible: seconds <= root.duration
                                x: seconds * lanes.pps
                                y: 0
                                width: 1
                                height: ruler.height

                                Rectangle {
                                    y: tick.major ? 0 : ruler.height * 0.55
                                    width: 1
                                    height: tick.major ? ruler.height : ruler.height * 0.45
                                    color: Qt.alpha(root.onGlass, tick.major ? 0.45 : 0.18)
                                }
                                Text {
                                    visible: tick.major && tick.seconds < root.duration
                                    x: 5
                                    anchors.bottom: parent.bottom
                                    anchors.bottomMargin: 3
                                    text: ruler.label(tick.seconds)
                                    color: root.onGlass
                                    font.pixelSize: Theme.m.fontSizeXs
                                    font.family: "monospace"
                                }
                            }
                        }
                    }
                    Rectangle {
                        anchors.top: parent.top
                        width: parent.width
                        height: 1
                        color: Qt.alpha(root.onGlass, 0.10)
                    }
                    TapHandler {
                        onTapped: function (point) {
                            root.seekRequested((scroller.contentX
                                                + point.position.x) / lanes.pps);
                        }
                    }
                }

                // ── playhead ──────────────────────────────────────
                // A sibling of the Flickable, not a child of the scrolled
                // content: the head lives in the pinned ruler strip and
                // the line must span whatever part of the tracks is on
                // show - it follows contentX only.
                //
                // The line ends where the head begins: the head is a HOLLOW
                // rounded droplet (outline only), and a line running through
                // its empty middle would read as a mistake. Apex up, body in
                // the bottom ruler strip - the tapered tip is what continues
                // into the line.
                Item {
                    x: root.position * lanes.pps - scroller.contentX
                    y: 0
                    width: 2
                    height: lanes.height

                    Rectangle {
                        width: 2
                        height: lanes.height - lanes.rulerH
                        color: Theme.c.playhead
                    }

                    Shape {
                        x: -5   // centre the 12px head on the 2px line
                        y: lanes.height - lanes.rulerH - 1
                        width: 12
                        height: 16
                        preferredRendererType: Shape.CurveRenderer
                        ShapePath {
                            strokeColor: Theme.c.playhead
                            strokeWidth: 1.6
                            fillColor: "transparent"
                            capStyle: ShapePath.RoundCap
                            joinStyle: ShapePath.RoundJoin
                            // A droplet: tapered tip at the top flaring into
                            // a rounded body, closed at the bottom.
                            PathSvg {
                                path: "M6 1
                                       C7.2 3.2 11 4.8 11 8.2
                                       L11 10.5
                                       C11 13.6 9 15 6 15
                                       C3 15 1 13.6 1 10.5
                                       L1 8.2
                                       C1 4.8 4.8 3.2 6 1 Z"
                            }
                        }
                    }
                }

                // ── vertical scrollbar ────────────────────────────
                // Hand-rolled (no Quick Controls in this shell): the
                // handle is a pure binding from contentY, and pressing or
                // dragging anywhere on the strip drives contentY - no
                // drag.target, so there is no binding to break.
                Item {
                    id: vbar
                    objectName: "timeline_vscroll"
                    visible: scroller.contentHeight > scroller.height + 1
                    x: lanes.width - width
                    width: 10
                    height: scroller.height

                    Rectangle {
                        id: vbarHandle
                        x: 3
                        width: 4
                        radius: 2
                        color: Qt.alpha(root.onGlass,
                                        vbarArea.pressed ? 0.55
                                        : vbarArea.containsMouse ? 0.40 : 0.25)
                        height: Math.max(24, vbar.height * scroller.height
                                             / Math.max(1, scroller.contentHeight))
                        y: (vbar.height - height)
                           * scroller.contentY
                           / Math.max(1, scroller.contentHeight - scroller.height)
                    }

                    MouseArea {
                        id: vbarArea
                        anchors.fill: parent
                        hoverEnabled: true

                        function scrollTo(mouseY) {
                            var span = Math.max(1, vbar.height - vbarHandle.height);
                            var frac = Math.max(0, Math.min(1,
                                (mouseY - vbarHandle.height / 2) / span));
                            scroller.contentY = frac
                                * (scroller.contentHeight - scroller.height);
                        }
                        onPressed: function (mouse) { scrollTo(mouse.y); }
                        onPositionChanged: function (mouse) {
                            if (pressed)
                                scrollTo(mouse.y);
                        }
                    }
                }
            }
        }
    }
}
