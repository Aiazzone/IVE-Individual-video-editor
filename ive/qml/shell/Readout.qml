// Timecode, session controls and volume, on a glass PILL.
//
// It used to sit straight on the video with white glyphs, but the row has
// grown real controls (quit, fullscreen, undo, redo) and bare icons over
// moving footage are hard to pick out. The pill is the same glass the
// tool rail uses, at the icon scrim - so its content follows the THEME,
// while the video underneath does not.
// Still a readout at heart: a little transparent at rest, full on hover.
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
    /*! Item sampled for the blur; see GlassSurface. */
    property Item sceneSource: null
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

    GlassSurface {
        anchors.fill: parent
        sceneSource: root.sceneSource
        originX: root.x
        originY: root.y
        radius: height / 2
        scrim: Theme.m.scrimIcons
    }

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: Theme.m.space3

        // Leftmost on purpose: quitting is an edge action, and putting it
        // past the fullscreen toggle would put it under a moving target.
        IconButton {
            size: 26
            iconSize: 16
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
            tipSide: "right"
            icon: root.fullscreen ? Icons.fullscreenExit : Icons.fullscreen
            label: Tr.s["view.fullscreen"] || ""
            shortcut: "F11"
            onTriggered: Actions.invoke("view.toggle_fullscreen")
        }

        // Undo and redo live with the other global controls. Dimmed when
        // there is nothing to revert; the tooltip names the step, so the
        // user knows WHAT Ctrl+Z is about to take back.
        IconButton {
            objectName: "undoButton"
            size: 26
            iconSize: 16
            tipSide: "right"
            enabled: History.canUndo
            icon: Icons.undo
            label: (Tr.s["timeline.undo"] || "")
                   + (History.canUndo && Tr.s[History.undoLabel]
                      ? ": " + Tr.s[History.undoLabel] : "")
            shortcut: "Ctrl+Z"
            onTriggered: Actions.invoke("edit.undo")
        }

        IconButton {
            objectName: "redoButton"
            size: 26
            iconSize: 16
            tipSide: "right"
            enabled: History.canRedo
            icon: Icons.redo
            label: (Tr.s["timeline.redo"] || "")
                   + (History.canRedo && Tr.s[History.redoLabel]
                      ? ": " + Tr.s[History.redoLabel] : "")
            shortcut: "Ctrl+Y"
            onTriggered: Actions.invoke("edit.redo")
        }

        Text {
            text: root.timecode
            color: Theme.c.text
            font.pixelSize: Theme.m.fontSizeLg
            font.family: "monospace"
            // Tabular figures: with a proportional font the digits jitter and
            // become unreadable during playback.
            font.features: { "tnum": 1 }
        }

        RowLayout {
            spacing: Theme.m.space2

            Glyph {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                path: root.muted || root.volume <= 0 ? Icons.volumeOff : Icons.volume
                color: Theme.c.text
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
