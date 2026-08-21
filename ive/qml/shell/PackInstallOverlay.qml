// The pack confirmation card: see WHAT you are installing before it
// lands on disk.
//
// Both install paths meet here - a .ivepack dropped on the window and
// "install from file" in the Packs panel: Packs.request_install() puts
// the previewed manifest in Packs.pending, this overlay shows it, and
// only Installa unpacks. The card SHOWS author and contents because it
// is useful to know, not to make anyone approve anything: a pack is
// data end to end, installing it is safe by construction.
import QtQuick
import QtQuick.Layouts
import components
import IVE

Item {
    id: root

    readonly property var pack: Packs.pending
    visible: pack.name !== undefined
    z: 1000

    // Dim the shell; a click outside the card is a cancel.
    Rectangle {
        anchors.fill: parent
        color: "#73000000"
        MouseArea {
            anchors.fill: parent
            onClicked: Packs.cancel_install()
        }
    }

    Rectangle {
        id: card
        objectName: "pack_install_card"
        anchors.centerIn: parent
        width: 440
        height: cardColumn.implicitHeight + Theme.m.space4 * 2
        radius: Theme.m.floatPanelRadius
        color: Theme.c.bgElevated
        border.width: 1
        border.color: Theme.c.borderStrong
        // Swallow clicks so the backdrop's cancel never fires through.
        MouseArea { anchors.fill: parent }

        ColumnLayout {
            id: cardColumn
            anchors { left: parent.left; right: parent.right; top: parent.top
                      margins: Theme.m.space4 }
            spacing: Theme.m.space3

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.m.space3
                Rectangle {
                    width: 44; height: 44
                    radius: 10
                    gradient: Gradient {
                        GradientStop { position: 0; color: "#2C4A8F" }
                        GradientStop { position: 1; color: "#E8964A" }
                    }
                    Glyph {
                        anchors.centerIn: parent
                        width: 21; height: 21
                        path: Icons.pack
                        color: "#FFFFFF"
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        Layout.fillWidth: true
                        text: root.pack.name || ""
                        color: Theme.c.text
                        font.pixelSize: Theme.m.fontSizeLg
                        font.bold: true
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        text: (root.pack.author
                               ? (Tr.s["pack.by"] || "{a}")
                                     .replace("{a}", root.pack.author) : "")
                              + (root.pack.version
                                 ? " · v" + root.pack.version : "")
                        color: Theme.c.textDisabled
                        font.pixelSize: Theme.m.fontSizeSm
                        elide: Text.ElideRight
                    }
                }
            }

            Text {
                visible: (root.pack.description || "") !== ""
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: root.pack.description || ""
                color: Theme.c.textMuted
                font.pixelSize: Theme.m.fontSizeSm
                lineHeight: 1.4
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0

                Repeater {
                    model: root.pack.counts === undefined ? [] : [
                        { label: Tr.s["pack.cat.colors"] || "",
                          count: root.pack.counts.color_effects,
                          icon: Icons.color, tint: Theme.c.clipEffect },
                        { label: Tr.s["pack.cat.transitions"] || "",
                          count: root.pack.counts.transitions,
                          icon: Icons.transition, tint: Theme.c.textMuted },
                        { label: Tr.s["pack.cat.stickers"] || "",
                          count: root.pack.counts.stickers,
                          icon: Icons.sticker, tint: Theme.c.clipSticker },
                        { label: Tr.s["pack.cat.motion"] || "",
                          count: root.pack.counts.motion || 0,
                          icon: Icons.motion, tint: Theme.c.accent },
                        { label: Tr.s["pack.cat.export_presets"] || "",
                          count: root.pack.counts.export_presets || 0,
                          icon: Icons.exportIcon, tint: Theme.c.textMuted },
                        { label: Tr.s["pack.cat.audio_effects"] || "",
                          count: root.pack.counts.audio_effects || 0,
                          icon: Icons.audio, tint: Theme.c.clipAudio },
                        { label: Tr.s["pack.cat.music"] || "",
                          count: root.pack.counts.music || 0,
                          icon: Icons.audio, tint: Theme.c.clipMusic }
                    ]
                    delegate: Rectangle {
                        id: contentRow
                        required property var modelData
                        required property int index
                        visible: modelData.count > 0
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        color: "transparent"
                        border.width: 0
                        Rectangle {
                            visible: contentRow.index > 0
                            width: parent.width; height: 1
                            color: Theme.c.border
                        }
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: Theme.m.space2
                            anchors.rightMargin: Theme.m.space2
                            spacing: Theme.m.space2
                            Glyph {
                                width: 15; height: 15
                                path: contentRow.modelData.icon
                                color: contentRow.modelData.tint
                            }
                            Text {
                                Layout.fillWidth: true
                                text: contentRow.modelData.count + " "
                                      + contentRow.modelData.label
                                color: Theme.c.text
                                font.pixelSize: Theme.m.fontSizeSm
                            }
                        }
                    }
                }
            }

            Rectangle {
                visible: (root.pack.duplicates || 0) > 0
                Layout.fillWidth: true
                Layout.preferredHeight: warningText.implicitHeight
                                        + Theme.m.space2 * 2
                radius: Theme.m.radiusMd
                color: Qt.alpha(Theme.c.warning, 0.10)
                border.width: 1
                border.color: Qt.alpha(Theme.c.warning, 0.35)
                Text {
                    id: warningText
                    anchors { left: parent.left; right: parent.right
                              verticalCenter: parent.verticalCenter
                              margins: Theme.m.space2 }
                    wrapMode: Text.WordWrap
                    text: (Tr.s["pack.duplicates"] || "{n}")
                        .replace("{n}", root.pack.duplicates || 0)
                    color: Theme.c.warning
                    font.pixelSize: Theme.m.fontSizeXs
                    lineHeight: 1.35
                }
            }

            Rectangle {
                visible: root.pack.already_installed === true
                Layout.fillWidth: true
                Layout.preferredHeight: alreadyText.implicitHeight
                                        + Theme.m.space2 * 2
                radius: Theme.m.radiusMd
                color: Qt.alpha(Theme.c.danger, 0.10)
                border.width: 1
                border.color: Qt.alpha(Theme.c.danger, 0.35)
                Text {
                    id: alreadyText
                    anchors { left: parent.left; right: parent.right
                              verticalCenter: parent.verticalCenter
                              margins: Theme.m.space2 }
                    wrapMode: Text.WordWrap
                    text: Tr.s["pack.already_installed"] || ""
                    color: Theme.c.danger
                    font.pixelSize: Theme.m.fontSizeXs
                    lineHeight: 1.35
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.m.space2
                Text {
                    Layout.fillWidth: true
                    text: Tr.s["pack.safe_note"] || ""
                    color: Theme.c.textDisabled
                    font.pixelSize: Theme.m.fontSizeXs
                    wrapMode: Text.WordWrap
                }
                Rectangle {
                    width: cancelText.implicitWidth + Theme.m.space4
                    height: Theme.m.controlHeight
                    radius: Theme.m.radiusMd
                    color: "transparent"
                    border.width: 1
                    border.color: Theme.c.borderStrong
                    Text {
                        id: cancelText
                        anchors.centerIn: parent
                        text: Tr.s["pack.cancel"] || ""
                        color: Theme.c.textMuted
                        font.pixelSize: Theme.m.fontSizeSm + 1
                    }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: Packs.cancel_install() }
                }
                Rectangle {
                    objectName: "pack_install_confirm"
                    width: installText.implicitWidth + Theme.m.space4 + 8
                    height: Theme.m.controlHeight
                    radius: Theme.m.radiusMd
                    enabled: root.pack.already_installed !== true
                    color: enabled
                        ? (installHover.hovered ? Theme.c.accentHover
                                                : Theme.c.accent)
                        : Qt.alpha(Theme.c.accent, 0.35)
                    Text {
                        id: installText
                        anchors.centerIn: parent
                        text: Tr.s["pack.install"] || ""
                        color: Theme.c.onAccent
                        font.pixelSize: Theme.m.fontSizeSm + 1
                        font.bold: true
                    }
                    HoverHandler { id: installHover
                                   cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: if (parent.enabled) Packs.confirm_install()
                    }
                }
            }
        }
    }
}
