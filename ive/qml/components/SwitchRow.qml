// An on/off option on a single line: the switch FIRST, its label beside it.
//
// The stacked SettingRow shape exists for wide controls (sliders, segmented)
// that need the full panel width under their label. A switch does not: state
// and label share a line comfortably, and leading with the control lets the
// eye find the state before reading what it governs. The whole line is
// tappable - a 40 px pill alone is a small target.
import QtQuick
import QtQuick.Layouts
import IVE

RowLayout {
    id: root

    property bool checked: false
    property string label: ""
    signal toggled(bool value)

    Layout.fillWidth: true
    spacing: Theme.m.space2

    AppSwitch {
        checked: root.checked
        label: root.label
        onToggled: function (v) { root.toggled(v); }
    }

    Text {
        Layout.fillWidth: true
        text: root.label
        color: Theme.c.textMuted
        font.pixelSize: Theme.m.fontSizeSm + 1
        wrapMode: Text.WordWrap

        HoverHandler { cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: root.toggled(!root.checked) }
    }
}
