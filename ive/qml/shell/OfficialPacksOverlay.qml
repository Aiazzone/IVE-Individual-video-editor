// The first-run offer: "want the official music packs?"
//
// Shown ONCE, over everything, the first time the shell opens with a
// catalogue that has something not yet installed. Every pack is a
// checkbox with its size; "Download" queues the ticked ones on the
// pack service's worker and closes the card, "Later" just closes it.
// Either way packs.offer_shown is set, and the same list lives forever
// under Packs > Official - nobody is nagged, nothing downloads in
// silence.
import QtQuick
import QtQuick.Layouts
import components
import IVE

Item {
    id: root

    readonly property var offers: Packs.official.filter(function (p) {
        return !p.installed;
    })
    visible: !Shell.v.packsOfferShown && offers.length > 0

    /*! Ids the user has ticked; everything ticked at first. */
    property var ticked: []
    Component.onCompleted: ticked = offers.map(function (p) { return p.id; })

    function toggle(id) {
        var next = ticked.slice();
        var at = next.indexOf(id);
        if (at >= 0) next.splice(at, 1); else next.push(id);
        ticked = next;
    }
    readonly property int tickedMb: offers.reduce(function (sum, p) {
        return sum + (ticked.indexOf(p.id) >= 0 ? p.sizeMb : 0);
    }, 0)

    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.45)
        MouseArea { anchors.fill: parent }   // swallow clicks
    }

    Rectangle {
        id: card
        objectName: "official_offer_card"
        anchors.centerIn: parent
        width: Math.min(460, parent.width - Theme.m.space5 * 2)
        height: body.implicitHeight + Theme.m.space4 * 2
        radius: Theme.m.radiusLg
        color: Theme.c.bgElevated
        border.width: 1
        border.color: Theme.c.borderStrong

        ColumnLayout {
            id: body
            anchors { left: parent.left; right: parent.right; top: parent.top
                      margins: Theme.m.space4 }
            spacing: Theme.m.space3

            Text {
                Layout.fillWidth: true
                text: Tr.s["pack.offer_title"] || ""
                color: Theme.c.text
                font.pixelSize: Theme.m.fontSizeLg
                font.bold: true
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                text: Tr.s["pack.offer_text"] || ""
                color: Theme.c.textMuted
                font.pixelSize: Theme.m.fontSizeSm
                wrapMode: Text.WordWrap
                lineHeight: 1.35
            }

            Repeater {
                model: root.offers
                delegate: Item {
                    id: row
                    required property var modelData
                    objectName: "offer_item_" + modelData.id
                    Layout.fillWidth: true
                    Layout.preferredHeight: 30
                    readonly property bool checked:
                        root.ticked.indexOf(modelData.id) >= 0
                    RowLayout {
                        anchors.fill: parent
                        spacing: Theme.m.space2
                        Rectangle {
                            width: 16; height: 16
                            radius: 4
                            color: row.checked ? Theme.c.accent : "transparent"
                            border.width: row.checked ? 0 : 1.5
                            border.color: Theme.c.borderStrong
                            Glyph {
                                visible: row.checked
                                anchors.centerIn: parent
                                width: 10; height: 10
                                path: Icons.check
                                color: Theme.c.onAccent
                                weight: 3
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: row.modelData.name
                            color: Theme.c.text
                            font.pixelSize: Theme.m.fontSizeSm
                            elide: Text.ElideRight
                        }
                        Text {
                            text: row.modelData.sizeMb + " MB"
                            color: Theme.c.textDisabled
                            font.pixelSize: Theme.m.fontSizeXs
                        }
                    }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: root.toggle(row.modelData.id) }
                }
            }

            Text {
                Layout.fillWidth: true
                text: Tr.s["pack.offer_licence"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                wrapMode: Text.WordWrap
                lineHeight: 1.35
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.m.space2
                Rectangle {
                    objectName: "offer_later"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 38
                    radius: Theme.m.radiusLg
                    color: "transparent"
                    border.width: 1
                    border.color: Theme.c.borderStrong
                    Text {
                        anchors.centerIn: parent
                        text: Tr.s["pack.later"] || ""
                        color: Theme.c.textMuted
                        font.pixelSize: Theme.m.fontSizeSm + 1
                    }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: Actions.invoke("pack.dismiss_offer") }
                }
                Rectangle {
                    objectName: "offer_download"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 38
                    radius: Theme.m.radiusLg
                    enabled: root.ticked.length > 0
                    color: enabled ? (dlHover.hovered ? Theme.c.accentHover
                                                      : Theme.c.accent)
                                   : Qt.alpha(Theme.c.accent, 0.35)
                    Text {
                        anchors.centerIn: parent
                        text: (Tr.s["pack.download"] || "")
                              + (root.tickedMb > 0 ? "  ·  " + root.tickedMb + " MB" : "")
                        color: Theme.c.onAccent
                        font.pixelSize: Theme.m.fontSizeSm + 1
                        font.bold: true
                    }
                    HoverHandler { id: dlHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: {
                            if (!parent.enabled)
                                return;
                            Actions.invoke("pack.download", { pack_ids: root.ticked });
                            Actions.invoke("pack.dismiss_offer");
                        }
                    }
                }
            }
        }
    }
}
