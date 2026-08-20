// Stickers, in two tabs.
//
//   STATIC     SVG/PNG stickers, in families (shapes, greetings, ...).
//              QML renders the SVG natively, so the previews ARE the
//              stickers - crisp at any size, no thumbnail worker.
//   ANIMATED   Lottie stickers, same family structure. Catalogued and
//              installable today; the live preview and the timeline
//              placement arrive with the Lottie renderer (docs/STICKERS.md),
//              so for now each card shows a badge, not a moving preview.
//
// The catalogue is JSON on disk (ive/stickers/library.py), shareable like
// the colour effects: drop a manifest + files in user_data/stickers/.
import QtQuick
import QtQuick.Layouts
import components
import IVE

Item {
    id: root

    implicitHeight: column.implicitHeight + Theme.m.space3 * 2

    property string tab: "static"
    /*! "" = the family grid; a section id = the stickers inside it. */
    property string section: ""

    /*! What the grid shows: the open family's stickers, or the starred
        ones (both kinds mixed). Reading Stickers.staticSections and
        Stickers.favorites keeps the binding live on language flips and
        on every star toggle. */
    readonly property var gridStickers: {
        var live = Stickers.staticSections;
        if (root.tab === "favorites") {
            var favs = Stickers.favorites;
            return Stickers.favorite_stickers();
        }
        return root.section !== ""
            ? Stickers.stickers(root.tab, root.section) : [];
    }

    function isFavorite(stickerId) {
        return Stickers.favorites.indexOf(stickerId) >= 0;
    }

    /*! The sticker being dragged towards the timeline, "" when none. Read
        by FloatingPanel as `interacting`: the panel must not retract and
        kill the drag mid-flight. */
    property string draggingSticker: ""
    property string draggingFileUrl: ""
    property point dragScenePos: Qt.point(0, 0)
    readonly property bool interacting: draggingSticker !== ""

    function sectionLabel(id) {
        return Tr.s["sticker.section." + id] || id;
    }

    /*! The SELECTED sticker clip (shared selection), or null: the
        Animazione section below edits its motion preset. */
    readonly property var motionClip: {
        var id = Shell.v.selectedClipId || "";
        if (id === "")
            return null;
        var clips = Project.timelineClips;
        for (var i = 0; i < clips.length; i++)
            if (clips[i].id === id && clips[i].stickerId)
                return clips[i];
        return null;
    }

    // The ghost that follows the pointer lives on the WINDOW, not in this
    // panel: the panel clips its children, and the attached Drag publishes
    // its position only when its item MOVES - same pattern as the colour
    // effects (see ColorContent.qml).
    Rectangle {
        id: dragGhost
        parent: root.Window.window ? root.Window.window.contentItem : root
        visible: root.draggingSticker !== ""
        width: 72
        height: 72
        radius: Theme.m.radiusSm
        color: root.draggingFileUrl !== "" ? "transparent"
                                           : Theme.c.clipSticker
        opacity: 0.9
        x: root.dragScenePos.x - 36
        y: root.dragScenePos.y - 36
        z: 100000

        /*! Read by the timeline's DropArea via drop.source. */
        property string stickerId: root.draggingSticker

        Drag.active: root.draggingSticker !== ""
        Drag.keys: ["ive-sticker"]
        Drag.hotSpot.x: 36
        Drag.hotSpot.y: 36

        Image {
            anchors.fill: parent
            visible: root.draggingFileUrl !== ""
            asynchronous: true
            fillMode: Image.PreserveAspectFit
            sourceSize.width: 144
            sourceSize.height: 144
            source: root.draggingFileUrl
        }
        Text {
            anchors.centerIn: parent
            visible: root.draggingFileUrl === ""
            text: "Lottie"
            color: "#FFFFFF"
            font.pixelSize: Theme.m.fontSizeXs
        }
    }

    ColumnLayout {
        id: column
        anchors { left: parent.left; right: parent.right; top: parent.top
                  margins: Theme.m.space3 }
        spacing: Theme.m.space3

        // ── tabs ──────────────────────────────────────────────────
        Segmented {
            Layout.fillWidth: true
            value: root.tab
            model: [
                { value: "static", text: Tr.s["sticker.tab.static"] || "" },
                { value: "animated", text: Tr.s["sticker.tab.animated"] || "" },
                { value: "favorites", text: Tr.s["sticker.tab.favorites"] || "" }
            ]
            onPicked: function (v) { root.tab = v; root.section = ""; }
        }

        // ── the families of the open tab ──────────────────────────
        CardGroup {
            visible: root.section === "" && root.tab !== "favorites"
            title: Tr.s["sticker.sections"] || ""

            Repeater {
                model: root.tab === "static"
                    ? Stickers.staticSections : Stickers.animatedSections
                delegate: Item {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 48

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.m.radiusMd
                        color: sectionHover.hovered ? Theme.c.bgHover
                                                    : Qt.alpha(Theme.c.glassOn, 0.05)
                    }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.m.space3
                        anchors.rightMargin: Theme.m.space2
                        spacing: Theme.m.space3

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                Layout.fillWidth: true
                                text: root.sectionLabel(modelData.id)
                                color: Theme.c.text
                                font.pixelSize: Theme.m.fontSizeSm + 2
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                text: (Tr.s["sticker.count"] || "{n}")
                                          .replace("{n}", modelData.count)
                                color: Theme.c.textDisabled
                                font.pixelSize: Theme.m.fontSizeXs
                            }
                        }
                        Glyph {
                            width: 15; height: 15
                            rotation: -90
                            path: Icons.chevronDown
                            color: Theme.c.textDisabled
                        }
                    }
                    HoverHandler { id: sectionHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: root.section = modelData.id }
                }
            }

            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: (root.tab === "animated"
                       ? Tr.s["sticker.animated_hint"]
                       : Tr.s["sticker.hint"]) || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }
        }

        // ── the stickers: one family, or the favourites ───────────
        CardGroup {
            visible: root.section !== "" || root.tab === "favorites"
            title: root.tab === "favorites"
                ? (Tr.s["sticker.tab.favorites"] || "")
                : root.sectionLabel(root.section)

            Text {
                visible: root.tab === "favorites"
                         && root.gridStickers.length === 0
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["sticker.fav_empty"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            // The way back sits first: a sub-page without an exit teaches
            // the user to close the whole panel instead.
            RowLayout {
                visible: root.tab !== "favorites"
                Layout.fillWidth: true
                spacing: Theme.m.space2
                IconButton {
                    size: 24; iconSize: 14
                    icon: Icons.chevronDown
                    rotation: 90
                    label: Tr.s["sticker.back"] || ""
                    onTriggered: root.section = ""
                }
                Text {
                    Layout.fillWidth: true
                    text: (root.tab === "animated"
                           ? Tr.s["sticker.animated_hint"]
                           : Tr.s["sticker.place_hint"]) || ""
                    color: Theme.c.textDisabled
                    font.pixelSize: Theme.m.fontSizeXs
                    wrapMode: Text.WordWrap
                }
            }

            Flow {
                Layout.fillWidth: true
                spacing: Theme.m.space2

                Repeater {
                    model: root.gridStickers
                    delegate: Item {
                        id: card
                        required property var modelData
                        objectName: "sticker_" + modelData.id
                        width: 104
                        height: 118

                        Rectangle {
                            width: 104
                            height: 96
                            radius: Theme.m.radiusSm
                            color: Qt.alpha(Theme.c.glassOn, 0.06)
                            border.width: 1
                            border.color: cardHover.hovered
                                ? Theme.c.accent : Qt.alpha(Theme.c.glassOn, 0.12)

                            // Static: the SVG itself, rendered by Qt.
                            Image {
                                visible: card.modelData.kind === "static"
                                anchors.centerIn: parent
                                width: 80
                                height: 80
                                sourceSize.width: 160
                                sourceSize.height: 160
                                fillMode: Image.PreserveAspectFit
                                asynchronous: true
                                source: card.modelData.kind === "static"
                                    ? card.modelData.fileUrl : ""
                            }

                            // Animated: a real frame at rest, and the
                            // ANIMATION itself under the mouse (a
                            // cached rlottie film strip).
                            AnimatedPreview {
                                visible: card.modelData.kind === "animated"
                                // NOT "sticker_*": the tests enumerate
                                // cards by that prefix, and animated ids
                                // already start with "anim_".
                                objectName: "anim_preview_"
                                            + card.modelData.id
                                anchors.centerIn: parent
                                width: 80
                                height: 80
                                stillFillMode: Image.PreserveAspectFit
                                still: card.modelData.kind === "animated"
                                    ? Stickers.preview(card.modelData.id) : ""
                                provider: function () {
                                    return Stickers.preview_strip(
                                        card.modelData.id);
                                }
                            }
                            // No "Lottie" badge: a format name means
                            // nothing to the user - the hover preview
                            // already shows that this one MOVES.
                            StarButton {
                                objectName: "star_" + card.modelData.id
                                anchors.top: parent.top
                                anchors.right: parent.right
                                anchors.margins: 2
                                starred: root.isFavorite(card.modelData.id)
                                onToggled: Actions.invoke(
                                    "sticker.toggle_favorite",
                                    { sticker_id: card.modelData.id })
                            }
                        }

                        Text {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            text: card.modelData.name
                            color: Theme.c.textMuted
                            font.pixelSize: Theme.m.fontSizeXs
                            elide: Text.ElideRight
                        }

                        HoverHandler { id: cardHover; cursorShape: Qt.OpenHandCursor }
                        DragHandler {
                            target: null
                            // The panel scrolls in a Flickable; without
                            // this the list steals the gesture.
                            grabPermissions:
                                PointerHandler.CanTakeOverFromAnything
                            onCentroidChanged: {
                                if (active)
                                    root.dragScenePos = centroid.scenePosition;
                            }
                            onActiveChanged: {
                                if (active) {
                                    root.dragScenePos = centroid.scenePosition;
                                    root.draggingFileUrl =
                                        card.modelData.kind === "static"
                                            ? card.modelData.fileUrl : "";
                                    root.draggingSticker = card.modelData.id;
                                    return;
                                }
                                // drop() BEFORE clearing: turning Drag.active
                                // off without it is a CANCEL, and the drop
                                // area under the pointer never hears a thing.
                                dragGhost.Drag.drop();
                                root.draggingSticker = "";
                                root.draggingFileUrl = "";
                            }
                        }
                    }
                }
            }
        }
        // ── the SELECTED sticker's animation ──────────────────────
        // Under the catalogue, like the Text panel's: shown whenever a
        // sticker clip is selected (on the timeline or by tapping it on
        // the video), browsing stays available above. Every card
        // previews THIS sticker moved by THAT preset - still at rest,
        // alive under the mouse.
        CardGroup {
            visible: root.motionClip !== null
            title: (Tr.s["motion.section"] || "")
                   + " — " + (root.motionClip !== null
                              ? root.motionClip.name : "")

            MotionPicker {
                Layout.fillWidth: true
                clip: root.motionClip
                presets: Stickers.motion_presets()
                still: root.motionClip !== null
                    ? Stickers.still_url(root.motionClip.stickerId) : ""
                stripFor: function (presetId) {
                    return root.motionClip === null ? null
                        : Stickers.motion_strip(root.motionClip.stickerId,
                                                presetId);
                }
            }
        }
    }
}
