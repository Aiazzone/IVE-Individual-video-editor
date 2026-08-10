// Stickers: not built yet, and honest about it.
//
// The rail button exists so the layout settles now; when the feature lands
// (animated overlays as shareable packs, like the colour effects) this
// placeholder is replaced. An empty panel would read as a bug.
import QtQuick
import QtQuick.Layouts
import components
import IVE

Item {
    id: root

    implicitHeight: column.implicitHeight + Theme.m.space3 * 2

    ColumnLayout {
        id: column
        anchors { left: parent.left; right: parent.right; top: parent.top
                  margins: Theme.m.space3 }
        spacing: Theme.m.space3

        CardGroup {
            Glyph {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: Theme.m.space3
                Layout.preferredWidth: 34
                Layout.preferredHeight: 34
                path: Icons.sticker
                color: Theme.c.textDisabled
            }
            Text {
                Layout.fillWidth: true
                Layout.bottomMargin: Theme.m.space3
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: Tr.s["stickers.coming"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeSm
                lineHeight: 1.35
            }
        }
    }
}
