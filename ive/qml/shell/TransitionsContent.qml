// Transitions between clips, in families.
//
// Every card shows the REAL transition caught mid-blend between a blue
// and an orange plate (rendered by the engine's own blender, cached as
// a PNG). Drag a card onto a CUT on the timeline: the junction diamond
// lights up and the two clips blend there. The catalogue is JSON on
// disk (ive/transitions/library.py), shareable like the colour effects:
// drop a manifest + a greyscale luma PNG in user_data/transitions/ and
// a hand-drawn wipe becomes a transition.
import QtQuick
import QtQuick.Layouts
import components
import IVE

Item {
    id: root

    implicitHeight: column.implicitHeight + Theme.m.space3 * 2

    /*! "" = the family list; a section id = the transitions inside it. */
    property string section: ""
    property string tab: "transitions"

    readonly property var gridTransitions: {
        var live = Transitions.sections;
        if (root.tab === "favorites") {
            var favs = Transitions.favorites;
            return Transitions.favorite_transitions();
        }
        return root.section !== ""
            ? Transitions.transitions(root.section) : [];
    }

    function isFavorite(transitionId) {
        return Transitions.favorites.indexOf(transitionId) >= 0;
    }

    /*! The transition being dragged towards a cut, "" when none. Read by
        FloatingPanel as `interacting`: the panel must not retract and
        kill the drag mid-flight. */
    property string draggingTransition: ""
    property string draggingPreview: ""
    property point dragScenePos: Qt.point(0, 0)
    readonly property bool interacting: draggingTransition !== ""

    function sectionLabel(id) {
        return Tr.s["transition.section." + id] || id;
    }

    // The ghost that follows the pointer lives on the WINDOW, not in this
    // panel - same pattern as the stickers (the panel clips its children).
    Rectangle {
        id: dragGhost
        parent: root.Window.window ? root.Window.window.contentItem : root
        visible: root.draggingTransition !== ""
        width: 84
        height: 48
        radius: Theme.m.radiusSm
        color: "#22222A"
        border.width: 1
        border.color: Theme.c.accent
        opacity: 0.92
        x: root.dragScenePos.x - 42
        y: root.dragScenePos.y - 24
        z: 100000

        /*! Read by the timeline's DropArea via drop.source. */
        property string transitionId: root.draggingTransition

        Drag.active: root.draggingTransition !== ""
        Drag.keys: ["ive-transition"]
        Drag.hotSpot.x: 42
        Drag.hotSpot.y: 24

        Image {
            anchors.fill: parent
            anchors.margins: 2
            asynchronous: true
            fillMode: Image.PreserveAspectCrop
            source: root.draggingPreview
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
                { value: "transitions",
                  text: Tr.s["transition.tab.all"] || "" },
                { value: "favorites",
                  text: Tr.s["transition.tab.favorites"] || "" }
            ]
            onPicked: function (v) { root.tab = v; root.section = ""; }
        }

        // ── the families ──────────────────────────────────────────
        CardGroup {
            visible: root.tab === "transitions" && root.section === ""
            title: Tr.s["transition.sections"] || ""

            Repeater {
                model: Transitions.sections
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
                                text: (Tr.s["transition.count"] || "{n}")
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
                text: Tr.s["transition.hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }
        }

        // ── the transitions: one family, or the favourites ────────
        CardGroup {
            visible: root.section !== "" || root.tab === "favorites"
            title: root.tab === "favorites"
                ? (Tr.s["transition.tab.favorites"] || "")
                : root.sectionLabel(root.section)

            Text {
                visible: root.tab === "favorites"
                         && root.gridTransitions.length === 0
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["transition.fav_empty"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

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
                    text: Tr.s["transition.place_hint"] || ""
                    color: Theme.c.textDisabled
                    font.pixelSize: Theme.m.fontSizeXs
                    wrapMode: Text.WordWrap
                }
            }

            Flow {
                Layout.fillWidth: true
                spacing: Theme.m.space2

                Repeater {
                    model: root.gridTransitions
                    delegate: Item {
                        id: card
                        required property var modelData
                        objectName: "transition_" + modelData.id
                        width: 104
                        height: 84

                        Rectangle {
                            width: 104
                            height: 62
                            radius: Theme.m.radiusSm
                            color: Qt.alpha(Theme.c.glassOn, 0.06)
                            border.width: 1
                            border.color: cardHover.hovered
                                ? Theme.c.accent : Qt.alpha(Theme.c.glassOn, 0.12)
                            clip: true

                            // Still at rest, the REAL animation on
                            // hover: A blending into B by this very
                            // recipe (AnimatedPreview + a cached strip).
                            AnimatedPreview {
                                objectName: "transition_anim_"
                                            + card.modelData.id
                                anchors.fill: parent
                                anchors.margins: 2
                                still: Transitions.preview(card.modelData.id)
                                provider: function () {
                                    return Transitions.preview_strip(
                                        card.modelData.id);
                                }
                            }

                            StarButton {
                                objectName: "star_" + card.modelData.id
                                anchors.top: parent.top
                                anchors.right: parent.right
                                anchors.margins: 2
                                starred: root.isFavorite(card.modelData.id)
                                onToggled: Actions.invoke(
                                    "transition.toggle_favorite",
                                    { transition_id: card.modelData.id })
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
                            grabPermissions:
                                PointerHandler.CanTakeOverFromAnything
                            onCentroidChanged: {
                                if (active)
                                    root.dragScenePos = centroid.scenePosition;
                            }
                            onActiveChanged: {
                                if (active) {
                                    root.dragScenePos = centroid.scenePosition;
                                    root.draggingPreview =
                                        Transitions.preview(card.modelData.id);
                                    root.draggingTransition = card.modelData.id;
                                    return;
                                }
                                // drop() BEFORE clearing: turning Drag.active
                                // off without it is a CANCEL.
                                dragGhost.Drag.drop();
                                root.draggingTransition = "";
                                root.draggingPreview = "";
                            }
                        }
                    }
                }
            }
        }
    }
}
