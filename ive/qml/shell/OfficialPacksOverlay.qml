// The startup question: "download the extra content?"
//
// Over everything, at startup, while something offered online is missing
// (official packs AND the default AI models - ive/ui/online_content.py
// owns the list and the rules). Every item is a checkbox with its size.
// "Download" fetches the ticked ones and answers the question for good;
// "Not now" asks again at the next start - unless the "Don't ask again"
// switch is on. Settings > Media keeps a button for later; nothing is
// ever fetched in silence.
import QtQuick
import QtQuick.Layouts
import components
import IVE

Item {
    id: root

    readonly property var offers: OnlineContent.missing
    visible: OnlineContent.shouldOffer && offers.length > 0

    /*! Ids the user UNticked: everything starts ticked, and an item that
        appears later (a list refreshed while open) is ticked too. */
    property var unticked: []
    readonly property var ticked: offers.filter(function (p) {
        return unticked.indexOf(p.id) < 0;
    }).map(function (p) { return p.id; })
    /*! The "Don't ask again" switch. */
    property bool neverAsk: false

    function toggle(id) {
        var next = unticked.slice();
        var at = next.indexOf(id);
        if (at >= 0) next.splice(at, 1); else next.push(id);
        unticked = next;
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
                text: Tr.s["online.title"] || ""
                color: Theme.c.text
                font.pixelSize: Theme.m.fontSizeLg
                font.bold: true
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                text: Tr.s["online.text"] || ""
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
                            text: Tr.s["online.kind." + row.modelData.kind] || ""
                            color: Theme.c.textDisabled
                            font.pixelSize: Theme.m.fontSizeXs
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
                text: Tr.s["online.licence"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                wrapMode: Text.WordWrap
                lineHeight: 1.35
            }

            SwitchRow {
                objectName: "offer_never_ask"
                Layout.fillWidth: true
                checked: root.neverAsk
                label: Tr.s["online.never_ask"] || ""
                onToggled: function (v) { root.neverAsk = v; }
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
                        text: Tr.s["online.later"] || ""
                        color: Theme.c.textMuted
                        font.pixelSize: Theme.m.fontSizeSm + 1
                    }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: Actions.invoke("online.dismiss_offer",
                                                 { never_ask: root.neverAsk })
                    }
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
                        text: (Tr.s["online.download"] || "")
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
                            Actions.invoke("online.download", {
                                ids: root.ticked, never_ask: root.neverAsk });
                        }
                    }
                }
            }
        }
    }
}
