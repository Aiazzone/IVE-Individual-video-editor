// On/off switch for persistent options.
//
// A sliding switch reads as a state; a checkable button reads as an action.
// Use this for anything the user turns on and leaves on.
import QtQuick
import IVE

Item {
    id: root

    property bool checked: false
    property string label: ""
    /*! A switch has an intrinsic size; SettingRow must not stretch it. */
    property bool fillsRow: false
    signal toggled(bool value)

    implicitWidth: 40
    implicitHeight: 22
    activeFocusOnTab: true

    Accessible.role: Accessible.CheckBox
    Accessible.name: root.label
    Accessible.checked: root.checked

    Rectangle {
        id: track
        anchors.fill: parent
        radius: height / 2
        color: root.checked ? Theme.c.accent : Theme.c.borderStrong
        Behavior on color {
            enabled: !Shell.v.reduceMotion
            ColorAnimation { duration: Theme.m.durNormal }
        }
    }

    Rectangle {
        id: knob
        width: parent.height - 4
        height: width
        radius: width / 2
        y: 2
        x: root.checked ? parent.width - width - 2 : 2
        color: "#FFFFFF"
        Behavior on x {
            enabled: !Shell.v.reduceMotion
            NumberAnimation { duration: Theme.m.durNormal; easing.type: Easing.OutCubic }
        }
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: -3
        radius: height / 2
        color: "transparent"
        border.width: 2
        border.color: Theme.c.accent
        visible: root.activeFocus
    }

    HoverHandler { cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: root.toggled(!root.checked) }
    Keys.onPressed: function (event) {
        if (event.key === Qt.Key_Space || event.key === Qt.Key_Return) {
            root.toggled(!root.checked);
            event.accepted = true;
        }
    }
}
