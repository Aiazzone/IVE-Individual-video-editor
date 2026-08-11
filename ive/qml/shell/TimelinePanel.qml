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
                           name: c.name, film: true, id: c.id, wave: false };
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
                           mediaDuration: c.mediaDuration };
              }) }
        ];
        // The Color lane exists only while something sits on it: an empty
        // permanent lane would just be chrome.
        var fx = clips.filter(function (c) { return c.track === 1; });
        if (fx.length > 0)
            lanes.push({ name: "Color", kind: "color", audio: false,
                         height: Theme.m.trackHeightAudio,
                         clips: fx.map(function (c) {
                             return { from: c.start, to: c.end,
                                      color: Theme.c.clipEffect,
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
          kinds: ["video", "audio", "color"],
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
          kinds: ["audio"],
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
        { icon: Icons.trash,
          label: Tr.s["timeline.delete"] || "",
          kinds: ["video", "color"],
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
            AppSlider {
                id: clipVolume
                visible: root.selectedKind === "audio"
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
            ColumnLayout {
                Layout.fillWidth: false
                Layout.preferredWidth: Theme.m.trackHeaderWidth
                Layout.minimumWidth: Theme.m.trackHeaderWidth
                Layout.maximumWidth: Theme.m.trackHeaderWidth
                Layout.fillHeight: true
                spacing: 0

                // Only the track NAME: the eye/lock/mute buttons that used
                // to sit here were placeholders wired to nothing, and dead
                // chrome teaches the user to ignore this column. They come
                // back one by one WITH their behaviour (hide/lock/mute per
                // track), which is what this column is for in every editor.
                // No ruler spacer: the ruler lives at the BOTTOM now.
                Repeater {
                    model: root.tracks
                    delegate: Item {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: modelData.height

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            x: Theme.m.space2
                            text: parent.modelData.name
                            color: Qt.alpha(root.onGlass, 0.72)
                            font.pixelSize: Theme.m.fontSizeSm
                            font.letterSpacing: 0.5
                        }
                    }
                }
                Item { Layout.fillWidth: true; Layout.fillHeight: true }
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

                readonly property real pps:
                    width * root.zoom / Math.max(0.001, root.duration)
                readonly property real rulerH: Theme.m.rulerHeight

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

                Flickable {
                    id: scroller
                    anchors.fill: parent
                    contentWidth: width * root.zoom
                    contentHeight: height
                    interactive: root.zoom > 1
                    flickableDirection: Flickable.HorizontalFlick
                    boundsBehavior: Flickable.StopAtBounds

                Item {
                    id: content
                    width: scroller.contentWidth
                    height: scroller.height

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
                // editor meaning of the wheel. On the CONTENT item, not on
                // `lanes`: once interactive, the Flickable would swallow
                // the wheel for panning before an outer handler saw it.
                WheelHandler {
                    target: null
                    onWheel: function (event) {
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
                    keys: ["ive-media", "ive-effect"]
                    onDropped: function (drop) {
                        var seconds = drop.x / lanes.pps;
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

                // ── ruler, along the BOTTOM edge ──────────────────
                // Mirrored from the usual top position: ticks grow upwards
                // from the bottom edge and the labels sit at the bottom.
                Item {
                    id: ruler
                    y: content.height - lanes.rulerH
                    width: content.width
                    height: lanes.rulerH

                    Repeater {
                        model: Math.floor(root.duration) + 1
                        delegate: Item {
                            id: tick
                            required property int index
                            readonly property bool major: index % 5 === 0
                            x: index * lanes.pps
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
                                visible: tick.major && tick.index < root.duration
                                x: 5
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 3
                                text: "00:%1:%2"
                                    .arg(String(Math.floor(tick.index / 60)).padStart(2, "0"))
                                    .arg(String(tick.index % 60).padStart(2, "0"))
                                color: root.onGlass
                                font.pixelSize: Theme.m.fontSizeXs
                                font.family: "monospace"
                            }
                        }
                    }
                    Rectangle {
                        anchors.top: parent.top
                        width: parent.width
                        height: 1
                        color: Qt.alpha(root.onGlass, 0.10)
                    }
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
                                clip: true

                                readonly property bool selected:
                                    root.selectedClipId === modelData.id
                                    && root.selectedKind
                                       === (lane.modelData.kind)

                                border.width: selected ? 2 : 1
                                border.color: selected
                                    ? Theme.c.clipSelected
                                    : Qt.rgba(1, 1, 1, 0.15)

                                // Thumbnail strip stand-in; real frames in stage 3.
                                Row {
                                    visible: clip.modelData.film
                                    anchors.fill: parent
                                    anchors.leftMargin: 3
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

                                Text {
                                    x: 7
                                    y: 4
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
                                    readonly property real mediaSeconds:
                                        clip.modelData.mediaDuration > 0
                                            ? clip.modelData.mediaDuration
                                            : clipSeconds

                                    Image {
                                        id: waveImage
                                        asynchronous: true
                                        fillMode: Image.Stretch
                                        smooth: true
                                        height: parent.height
                                        width: parent.width
                                               * waveBox.mediaSeconds
                                               / waveBox.clipSeconds
                                        x: -parent.width
                                           * (clip.modelData.sourceIn || 0)
                                           / waveBox.clipSeconds
                                        source: {
                                            Waves.rev;   // re-ask on arrival
                                            return waveBox.visible
                                                   && clip.modelData.path
                                                ? Waves.wave(clip.modelData.path)
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
                                                color: Qt.rgba(1, 1, 1, 0.30)
                                                radius: 1
                                            }
                                        }
                                    }
                                }

                                // Tap selects (and the content handler under
                                // this one moves the playhead there, which is
                                // exactly where a split wants it). Double-tap
                                // keeps the old "open this file in the
                                // preview" behaviour.
                                TapHandler {
                                    onTapped: {
                                        root.selectedClipId = clip.modelData.id;
                                        root.selectedKind =
                                            lane.modelData.kind;
                                    }
                                    onDoubleTapped: {
                                        if (clip.modelData.id)
                                            Actions.invoke("timeline.preview_clip",
                                                           { clip_id: clip.modelData.id });
                                    }
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
                                            var minStart = clip.modelData.from
                                                - (clipData ? clipData.sourceIn : 0);
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
                                                source_in: clipData.sourceIn + delta,
                                                duration: clipData.duration - delta
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
                                            // source material.
                                            var maxEnd = clip.modelData.from
                                                + (clipData && clipData.mediaDuration > 0
                                                   ? clipData.mediaDuration
                                                     - clipData.sourceIn
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

                // ── playhead ──────────────────────────────────────
                // The line ends where the head begins: the head is a HOLLOW
                // rounded droplet (outline only), and a line running through
                // its empty middle would read as a mistake. Apex up, body in
                // the bottom ruler strip - the tapered tip is what continues
                // into the line.
                Item {
                    x: root.position * lanes.pps
                    y: 0
                    width: 2
                    height: content.height

                    Rectangle {
                        width: 2
                        height: content.height - lanes.rulerH
                        color: Theme.c.playhead
                    }

                    Shape {
                        x: -5   // centre the 12px head on the 2px line
                        y: content.height - lanes.rulerH - 1
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

                }   // content
                }   // scroller
            }
        }
    }
}
