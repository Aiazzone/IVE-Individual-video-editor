// The immersive shell.
//
// Layer order (docs/UI_SHELL.md section 2):
//   0  ambient backdrop      blurred, enlarged copy of the frame
//   1  video                 whole frame, inside the free area
//   2  transport / readout
//   3  timeline              glass, full window width
//   4  tool rail             glass
//   5  floating panel        solid
//
// `sceneLayer` holds layers 0-1 and is what every glass surface samples.
// It must not be an ancestor of the overlays, or the scene graph recurses.
import QtQuick
import QtQuick.Window
import QtQuick.Dialogs
import components
import shell
import IVE

Window {
    id: win

    width: 1440
    height: 900
    minimumWidth: 960
    minimumHeight: 600
    visible: true
    color: Theme.c.bgRoot
    title: Tr.s["app.title"] || "IVE"

    /*! Driven from Python (_apply_window_state) and by the fullscreen action. */
    property bool isFullscreen: false
    // Deferred ON PURPOSE. isFullscreen is written from Python, and a
    // synchronous assignment here runs setVisibility inside that Python
    // frame - which holds the GIL. setVisibility blocks on the render
    // thread's scene-graph sync, and the sync needs the GIL to call the
    // Python paint() of PreviewItem (QQuickPaintedItem): GUI waits for
    // render, render waits for the GIL, the GIL is the GUI's. Proven twice
    // with native stacks (py-spy --native); tests/visual/
    // test_fullscreen_cycles.py froze on it reliably. Qt.callLater runs
    // the assignment from the C++ event loop, where PySide has released
    // the GIL, so the sync can complete. Coalescing is fine: the callback
    // reads the CURRENT value, so the last toggle wins.
    onIsFullscreenChanged: Qt.callLater(function () {
        visibility = isFullscreen ? Window.FullScreen : Window.Windowed;
    })

    // ── shell state ───────────────────────────────────────────────
    readonly property bool railLeft: Shell.v.railSide === "left"
    readonly property real margin: Theme.m.space3
    readonly property real railSpace: Theme.m.toolRailWidth + margin * 2
    readonly property real panelSpace: panel.width + margin * 2
    readonly property real timelineHeight: Shell.v.timelineHeight

    // Declared on the window, not read off the item: sibling bindings are
    // evaluated before `idleClip` exists, and reading `.visible` off a null id
    // produces a startup warning.
    readonly property bool idleActive:
        !Playback.hasMedia && Shell.v.idleBackground && !Shell.v.windowHidden

    property string section: ""
    property bool playing: false
    property real position: 0
    readonly property real duration: 32

    function timecode(seconds) {
        var f = Math.floor((seconds % 1) * 30);
        var s = Math.floor(seconds) % 60;
        var m = Math.floor(seconds / 60);
        function pad(n) { return String(n).padStart(2, "0"); }
        return "00:" + pad(m) + ":" + pad(s) + ":" + pad(f);
    }

    function openSection(key) {
        if (section === key) {
            section = "";
            return;
        }
        section = key;
        var entry = rail.sections.find(function (e) { return e.key === key; });
        panel.open(key, entry ? (Tr.s[entry.label] || entry.label) : key,
                   entry ? entry.icon : "");
    }

    // Playback stand-in until stage 2: enough to see the playhead move and the
    // transport auto-hide behave. Replaced by PlaybackService.
    Timer {
        running: win.playing && !Playback.hasMedia
        interval: 33
        repeat: true
        onTriggered: win.position = (win.position + 0.033) % win.duration
    }

    // ── layer 0-1: the scene every glass surface samples ──────────
    Item {
        id: sceneLayer
        anchors.fill: parent

        // Drawn, not decoded. The geometry is built once and only a
        // translation animates, so this costs the GPU a few transforms and
        // the CPU nothing per frame - unlike the video loop it replaces,
        // which spent ~5 ms per frame decoding something nobody looks at.
        Rectangle {
            anchors.fill: parent
            visible: win.idleActive
            color: Theme.c.bgRoot
        }
        IdleBackdrop {
            anchors.fill: parent
            visible: win.idleActive
        }

        // With a project open the backdrop is the user's own frame.
        AmbientBackdrop {
            anchors.fill: parent
            visible: !win.idleActive
            sourceItem: video
        }

        // Free area: what is left once rail, panel and timeline are subtracted.
        Item {
            id: freeArea
            anchors.fill: parent
            // Only the rail and the timeline take space away from the video.
            // The floating panel is an overlay: subtracting it made the frame
            // jump sideways every time the panel opened, and moved everything
            // anchored to the video with it.
            anchors.leftMargin: win.railLeft ? win.railSpace : win.margin
            anchors.rightMargin: win.railLeft ? win.margin : win.railSpace
            anchors.topMargin: Theme.m.space5 + Theme.m.space4
            anchors.bottomMargin: win.timelineHeight + Theme.m.space5

            Behavior on anchors.leftMargin {
                enabled: !Shell.v.reduceMotion
                NumberAnimation { duration: Theme.m.durNormal; easing.type: Easing.OutCubic }
            }
            Behavior on anchors.rightMargin {
                enabled: !Shell.v.reduceMotion
                NumberAnimation { duration: Theme.m.durNormal; easing.type: Easing.OutCubic }
            }
        }

        // The frame. viewAspect shapes the item: the canvas when the project
        // chose one, the CURRENT clip on "auto" - so a 9:16 clip in a 16:9
        // timeline stands vertical with the ambient backdrop at its sides
        // instead of the canvas' own baked black pillars. fillMode "cover"
        // then centre-crops the composited canvas to the item; with an
        // explicit canvas the two ratios match and nothing is cropped.
        Item {
            id: video
            readonly property real aspect: Playback.hasMedia ? Playback.viewAspect : 16 / 9
            readonly property real fit:
                Math.min(freeArea.width / aspect, freeArea.height)
            width: Math.max(160, fit * aspect)
            height: Math.max(90, fit)

            PreviewPlaceholder {
                anchors.fill: parent
                visible: !Playback.hasMedia && !win.idleActive
            }

            PreviewItem {
                anchors.fill: parent
                visible: Playback.hasMedia
                source: Playback
                fillMode: "cover"
            }
            x: freeArea.x + (freeArea.width - width) / 2
            y: freeArea.y + (freeArea.height - height) / 2

            Behavior on width {
                enabled: !Shell.v.reduceMotion
                NumberAnimation { duration: Theme.m.durNormal; easing.type: Easing.OutCubic }
            }
            Behavior on height {
                enabled: !Shell.v.reduceMotion
                NumberAnimation { duration: Theme.m.durNormal; easing.type: Easing.OutCubic }
            }
        }
    }

    // ── overlays. Direct children of overlayLayer so a glass surface can
    //    use its own x/y as the sample rectangle (see GlassSurface). ──
    Item {
        id: overlayLayer
        anchors.fill: parent

        // On-video sticker handles: first overlay child on purpose, so the
        // transport pill, the timeline and the panels stay clickable above
        // it. Laid exactly over the video item; only sticker boxes accept
        // the mouse, the rest of the surface lets events through.
        StickerHandles {
            x: video.x
            y: video.y
            width: video.width
            height: video.height
            canvasAspect: Playback.hasMedia ? Playback.aspect : 16 / 9
        }

        // Zones that reveal the playback controls. Each placement has its own;
        // only the active one is enabled, so an idle zone cannot keep the pill
        // on screen.
        Item {
            id: centreZone
            enabled: Shell.v.transportPosition === "center"
            x: video.x + video.width * 0.20
            y: video.y + video.height * 0.18
            width: video.width * 0.60
            height: video.height * 0.64
            HoverHandler { id: centreHover; enabled: centreZone.enabled }
        }

        Item {
            id: bottomZone
            enabled: Shell.v.transportPosition === "bottom"
            // The band immediately above the timeline: tall enough to be easy
            // to hit on the way down, not so tall that it triggers by accident
            // while working in the middle of the frame.
            height: 96
            y: win.height - win.timelineHeight - height
            // Spans the window, minus the rail. Deliberately NOT tied to the
            // panel: the strip must stay where the user learned it is.
            x: win.railLeft ? win.railSpace : 0
            width: win.width - win.railSpace
            HoverHandler { id: bottomHover; enabled: bottomZone.enabled }
        }

        TimelinePanel {
            id: timeline
            x: 0
            y: win.height - height
            width: win.width
            height: win.timelineHeight
            sceneSource: sceneLayer
            mediaName: Playback.hasMedia ? Playback.name : ""
            position: Playback.hasMedia ? Playback.positionSeconds : win.position
            // The ruler spans the project; it falls back to the previewed clip
            // so a single file still gets a sensible scale.
            duration: Project.isOpen && Project.timelineDuration > 0
                ? Project.timelineDuration
                : (Playback.hasMedia ? Playback.durationSeconds : win.duration)
            onMediaDropped: function (mediaId, seconds) {
                Actions.invoke("timeline.place_media",
                               { media_id: mediaId, at: seconds });
            }
            onSeekRequested: function (seconds) {
                if (Playback.hasMedia)
                    Actions.invoke("playback.seek_seconds", { seconds: seconds });
                else
                    win.position = seconds;
            }
            onPanelRequested: function (key) {
                // openSection toggles; asked for explicitly, it must OPEN.
                if (win.section !== key)
                    win.openSection(key);
            }

            Behavior on height {
                enabled: !Shell.v.reduceMotion
                NumberAnimation { duration: Theme.m.durNormal; easing.type: Easing.OutCubic }
            }
        }

        ToolRail {
            id: rail
            x: win.railLeft ? win.margin : win.width - width - win.margin
            // Centred in the room above the timeline, and never taller
            // than it: on a short window the rail scrolls instead.
            availableHeight: win.height - win.timelineHeight - win.margin * 2
            y: win.margin + (availableHeight - height) / 2
            sceneSource: sceneLayer
            section: win.section
            onSectionRequested: function (key) { win.openSection(key); }

            Behavior on x {
                enabled: !Shell.v.reduceMotion
                NumberAnimation { duration: Theme.m.durNormal; easing.type: Easing.OutCubic }
            }
        }

        TransportControls {
            id: transport
            // Centred on the TIMELINE, not on the video. Centring on the video
            // made the pill slide sideways every time the floating panel
            // expanded or collapsed - hovering the collapsed square was enough
            // to shove the playback controls across the screen.
            x: Shell.v.transportPosition === "bottom"
                ? (win.width - width) / 2
                : video.x + (video.width - width) / 2
            y: Shell.v.transportPosition === "bottom"
                ? win.height - win.timelineHeight - height - Theme.m.space3
                : video.y + (video.height - height) / 2
            sceneSource: sceneLayer
            playing: Playback.playing
            pointerInZone: Shell.v.transportPosition === "bottom"
                ? bottomHover.hovered : centreHover.hovered
            discoverable: !Playback.playing && Playback.position === 0

            onPlayPause: Actions.invoke("playback.toggle")
            onSeekStart: Actions.invoke("playback.go_to_start")
            onSeekEnd: Actions.invoke("playback.go_to_end")
            onStepBackward: Actions.invoke("playback.step", { frames: -1 })
            onStepForward: Actions.invoke("playback.step", { frames: 1 })

            Behavior on y {
                enabled: !Shell.v.reduceMotion
                NumberAnimation { duration: Theme.m.durNormal; easing.type: Easing.OutCubic }
            }
        }

        Readout {
            id: readout
            timecode: Playback.hasMedia ? Playback.timecode : win.timecode(0)
            fullscreen: win.isFullscreen
            sceneSource: sceneLayer
            x: {
                switch (Shell.v.readoutCorner) {
                case "top_right":
                    return win.railLeft
                        ? win.width - win.panelSpace - width
                        : win.width - win.railSpace - width;
                default:
                    return win.railLeft ? win.railSpace : win.margin;
                }
            }
            y: Shell.v.readoutCorner === "bottom_left"
                ? win.height - win.timelineHeight - height - Theme.m.space2
                : Theme.m.space2
        }

        // The pack confirmation card, above everything: a dropped
        // .ivepack (or "install from file") shows WHAT it carries
        // before anything lands on disk.
        PackInstallOverlay {
            anchors.fill: parent
            z: 50
        }
        // The one-time offer of the official packs (catalogue shipped
        // with the app, files on GitHub Releases).
        OfficialPacksOverlay {
            anchors.fill: parent
            z: 51
        }

        FloatingPanel {
            id: panel
            // The docked edge is pinned and only the width animates. Animating
            // x and width together made the panel look like it grew leftwards
            // and then slid right, because the two animations never agree
            // frame by frame.
            x: win.railLeft ? win.width - panel.expandedWidth - win.margin : win.margin
            y: win.margin
            sceneSource: sceneLayer
            // Down to just above the timeline: that is the room there is.
            availableHeight: win.height - win.timelineHeight - win.margin * 2
            // No section open means no panel: an empty shell would just be a
            // hole punched in the video.
            visible: win.section !== ""
            onCloseRequested: win.section = ""

        }
    }

    // ── drag and drop ─────────────────────────────────────────────
    // Files can be dropped anywhere in the window. Without a project there is
    // nowhere to put them, so the drop opens "new project" instead of failing
    // silently.
    DropArea {
        anchors.fill: parent
        keys: ["text/uri-list"]

        onEntered: function (drag) {
            drag.accepted = drag.hasUrls;
        }
        onDropped: function (drop) {
            if (!drop.hasUrls)
                return;
            var list = [];
            for (var i = 0; i < drop.urls.length; i++)
                list.push(String(drop.urls[i]));
            // A .ivepack is a content pack, not media: it needs no open
            // project, and it goes through the confirmation card.
            var packs = list.filter(function (u) {
                return u.toLowerCase().indexOf(".ivepack") ===
                       u.length - ".ivepack".length;
            });
            if (packs.length > 0) {
                Actions.invoke("pack.install", { path: packs[0] });
                drop.accept();
                return;
            }
            if (!Project.isOpen) {
                win.openSection("new");
                return;
            }
            Actions.invoke("project.import_media", { paths: list });
            drop.accept();
        }

        Rectangle {
            anchors.fill: parent
            visible: parent.containsDrag
            color: Theme.c.accent
            opacity: 0.12
            border.width: 2
            border.color: Theme.c.accent
        }
        Rectangle {
            anchors.centerIn: parent
            visible: parent.containsDrag
            width: dropLabel.implicitWidth + Theme.m.space5 * 2
            height: dropLabel.implicitHeight + Theme.m.space4 * 2
            radius: Theme.m.radiusLg
            color: Theme.c.bgPanel
            border.width: 1
            border.color: Theme.c.accent
            Text {
                id: dropLabel
                anchors.centerIn: parent
                text: Project.isOpen ? (Tr.s["project.drop_now"] || "")
                                     : (Tr.s["project.empty.hint"] || "")
                color: Theme.c.text
                font.pixelSize: Theme.m.fontSizeMd
            }
        }
    }

    // After a project is created the panel should show the project, not the
    // creation form the user has just finished with.
    Connections {
        target: Project
        function onProjectChanged() {
            if (Project.isOpen && win.section === "new")
                win.openSection("project");
        }
    }

    // ── keyboard ──────────────────────────────────────────────────
    Item {
        anchors.fill: parent
        // App-wide, not Keys: after any click on a button or panel the
        // focus item below loses activeFocus and a Keys-only Space went
        // dead. A focused text field still wins - editable items accept
        // the shortcut-override, so typing a space never toggles playback.
        // Focused switches/buttons keep Return/Enter for activation.
        Shortcut {
            sequences: ["Space"]
            context: Qt.ApplicationShortcut
            onActivated: {
                if (Playback.hasMedia)
                    Actions.invoke("playback.toggle");
                else
                    win.playing = !win.playing;
            }
        }

        // Delete removes the SELECTED timeline clip. Same app-wide rule as
        // Space, same escape hatch: an editable field consumes these keys
        // first, so deleting a character never deletes a clip.
        Shortcut {
            sequences: ["Delete", "Backspace"]
            context: Qt.ApplicationShortcut
            onActivated: timeline.deleteSelected()
        }

        // A focused text field keeps Ctrl+Z for its own typing undo: the
        // editor consumes the shortcut-override, so these never fire there.
        Shortcut {
            sequences: ["Ctrl+Z"]
            context: Qt.ApplicationShortcut
            onActivated: Actions.invoke("edit.undo")
        }
        Shortcut {
            // Both conventions: Windows habit and the shifted pair.
            sequences: ["Ctrl+Y", "Ctrl+Shift+Z"]
            context: Qt.ApplicationShortcut
            onActivated: Actions.invoke("edit.redo")
        }

        focus: true
        Keys.onPressed: function (event) {
            switch (event.key) {
            case Qt.Key_Space:
                if (Playback.hasMedia)
                    Actions.invoke("playback.toggle");
                else
                    win.playing = !win.playing;
                event.accepted = true;
                break;
            case Qt.Key_O:
                if (event.modifiers & Qt.ControlModifier) {
                    openDialog.open();
                    event.accepted = true;
                }
                break;
            case Qt.Key_N:
                if (event.modifiers & Qt.ControlModifier) {
                    win.openSection("new");
                    event.accepted = true;
                }
                break;
            case Qt.Key_S:
                if ((event.modifiers & Qt.ControlModifier) && Project.isOpen) {
                    Actions.invoke("project.save");
                    event.accepted = true;
                }
                break;
            case Qt.Key_F11:
                Actions.invoke("view.toggle_fullscreen");
                event.accepted = true;
                break;
            case Qt.Key_Escape:
                if (win.isFullscreen) {
                    Actions.invoke("view.toggle_fullscreen");
                    event.accepted = true;
                }
                break;
            case Qt.Key_Comma:
                win.openSection("settings");
                event.accepted = true;
                break;
            default:
                // Digits open the section that DECLARES that digit as its
                // shortcut: sections[0] is "new" (Ctrl+N), so indexing by
                // digit opened the section one to the left of every tooltip.
                if (event.key >= Qt.Key_1 && event.key <= Qt.Key_6) {
                    const digit = String(event.key - Qt.Key_0);
                    for (let i = 0; i < rail.sections.length; ++i) {
                        if (rail.sections[i].shortcut === digit) {
                            win.openSection(rail.sections[i].key);
                            event.accepted = true;
                            break;
                        }
                    }
                }
            }
        }
    }

    FileDialog {
        id: openDialog
        title: Tr.s["media.open"] || "Open media"
        nameFilters: [
            (Tr.s["media.filter.video"] || "Video files")
                + " (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.mts *.m2ts *.mpg *.mpeg *.wmv)",
            (Tr.s["media.filter.all"] || "All files") + " (*)"
        ]
        onAccepted: Actions.invoke("media.open", { path: String(selectedFile) })
    }

    Connections {
        target: Actions
        function onFailed(actionId, message) {
            console.warn("Action failed:", actionId, "-", message);
        }
    }
}
