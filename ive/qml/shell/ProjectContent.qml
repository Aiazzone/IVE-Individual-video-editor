// The open project: its name, where it is saved, and the media pool.
//
// Clicking an item loads it into the preview. Items whose file no longer
// resolves are marked, not hidden: a project that quietly drops half its
// media is worse than one that admits the links are broken.
import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs
import components
import IVE

Item {
    id: root

    implicitHeight: column.implicitHeight + Theme.m.space3 * 2
    /*! Media being dragged towards the timeline. While set, FloatingPanel
        reads `interacting` and must not retract - a retracting panel used
        to kill the drag mid-flight. */
    property string draggingMediaId: ""
    property string draggingMediaName: ""
    property point dragScenePos: Qt.point(0, 0)
    readonly property bool interacting: draggingMediaId !== ""

    // Window-level ghost carrying the Drag: the panel clips its children,
    // so a ghost inside it vanished at the edge - and the attached Drag
    // only publishes positions when its item MOVES, which this one does.
    // Ending with Drag.drop() is what actually delivers the drop; flipping
    // Drag.active off is a cancel.
    Rectangle {
        id: mediaGhost
        parent: root.Window.window
            ? root.Window.window.contentItem : root
        visible: root.draggingMediaId !== ""
        width: 120
        height: 26
        radius: Theme.m.radiusSm
        color: Theme.c.clipVideo
        opacity: 0.9
        x: root.dragScenePos.x - 60
        y: root.dragScenePos.y - 13
        z: 100000

        /*! Read by the timeline's DropArea via drop.source. */
        property string mediaId: root.draggingMediaId

        Drag.active: root.draggingMediaId !== ""
        Drag.keys: ["ive-media"]
        Drag.hotSpot.x: 60
        Drag.hotSpot.y: 13

        Text {
            anchors.fill: parent
            anchors.margins: 5
            text: root.draggingMediaName
            color: "#FFFFFF"
            font.pixelSize: Theme.m.fontSizeXs
            elide: Text.ElideMiddle
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }

    FileDialog {
        id: importDialog
        title: Tr.s["project.import_media"] || "Import media"
        fileMode: FileDialog.OpenFiles
        nameFilters: [
            (Tr.s["media.filter.video"] || "Media files")
                + " (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.mts *.m2ts *.mpg *.mpeg *.wmv"
                + " *.mp3 *.wav *.flac *.aac *.m4a *.ogg *.opus"
                + " *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)",
            (Tr.s["media.filter.all"] || "All files") + " (*)"
        ]
        onAccepted: {
            var list = [];
            for (var i = 0; i < selectedFiles.length; i++)
                list.push(String(selectedFiles[i]));
            Actions.invoke("project.import_media", { paths: list });
        }
    }

    ColumnLayout {
        id: column
        anchors { left: parent.left; right: parent.right; top: parent.top
                  margins: Theme.m.space3 }
        spacing: Theme.m.space3

        // ── no project ────────────────────────────────────────────
        CardGroup {
            visible: !Project.isOpen
            title: Tr.s["project.empty.title"] || ""
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["project.empty.hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }
        }

        // ── identity ──────────────────────────────────────────────
        CardGroup {
            visible: Project.isOpen
            title: Project.name

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.m.space2
                Text {
                    text: Tr.s["project.saved_in"] || ""
                    color: Theme.c.textDisabled
                    font.pixelSize: Theme.m.fontSizeXs
                }
                Text {
                    Layout.fillWidth: true
                    text: Project.folder
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeXs
                    elide: Text.ElideLeft
                }
            }
            Text {
                visible: Project.dirty
                text: Tr.s["project.dirty"] || ""
                color: Theme.c.warning
                font.pixelSize: Theme.m.fontSizeXs
            }
        }

        // ── media pool ────────────────────────────────────────────
        CardGroup {
            visible: Project.isOpen
            title: (Tr.s["project.media_title"] || "") + "  ·  " + Project.mediaCount

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.m.controlHeight
                radius: Theme.m.radiusMd
                color: Qt.alpha(Theme.c.glassOn, addHover.hovered ? 0.14 : 0.07)
                border.width: 1
                border.color: Theme.c.border
                RowLayout {
                    anchors.centerIn: parent
                    spacing: Theme.m.space2
                    Glyph {
                        width: 15; height: 15
                        path: Icons.plus
                        color: Theme.c.text
                    }
                    Text {
                        text: Tr.s["project.add_media"] || ""
                        color: Theme.c.text
                        font.pixelSize: Theme.m.fontSizeSm
                    }
                }
                HoverHandler { id: addHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: importDialog.open() }
            }

            Text {
                visible: Project.mediaCount > 0
                Layout.fillWidth: true
                Layout.topMargin: Theme.m.space1
                text: Tr.s["project.drag_hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
            }

            Text {
                visible: Project.mediaCount === 0
                Layout.fillWidth: true
                Layout.topMargin: Theme.m.space2
                wrapMode: Text.WordWrap
                text: (Tr.s["project.no_media"] || "") + ". "
                      + (Tr.s["project.drop_hint"] || "")
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            Repeater {
                model: Project.media
                delegate: Item {
                    id: poolRow
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 46

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.m.radiusMd
                        color: dragHandler.active ? Theme.c.bgPressed
                             : itemHover.hovered ? Theme.c.bgHover : "transparent"
                    }

                    // Internal drag, NOT Drag.Automatic with mime data: the
                    // automatic path hands the gesture to the platform's
                    // native drag and never reached our DropArea. The Drag
                    // itself rides the window-level ghost above - which
                    // MOVES, publishing drag positions, and whose release
                    // path calls Drag.drop(); this row only feeds it.
                    DragHandler {
                        id: dragHandler
                        enabled: !poolRow.modelData.missing
                        target: null
                        // The row lives inside a Flickable; without this the
                        // list steals the gesture and no drag ever begins.
                        grabPermissions: PointerHandler.CanTakeOverFromAnything
                        onCentroidChanged: {
                            if (active)
                                root.dragScenePos = centroid.scenePosition;
                        }
                        onActiveChanged: {
                            if (active) {
                                root.dragScenePos = centroid.scenePosition;
                                root.draggingMediaId = poolRow.modelData.id;
                                root.draggingMediaName = poolRow.modelData.name;
                                return;
                            }
                            mediaGhost.Drag.drop();
                            root.draggingMediaId = "";
                            root.draggingMediaName = "";
                        }
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.m.space2
                        anchors.rightMargin: Theme.m.space1
                        spacing: Theme.m.space2

                        // A real frame from the file, decoded off the GUI
                        // thread by the "thumb" image provider. The colour
                        // block is what shows until it arrives (or when the
                        // file has no picture).
                        Rectangle {
                            Layout.preferredWidth: 40
                            Layout.preferredHeight: 26
                            radius: 3
                            clip: true
                            color: modelData.missing ? Theme.c.bgSunken
                                 : modelData.width > 0 ? Theme.c.clipVideo
                                                       : Theme.c.clipAudio
                            Image {
                                anchors.fill: parent
                                visible: !poolRow.modelData.missing
                                asynchronous: true
                                fillMode: Image.PreserveAspectCrop
                                // 2x the cell, for crispness on scaled UIs.
                                sourceSize.width: 80
                                // Thumbs.rev makes this re-resolve when the
                                // worker lands the PNG.
                                source: poolRow.modelData.missing
                                        || Thumbs.rev < 0 ? ""
                                    : Thumbs.thumb(poolRow.modelData.path)
                            }
                            Glyph {
                                anchors.centerIn: parent
                                width: 14; height: 14
                                visible: modelData.missing
                                path: Icons.alert
                                color: Theme.c.warning
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Text {
                                Layout.fillWidth: true
                                text: modelData.name
                                color: modelData.missing ? Theme.c.textDisabled : Theme.c.text
                                font.pixelSize: Theme.m.fontSizeSm
                                elide: Text.ElideMiddle
                            }
                            Text {
                                Layout.fillWidth: true
                                text: modelData.missing
                                    ? (Tr.s["project.missing"] || "")
                                    : [modelData.durationLabel, modelData.sizeLabel]
                                        .filter(function (v) { return v !== ""; }).join("  ·  ")
                                color: modelData.missing ? Theme.c.warning : Theme.c.textDisabled
                                font.pixelSize: Theme.m.fontSizeXs
                                elide: Text.ElideRight
                            }
                        }

                        // Dragging is the pleasant way in; this is the one
                        // that always works, including from the keyboard.
                        IconButton {
                            size: 24; iconSize: 13; tipSide: "left"
                            icon: Icons.plus
                            label: Tr.s["timeline.place_media"] || ""
                            opacity: itemHover.hovered ? 1 : 0.35
                            onTriggered: Actions.invoke("timeline.place_media",
                                                        { media_id: modelData.id })
                        }

                        IconButton {
                            size: 24; iconSize: 13; tipSide: "left"
                            icon: Icons.trash
                            label: Tr.s["project.remove_media"] || ""
                            opacity: itemHover.hovered ? 1 : 0
                            onTriggered: Actions.invoke("project.remove_media",
                                                        { media_id: modelData.id })
                        }
                    }

                    HoverHandler {
                        id: itemHover
                        cursorShape: dragHandler.active ? Qt.ClosedHandCursor
                                                        : Qt.PointingHandCursor
                    }
                    TapHandler {
                        enabled: !modelData.missing
                        onTapped: Actions.invoke("project.preview_media",
                                                 { media_id: modelData.id })
                    }
                }
            }
        }
    }
}
