// The command palette: every no-argument Action, one keystroke away.
//
// Ctrl+K opens it; typing filters the registry's catalogue by title, id
// and category; Up/Down move, Return runs, Escape leaves. Only actions
// invocable WITHOUT parameters are listed - one that needs a clip id or
// a path can only run from a place that has them. The palette is the
// registry made visible: an action registered anywhere in the code
// appears here with no UI work at all (CLAUDE.md 4.4).
import QtQuick
import QtQuick.Layouts
import components
import IVE

Item {
    id: root
    anchors.fill: parent
    visible: false
    z: 300

    function open() {
        visible = true;
        queryField.text = "";
        list.currentIndex = 0;
        queryField.forceActiveFocus();
    }
    function close() {
        visible = false;
        queryField.focus = false;
    }

    readonly property var entries: {
        var query = queryField.text.trim().toLowerCase();
        var all = Actions.catalogue.filter(function (a) {
            return a.invocable === true;
        }).map(function (a) {
            return {
                id: a.id,
                title: Tr.s[a.titleKey] || a.id,
                category: a.category,
                shortcut: a.shortcut
            };
        });
        if (query === "")
            return all;
        return all.filter(function (a) {
            return (a.title + " " + a.id + " " + a.category)
                .toLowerCase().indexOf(query) >= 0;
        });
    }

    function run() {
        var entry = root.entries[list.currentIndex];
        if (entry === undefined)
            return;
        root.close();
        Actions.invoke(entry.id);
    }

    // A tap outside the card leaves.
    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.35)
        TapHandler { onTapped: root.close() }
    }

    Rectangle {
        objectName: "command_palette"
        width: Math.min(560, parent.width - Theme.m.space5 * 2)
        height: Math.min(searchBox.height + list.contentHeight
                         + Theme.m.space2 * 3, parent.height * 0.6)
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height * 0.14
        radius: Theme.m.radiusLg
        color: Theme.c.bgElevated
        border.width: 1
        border.color: Theme.c.borderStrong
        TapHandler { }   // eats taps so they never reach the scrim

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.m.space2
            spacing: Theme.m.space2

            Rectangle {
                id: searchBox
                Layout.fillWidth: true
                height: Theme.m.controlHeight
                radius: Theme.m.radiusMd
                color: Qt.alpha(Theme.c.glassOn, 0.07)
                border.width: 1
                border.color: queryField.activeFocus ? Theme.c.accent
                                                     : Theme.c.border
                TextInput {
                    id: queryField
                    objectName: "palette_query"
                    anchors.fill: parent
                    anchors.leftMargin: Theme.m.space2
                    anchors.rightMargin: Theme.m.space2
                    verticalAlignment: TextInput.AlignVCenter
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeSm + 1
                    selectByMouse: true
                    selectionColor: Theme.c.accent
                    clip: true
                    onTextChanged: list.currentIndex = 0
                    Keys.onPressed: function (event) {
                        switch (event.key) {
                        case Qt.Key_Escape:
                            root.close();
                            event.accepted = true;
                            break;
                        case Qt.Key_Down:
                            list.currentIndex = Math.min(
                                list.currentIndex + 1, list.count - 1);
                            event.accepted = true;
                            break;
                        case Qt.Key_Up:
                            list.currentIndex = Math.max(
                                list.currentIndex - 1, 0);
                            event.accepted = true;
                            break;
                        case Qt.Key_Return:
                        case Qt.Key_Enter:
                            root.run();
                            event.accepted = true;
                            break;
                        }
                    }
                }
                Text {
                    anchors.fill: queryField
                    verticalAlignment: Text.AlignVCenter
                    visible: queryField.text === ""
                    text: Tr.s["palette.hint"] || ""
                    color: Theme.c.textDisabled
                    font.pixelSize: Theme.m.fontSizeSm + 1
                    elide: Text.ElideRight
                }
            }

            ListView {
                id: list
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: root.entries
                keyNavigationWraps: false
                highlightMoveDuration: 60
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    objectName: "palette_row_" + modelData.id
                    width: list.width
                    height: 34
                    radius: Theme.m.radiusMd
                    color: index === list.currentIndex
                        ? Qt.alpha(Theme.c.accent, 0.22)
                        : rowHover.hovered ? Theme.c.bgHover : "transparent"
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.m.space2
                        anchors.rightMargin: Theme.m.space2
                        spacing: Theme.m.space2
                        Text {
                            Layout.fillWidth: true
                            text: parent.parent.modelData.title
                            color: Theme.c.text
                            font.pixelSize: Theme.m.fontSizeSm
                            elide: Text.ElideRight
                        }
                        Text {
                            text: parent.parent.modelData.category
                            color: Theme.c.textDisabled
                            font.pixelSize: Theme.m.fontSizeXs
                        }
                        Text {
                            visible: parent.parent.modelData.shortcut !== ""
                            text: parent.parent.modelData.shortcut
                            color: Theme.c.textMuted
                            font.pixelSize: Theme.m.fontSizeXs
                            font.family: "monospace"
                        }
                    }
                    HoverHandler { id: rowHover
                                   cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: {
                            list.currentIndex = index;
                            root.run();
                        }
                    }
                }
                Text {
                    visible: list.count === 0
                    anchors.centerIn: parent
                    text: Tr.s["palette.empty"] || ""
                    color: Theme.c.textDisabled
                    font.pixelSize: Theme.m.fontSizeSm
                }
            }
        }
    }
}
