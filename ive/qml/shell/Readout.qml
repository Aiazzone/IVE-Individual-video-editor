// Timecode and volume, sitting straight on the video with no plate.
//
// These are values you glance at, not controls you aim for. A plate would turn
// them into permanent chrome stealing space from the frame; a drop shadow
// costs nothing and keeps them legible on any content.
// Always a little visible (opacity 0.55), full on hover.
// See docs/UI_SHELL.md section 8-bis.
import QtQuick
import QtQuick.Layouts
import components
import IVE

Item {
    id: root

    property string timecode: "00:00:00:00"
    /*! Current window state, so the icon can show the way out, not the way in. */
    property bool fullscreen: false
    property real volume: Shell.v.volume
    property bool muted: Shell.v.muted

    implicitWidth: row.implicitWidth + Theme.m.space3 * 2
    implicitHeight: row.implicitHeight + Theme.m.space2 * 2

    opacity: hover.hovered || volumeSlider.activeFocus
        ? 1.0 : Theme.m.readoutIdleOpacity
    Behavior on opacity {
        enabled: !Shell.v.reduceMotion
        NumberAnimation { duration: Theme.m.durNormal }
    }

    HoverHandler { id: hover }

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: Theme.m.space3

        // Leftmost on purpose: quitting is an edge action, and putting it
        // past the fullscreen toggle would put it under a moving target.
        IconButton {
            size: 26
            iconSize: 16
            onVideo: true
            tipSide: "right"
            icon: Icons.power
            label: Tr.s["app.quit"] || ""
            onTriggered: Actions.invoke("app.quit")
        }

        // Sits before the timecode: leaving fullscreen is otherwise only
        // discoverable by knowing about F11.
        IconButton {
            size: 26
            iconSize: 17
            onVideo: true
            tipSide: "right"
            icon: root.fullscreen ? Icons.fullscreenExit : Icons.fullscreen
            label: Tr.s["view.fullscreen"] || ""
            shortcut: "F11"
            onTriggered: Actions.invoke("view.toggle_fullscreen")
        }

        Text {
            text: root.timecode
            color: "#FFFFFF"
            font.pixelSize: Theme.m.fontSizeLg
            font.family: "monospace"
            // Tabular figures: with a proportional font the digits jitter and
            // become unreadable during playback.
            font.features: { "tnum": 1 }
            style: Text.Raised
            styleColor: "#000000"
        }

        RowLayout {
            spacing: Theme.m.space2

            Glyph {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                path: root.muted || root.volume <= 0 ? Icons.volumeOff : Icons.volume
                color: "#FFFFFF"
                shadow: true
            }

            // Hidden at rest, expands on hover: a readout, not a control bar.
            AppSlider {
                id: volumeSlider
                Layout.preferredWidth: hover.hovered || activeFocus ? 74 : 0
                Layout.preferredHeight: 18
                opacity: hover.hovered || activeFocus ? 1 : 0
                visible: opacity > 0
                label: Tr.s["transport.volume"] || ""
                from: 0
                to: 1
                stepSize: 0.01
                value: root.volume
                onMoved: function (v) {
                    Actions.invoke("settings.set",
                                   { key: "playback.volume", value: String(v) });
                }
                Behavior on Layout.preferredWidth {
                    enabled: !Shell.v.reduceMotion
                    NumberAnimation { duration: Theme.m.durNormal; easing.type: Easing.OutCubic }
                }
                Behavior on opacity {
                    enabled: !Shell.v.reduceMotion
                    NumberAnimation { duration: Theme.m.durNormal }
                }
            }
        }
    }
}
