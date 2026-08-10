// A titled group of related options inside the floating panel.
import QtQuick
import QtQuick.Layouts
import IVE

Rectangle {
    id: root

    property string title: ""
    default property alias content: column.data

    Layout.fillWidth: true
    implicitHeight: column.implicitHeight + Theme.m.space3 * 2
                    + (title !== "" ? header.implicitHeight + Theme.m.space3 : 0)
    radius: Theme.m.radiusLg
    // No fill. A tinted card inside a glass panel makes the areas WITH a card
    // a different shade from the areas without one, so the panel reads as two
    // materials glued together - measured as #313134 against #252528, which is
    // exactly the "the bottom has no blur" report. Sections are marked with a
    // hairline instead.
    color: "transparent"
    border.width: 1
    border.color: Qt.alpha(Theme.c.glassOn, 0.13)

    Text {
        id: header
        visible: root.title !== ""
        text: root.title
        color: Theme.c.text
        font.pixelSize: Theme.m.fontSizeMd
        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
            margins: Theme.m.space3
        }
        wrapMode: Text.WordWrap
    }

    ColumnLayout {
        id: column
        anchors {
            top: root.title !== "" ? header.bottom : parent.top
            left: parent.left
            right: parent.right
            topMargin: root.title !== "" ? Theme.m.space3 : Theme.m.space3
            leftMargin: Theme.m.space3
            rightMargin: Theme.m.space3
        }
        spacing: Theme.m.space2
    }
}
