// Icon-only button with a mandatory tooltip.
//
// An icon-only interface without tooltips is guessable only by whoever wrote
// it, so `label` is required and the tooltip also shows the shortcut.
import QtQuick
import IVE

Item {
    id: root

    property string icon: ""
    property string label: ""             // already translated
    property string shortcut: ""
    property bool checked: false
    // `enabled` is inherited from Item - do not redeclare it, that shadows the
    // base member and Qt warns about it.
    /*! Tooltip side; follows the rail so it always opens inwards. */
    property string tipSide: "right"
    property real size: Theme.m.toolRailButton
    property real iconSize: Theme.m.toolRailIcon
    /*! Set on buttons that sit on glass or straight on the video: the icon
        follows the theme's on-glass colour and gains a drop shadow. */
    property bool onVideo: false
    readonly property color _onGlass: Theme.c.glassOn

    signal triggered()

    implicitWidth: size
    implicitHeight: size
    activeFocusOnTab: enabled
    opacity: enabled ? 1.0 : 0.45

    Accessible.role: Accessible.Button
    Accessible.name: root.label
    Accessible.description: root.shortcut

    Rectangle {
        anchors.fill: parent
        radius: Math.min(width, height) * 0.28
        color: root.checked ? Theme.c.accent
             : hover.hovered ? Qt.alpha(root.onVideo ? root._onGlass : Theme.c.text, 0.14)
             : "transparent"
        Behavior on color {
            enabled: !Shell.v.reduceMotion
            ColorAnimation { duration: Theme.m.durFast }
        }
    }

    Glyph {
        anchors.centerIn: parent
        width: root.iconSize
        height: root.iconSize
        path: root.icon
        color: root.checked ? Theme.c.onAccent
             : root.onVideo ? root._onGlass : Theme.c.text
        shadow: root.onVideo && !root.checked
    }

    Rectangle {   // keyboard focus ring, visible on glass too
        anchors.fill: parent
        anchors.margins: -2
        radius: Math.min(width, height) * 0.3
        color: "transparent"
        border.width: 2
        border.color: Theme.c.accent
        visible: root.activeFocus
    }

    HoverHandler { id: hover; enabled: root.enabled; cursorShape: Qt.PointingHandCursor }
    TapHandler {
        enabled: root.enabled
        onTapped: root.triggered()
    }
    Keys.onPressed: function (event) {
        if (event.key === Qt.Key_Space || event.key === Qt.Key_Return) {
            root.triggered();
            event.accepted = true;
        }
    }

    // ── tooltip ───────────────────────────────────────────────────
    Loader {
        active: hover.hovered || root.activeFocus
        asynchronous: true
        sourceComponent: Rectangle {
            id: tip
            parent: root
            x: root.tipSide === "right" ? root.width + 10 : -width - 10
            y: (root.height - height) / 2
            width: row.implicitWidth + 18
            height: row.implicitHeight + 12
            radius: Theme.m.radiusMd
            color: Theme.isDark ? "#000000" : "#16161A"
            border.width: 1
            border.color: Theme.c.borderStrong
            opacity: 0
            z: 100

            Row {
                id: row
                anchors.centerIn: parent
                spacing: 8
                Text {
                    text: root.label
                    color: "#EDEDF2"
                    font.pixelSize: Theme.m.fontSizeSm + 1
                }
                Rectangle {
                    visible: root.shortcut !== ""
                    width: kbd.implicitWidth + 8
                    height: kbd.implicitHeight + 2
                    anchors.verticalCenter: parent.verticalCenter
                    radius: 3
                    color: "transparent"
                    border.width: 1
                    border.color: "#3A3A46"
                    Text {
                        id: kbd
                        anchors.centerIn: parent
                        text: root.shortcut
                        color: "#8A8A96"
                        font.pixelSize: Theme.m.fontSizeXs
                        font.family: "monospace"
                    }
                }
            }

            // 400 ms delay: instant tooltips are noise while moving the mouse.
            Timer {
                running: true
                interval: 400
                onTriggered: tip.opacity = 1
            }
            Behavior on opacity {
                enabled: !Shell.v.reduceMotion
                NumberAnimation { duration: Theme.m.durFast }
            }
        }
    }
}
