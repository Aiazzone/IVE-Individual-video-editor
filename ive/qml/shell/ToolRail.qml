// Icon-only tool rail. Every button opens its section in the floating panel.
//
// The rail is a glass surface at the ICON threshold (scrimIcons), not the text
// one: icons need 3:1, not 4.5:1, and using the text scrim here would make the
// rail look like a slab instead of glass. See docs/UI_SHELL.md section 4.
import QtQuick
import QtQuick.Layouts
import components
import IVE

Item {
    id: root

    /*! Item sampled for the blur; see GlassSurface. */
    property Item sceneSource: null
    /*! Currently open section, "" when the panel is closed. */
    property string section: ""

    signal sectionRequested(string section)

    readonly property var sections: [
        // "+" only ever means "start something new". Browsing what is
        // already in the project is a different job, so it gets its own
        // button right below: one icon, one meaning.
        { key: "new",     icon: Icons.plus,    label: "rail.new_project", shortcut: "Ctrl+N" },
        // The clapperboard, not a folder: this is where the FILM lives.
        { key: "project", icon: Icons.clapper, label: "rail.project",     shortcut: "1" },
        { key: "text",      icon: Icons.text,      label: "rail.text",      shortcut: "2" },
        { key: "effects",   icon: Icons.effects,   label: "rail.effects",   shortcut: "3" },
        { key: "stickers",  icon: Icons.sticker,   label: "rail.stickers",  shortcut: "" },
        { key: "audio",     icon: Icons.audio,     label: "rail.audio",     shortcut: "4" },
        { key: "color",     icon: Icons.color,     label: "rail.color",     shortcut: "5" },
        { key: "ai",        icon: Icons.ai,        label: "rail.ai",        shortcut: "6" },
        { key: "export",  icon: Icons.exportIcon, label: "rail.export",  shortcut: "Ctrl+E" },
        { key: "-",         icon: "",              label: "",               shortcut: "" },
        { key: "assistant", icon: Icons.assistant, label: "rail.assistant", shortcut: "A" },
        { key: "settings",  icon: Icons.settings,  label: "rail.settings",  shortcut: "," }
    ]

    width: Theme.m.toolRailWidth
    implicitHeight: column.implicitHeight + Theme.m.space2 * 2

    GlassSurface {
        anchors.fill: parent
        sceneSource: root.sceneSource
        originX: root.x
        originY: root.y
        radius: Theme.m.toolRailRadius
        scrim: Theme.m.scrimIcons
    }

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.margins: Theme.m.space2
        spacing: Theme.m.space1

        Repeater {
            model: root.sections
            delegate: Item {
                required property var modelData
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: modelData.key === "-" ? 24 : Theme.m.toolRailButton
                Layout.preferredHeight: modelData.key === "-"
                    ? Theme.m.space4 : Theme.m.toolRailButton

                Rectangle {                       // separator
                    visible: modelData.key === "-"
                    anchors.centerIn: parent
                    width: 24
                    height: 1
                    color: Qt.alpha(Theme.c.glassOn, 0.14)
                }

                // The rail sits on its own glass plate, which DOES follow
                // the theme - so its icons use the themed colour, not the
                // fixed on-video white.
                IconButton {
                    visible: modelData.key !== "-"
                    anchors.fill: parent
                    icon: modelData.icon
                    label: Tr.s[modelData.label] || modelData.label
                    shortcut: modelData.shortcut
                    checked: root.section === modelData.key
                    tipSide: Shell.v.railSide === "left" ? "right" : "left"
                    onTriggered: root.sectionRequested(modelData.key)
                }
            }
        }
    }
}
