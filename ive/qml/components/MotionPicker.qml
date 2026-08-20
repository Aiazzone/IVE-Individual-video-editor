// The motion-preset cards of ONE overlay clip (a sticker or a title).
//
// A "None" card plus one card per preset, each previewing THIS overlay
// moved by THAT recipe: still at rest, alive under the mouse (the
// AnimatedPreview film strip). Tapping a card applies the preset with
// one undo step through timeline.set_clip_motion; the current one wears
// the accent border.
//
// The host decides what the still and the strip are: a sticker's file and
// Stickers.motion_strip, or a title's raster and Motion.text_strip. The
// cards never know which kind of clip they animate.
import QtQuick
import IVE

Flow {
    id: root

    /*! The clip being edited (its id and motionId are read live). */
    property var clip: null
    /*! The catalogue, as Motion.presets / Stickers.motion_presets(). */
    property var presets: []
    /*! The overlay at rest, as a file URL. */
    property string still: ""
    /*! function (presetId) → the strip descriptor, or null. */
    property var stripFor: null

    readonly property string motionId: clip !== null && clip.motionId
                                       ? clip.motionId : ""

    spacing: Theme.m.space2

    function kindLabel(kind) {
        return Tr.s["motion.kind." + kind] || kind;
    }

    // "None": the resting state, and the way back to it.
    Item {
        objectName: "motion_none"
        width: 104
        height: 96
        Rectangle {
            width: 104
            height: 74
            radius: Theme.m.radiusSm
            color: Qt.alpha(Theme.c.glassOn, 0.06)
            border.width: root.motionId === "" ? 2 : 1
            border.color: root.motionId === "" || noneHover.hovered
                ? Theme.c.accent : Qt.alpha(Theme.c.glassOn, 0.12)
            Glyph {
                anchors.centerIn: parent
                width: 22; height: 22
                path: Icons.close
                color: Theme.c.textDisabled
            }
        }
        Text {
            anchors.bottom: parent.bottom
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: Tr.s["motion.none"] || ""
            color: Theme.c.textMuted
            font.pixelSize: Theme.m.fontSizeXs
            elide: Text.ElideRight
        }
        HoverHandler { id: noneHover; cursorShape: Qt.PointingHandCursor }
        TapHandler {
            onTapped: if (root.clip !== null)
                Actions.invoke("timeline.set_clip_motion",
                               { clip_id: root.clip.id, motion_id: "" })
        }
    }

    Repeater {
        model: root.clip !== null ? root.presets : []
        delegate: Item {
            id: card
            required property var modelData
            objectName: "motion_" + modelData.id
            width: 104
            height: 96

            readonly property bool current: root.motionId === modelData.id

            Rectangle {
                width: 104
                height: 74
                radius: Theme.m.radiusSm
                color: Qt.alpha(Theme.c.glassOn, 0.06)
                border.width: card.current ? 2 : 1
                border.color: card.current || cardHover.hovered
                    ? Theme.c.accent : Qt.alpha(Theme.c.glassOn, 0.12)
                clip: true

                AnimatedPreview {
                    anchors.fill: parent
                    anchors.margins: 4
                    stillFillMode: Image.PreserveAspectFit
                    interval: 60
                    still: root.still
                    provider: function () {
                        return root.stripFor !== null
                            ? root.stripFor(card.modelData.id) : null;
                    }
                }

                Rectangle {
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.margins: 4
                    width: kindTag.implicitWidth + 10
                    height: kindTag.implicitHeight + 4
                    radius: height / 2
                    color: Qt.alpha(Theme.c.accent, 0.25)
                    Text {
                        id: kindTag
                        anchors.centerIn: parent
                        text: root.kindLabel(card.modelData.kind)
                        color: Theme.c.text
                        font.pixelSize: Theme.m.fontSizeXs
                    }
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
            HoverHandler { id: cardHover; cursorShape: Qt.PointingHandCursor }
            TapHandler {
                onTapped: if (root.clip !== null)
                    Actions.invoke("timeline.set_clip_motion", {
                        clip_id: root.clip.id, motion_id: card.modelData.id
                    })
            }
        }
    }
}
