// Playback controls: a glass pill, hidden until the pointer comes near.
//
// Two placements, both hover-revealed (docs/UI_SHELL.md section 8):
//   bottom (default) - just above the timeline toolbar, revealed by a strip
//                      spanning that band. The hand is already travelling
//                      between timeline and preview, so it costs no detour.
//   center           - middle of the frame, revealed by a zone around it.
//
// Nothing covers the video when the controls are not wanted.
//
// Actions only: no timecode, no volume. Those live in Readout, so this pill
// stays small. See docs/UI_SHELL.md section 8.
import QtQuick
import QtQuick.Layouts
import components
import IVE

Item {
    id: root

    property bool playing: false
    /*! True when the pointer is inside the centre zone of the video. */
    property bool pointerInZone: false
    /*! Kept visible while the project is untouched, or nobody finds Play. */
    property bool discoverable: true

    signal playPause()
    signal seekStart()
    signal seekEnd()
    signal stepBackward()
    signal stepForward()

    readonly property bool bottomMode: Shell.v.transportPosition === "bottom"

    // Hidden until the pointer reaches the strip that belongs to it. In bottom
    // mode there is no "always visible while paused" exception: the strip sits
    // right above the timeline, which is where the hand already goes.
    // Space always works, visible or not.
    readonly property bool shown:
        pointerInZone || hover.hovered || (discoverable && !bottomMode)

    implicitWidth: row.implicitWidth + Theme.m.space2 * 2
    implicitHeight: row.implicitHeight + Theme.m.space2 * 2

    opacity: shown ? 1 : 0
    visible: opacity > 0
    scale: shown ? 1.0 : 0.94
    Behavior on opacity {
        enabled: !Shell.v.reduceMotion
        NumberAnimation { duration: Theme.m.durNormal }
    }
    Behavior on scale {
        enabled: !Shell.v.reduceMotion
        NumberAnimation { duration: Theme.m.durNormal; easing.type: Easing.OutCubic }
    }

    HoverHandler { id: hover }

    /*! Item sampled for the blur; see GlassSurface. */
    property alias sceneSource: glass.sceneSource

    GlassSurface {
        id: glass
        anchors.fill: parent
        originX: root.x
        originY: root.y
        radius: height / 2
        scrim: Theme.m.scrimIcons
    }

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: Theme.m.space1

        IconButton {
            size: 34; iconSize: 17; onVideo: true
            icon: Icons.skipStart
            label: Tr.s["transport.start"] || ""
            onTriggered: root.seekStart()
        }
        IconButton {
            size: 34; iconSize: 17; onVideo: true
            icon: Icons.stepBack
            label: Tr.s["transport.prev_frame"] || ""
            onTriggered: root.stepBackward()
        }
        IconButton {
            size: 44; iconSize: 22; onVideo: true
            icon: root.playing ? Icons.pause : Icons.play
            label: root.playing ? (Tr.s["transport.pause"] || "")
                                : (Tr.s["transport.play"] || "")
            shortcut: "Space"
            onTriggered: root.playPause()
        }
        IconButton {
            size: 34; iconSize: 17; onVideo: true
            icon: Icons.stepForward
            label: Tr.s["transport.next_frame"] || ""
            onTriggered: root.stepForward()
        }
        IconButton {
            size: 34; iconSize: 17; onVideo: true
            icon: Icons.skipEnd
            label: Tr.s["transport.end"] || ""
            onTriggered: root.seekEnd()
        }
    }
}
