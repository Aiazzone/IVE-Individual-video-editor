// "New project": a name, a folder, and nothing else.
//
// The project is written to disk the moment it is created, so the user finds
// out immediately if the folder is unwritable - not after an hour of importing.
import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs
import components
import IVE

Item {
    id: root

    implicitHeight: column.implicitHeight + Theme.m.space3 * 2
    readonly property bool interacting: false

    property string chosenFolder: Project.defaultFolder
    // "+" means "start working": creating and reopening are both that, so
    // they belong together rather than behind two different icons.
    property string tab: "create"

    FileDialog {
        id: openDialog
        title: Tr.s["project.open"] || "Open project"
        nameFilters: [(Tr.s["project.file"] || "IVE project") + " (*.iveproj)",
                      (Tr.s["media.filter.all"] || "All files") + " (*)"]
        onAccepted: Actions.invoke("project.open", { path: String(selectedFile) })
    }

    FolderDialog {
        id: folderDialog
        title: Tr.s["project.folder"] || "Save folder"
        // Python does the URL -> path conversion: the naive replace() here
        // kept percent-escapes (spaces, accents) and broke POSIX paths.
        onAccepted: root.chosenFolder = Project.localPath(String(selectedFolder))
    }

    ColumnLayout {
        id: column
        anchors { left: parent.left; right: parent.right; top: parent.top
                  margins: Theme.m.space3 }
        spacing: Theme.m.space3

        Segmented {
            Layout.fillWidth: true
            value: root.tab
            model: [
                { value: "create", text: Tr.s["project.tab.create"] || "" },
                { value: "open",   text: Tr.s["project.tab.open"] || "" }
            ]
            onPicked: function (v) { root.tab = v; }
        }

        // ── open an existing project ──────────────────────────────
        CardGroup {
            visible: root.tab === "open"
            title: Tr.s["project.open"] || ""

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.m.controlHeight
                radius: Theme.m.radiusMd
                color: browseHover.hovered ? Theme.c.accentHover : Theme.c.accent
                RowLayout {
                    anchors.centerIn: parent
                    spacing: Theme.m.space2
                    Glyph {
                        width: 15; height: 15
                        path: Icons.folderOpen
                        color: Theme.c.onAccent
                    }
                    Text {
                        text: Tr.s["project.browse"] || ""
                        color: Theme.c.onAccent
                        font.pixelSize: Theme.m.fontSizeSm + 1
                        font.bold: true
                    }
                }
                HoverHandler { id: browseHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: openDialog.open() }
            }

            Text {
                Layout.fillWidth: true
                Layout.topMargin: Theme.m.space2
                wrapMode: Text.WordWrap
                text: Tr.s["project.open_hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            // Recently used projects, so the common case needs no dialog.
            Repeater {
                model: Project.recentProjects
                delegate: Item {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.m.radiusMd
                        color: Qt.alpha(Theme.c.glassOn, recentHover.hovered ? 0.12 : 0.0)
                    }
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.m.space3
                        anchors.rightMargin: Theme.m.space3
                        spacing: 0
                        Text {
                            Layout.fillWidth: true
                            text: modelData.name
                            color: Theme.c.text
                            font.pixelSize: Theme.m.fontSizeSm + 1
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.folder
                            color: Theme.c.textDisabled
                            font.pixelSize: Theme.m.fontSizeXs
                            elide: Text.ElideLeft
                        }
                    }
                    HoverHandler { id: recentHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: Actions.invoke("project.open", { path: modelData.path })
                    }
                }
            }

            Text {
                visible: Project.recentProjects.length === 0
                Layout.fillWidth: true
                text: Tr.s["project.no_recent"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
            }
        }

        // ── create a new one ──────────────────────────────────────
        CardGroup {
            visible: root.tab === "create"
            title: Tr.s["project.new"] || ""

            Text {
                Layout.fillWidth: true
                text: Tr.s["project.name"] || ""
                color: Theme.c.textMuted
                font.pixelSize: Theme.m.fontSizeSm + 1
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.m.controlHeight
                radius: Theme.m.radiusMd
                color: Qt.alpha(Theme.c.glassOn, 0.07)
                border.width: 1
                border.color: nameField.activeFocus ? Theme.c.accent : Theme.c.border

                TextInput {
                    id: nameField
                    anchors.fill: parent
                    anchors.leftMargin: Theme.m.space2
                    anchors.rightMargin: Theme.m.space2
                    verticalAlignment: TextInput.AlignVCenter
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeSm + 1
                    selectByMouse: true
                    selectionColor: Theme.c.accent
                    text: Tr.s["project.name_placeholder"] || "My project"
                    onAccepted: createButton.create()
                    Component.onCompleted: { selectAll(); forceActiveFocus(); }
                }
            }

            Text {
                Layout.fillWidth: true
                Layout.topMargin: Theme.m.space2
                text: Tr.s["project.folder"] || ""
                color: Theme.c.textMuted
                font.pixelSize: Theme.m.fontSizeSm + 1
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.m.space2

                Text {
                    Layout.fillWidth: true
                    text: root.chosenFolder
                    color: Theme.c.textDisabled
                    font.pixelSize: Theme.m.fontSizeXs
                    elide: Text.ElideLeft
                    maximumLineCount: 1
                }
                Rectangle {
                    Layout.preferredWidth: chooseText.implicitWidth + Theme.m.space3 * 2
                    Layout.preferredHeight: Theme.m.controlHeightSm + 4
                    radius: Theme.m.radiusMd
                    color: chooseHover.hovered ? Theme.c.bgHover : Theme.c.bgElevated
                    border.width: 1
                    border.color: Theme.c.border
                    Text {
                        id: chooseText
                        anchors.centerIn: parent
                        text: Tr.s["project.choose_folder"] || ""
                        color: Theme.c.text
                        font.pixelSize: Theme.m.fontSizeSm
                    }
                    HoverHandler { id: chooseHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: folderDialog.open() }
                }
            }

            Rectangle {
                id: createButton
                Layout.fillWidth: true
                Layout.topMargin: Theme.m.space3
                Layout.preferredHeight: Theme.m.controlHeight
                radius: Theme.m.radiusMd
                color: createHover.hovered ? Theme.c.accentHover : Theme.c.accent

                function create() {
                    Actions.invoke("project.new",
                                   { name: nameField.text, folder: root.chosenFolder });
                }

                Text {
                    anchors.centerIn: parent
                    text: Tr.s["project.create"] || ""
                    color: Theme.c.onAccent
                    font.pixelSize: Theme.m.fontSizeSm + 1
                    font.bold: true
                }
                HoverHandler { id: createHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: createButton.create() }
            }

            Text {
                Layout.fillWidth: true
                Layout.topMargin: Theme.m.space2
                wrapMode: Text.WordWrap
                text: Tr.s["project.drop_hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }
        }
    }
}
