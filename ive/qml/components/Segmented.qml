// Segmented choice: a few mutually exclusive options side by side.
//
// `model` is a list of { value, text } objects. The text must already be
// translated by the caller, so this component stays free of string keys.
import QtQuick
import QtQuick.Layouts
import IVE

Item {
    id: root

    property var model: []
    property string value: ""
    signal picked(string value)

    // Every segment is the same width, and that width fits the longest
    // label. Equal-but-too-narrow just moves the problem from "ragged" to
    // "truncated", which is worse: a truncated label cannot be read at all.
    property real cell: 0
    implicitWidth: Math.max(cell * Math.max(1, model.length) + 4, 120)
    implicitHeight: Theme.m.controlHeightSm + 6

    Rectangle {
        anchors.fill: parent
        radius: Theme.m.radiusMd
        color: Qt.alpha(Theme.c.glassOn, 0.07)
    }

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: 2
        spacing: 2

        Repeater {
            model: root.model
            delegate: Item {
                required property var modelData
                // Every segment takes the same width: labels of different
                // lengths made the tabs look misaligned even though they were
                // evenly spaced.
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: root.cell
                implicitWidth: root.cell
                Component.onCompleted:
                    root.cell = Math.max(root.cell, text.implicitWidth + 22)
                activeFocusOnTab: true

                readonly property bool selected: modelData.value === root.value

                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData.text
                Accessible.checked: selected

                Rectangle {
                    anchors.fill: parent
                    radius: Theme.m.radiusSm
                    color: parent.selected ? Theme.c.accent
                         : hover.hovered ? Theme.c.bgHover : "transparent"
                    Behavior on color {
                        enabled: !Shell.v.reduceMotion
                        ColorAnimation { duration: Theme.m.durFast }
                    }
                }

                Text {
                    id: text
                    anchors.fill: parent
                    anchors.leftMargin: 4
                    anchors.rightMargin: 4
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    text: parent.modelData.text
                    elide: Text.ElideRight
                    color: parent.selected ? Theme.c.onAccent : Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeSm
                }

                Rectangle {
                    anchors.fill: parent
                    radius: Theme.m.radiusSm
                    color: "transparent"
                    border.width: 2
                    border.color: Theme.c.accent
                    visible: parent.activeFocus
                }

                HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: root.picked(modelData.value) }
                Keys.onPressed: function (event) {
                    if (event.key === Qt.Key_Space || event.key === Qt.Key_Return) {
                        root.picked(modelData.value);
                        event.accepted = true;
                    }
                }
            }
        }
    }
}
