// One setting: its label, and the control under it.
//
// Stacked rather than side by side. In a 392 px panel a label and a
// four-option segmented control cannot share a line without one of them being
// cut, and a truncated label ("Comandi ripro...") is worse than a taller row.
import QtQuick
import QtQuick.Layouts
import IVE

ColumnLayout {
    id: root

    property string label: ""
    property string hint: ""
    default property alias control: holder.data

    Layout.fillWidth: true
    spacing: 3

    Text {
        text: root.label
        color: Theme.c.textMuted
        font.pixelSize: Theme.m.fontSizeSm + 1
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
    }

    Text {
        visible: root.hint !== ""
        text: root.hint
        color: Theme.c.textDisabled
        font.pixelSize: Theme.m.fontSizeXs
        Layout.fillWidth: true
        Layout.bottomMargin: 2
        wrapMode: Text.WordWrap
    }

    Item {
        id: holder
        Layout.fillWidth: true
        Layout.preferredHeight: childrenRect.height
        // Most controls take the full width they now have to themselves - a
        // slider or a segmented control is meaningless at its implicit size.
        //
        // A switch is not one of them. It is a pill with an intrinsic 40x22,
        // and anchoring it on both sides stretched it across the whole panel.
        // So a control can opt out by declaring `fillsRow: false`; anything
        // that does not declare the property keeps the old behaviour.
        onChildrenChanged: {
            for (var i = 0; i < children.length; i++) {
                var c = children[i];
                c.anchors.left = holder.left;
                if (c.fillsRow === undefined || c.fillsRow)
                    c.anchors.right = holder.right;
            }
        }
    }
}
