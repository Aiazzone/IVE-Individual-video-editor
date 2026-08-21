// Settings, shown inside the floating panel.
//
// Note what this file does NOT do: it never writes a setting. Every control
// invokes an action, so the same operations stay reachable from the command
// palette, a script, a plugin and the assistant.
//
// `interacting` is read by FloatingPanel: while a slider is being dragged the
// panel must not retract (docs/UI_SHELL.md section 7, rule 1).
import QtQuick
import QtQuick.Layouts
import components
import IVE

Item {
    id: root

    implicitHeight: column.implicitHeight + Theme.m.space3 * 2
    readonly property bool interacting:
        delaySlider.pressed || opacitySlider.pressed || blurSlider.pressed

    // Tabs rather than one long column: a panel that needs scrolling hides
    // half its controls, which is exactly how the transparency sliders went
    // unnoticed for a whole session.
    property string tab: "layout"

    ColumnLayout {
        id: column
        anchors {
            left: parent.left
            right: parent.right
            top: parent.top
            margins: Theme.m.space3
        }
        spacing: Theme.m.space3

        Segmented {
            Layout.fillWidth: true
            value: root.tab
            model: [
                { value: "layout",     text: Tr.s["settings.tab.layout"] || "" },
                { value: "appearance", text: Tr.s["settings.tab.appearance"] || "" },
                { value: "language",   text: Tr.s["settings.tab.language"] || "" }
            ]
            onPicked: function (v) { root.tab = v; }
        }

        // ── language ──────────────────────────────────────────────
        CardGroup {
            visible: root.tab === "language"
            title: Tr.s["settings.section.language"] || ""

            Repeater {
                model: Tr.availableLanguages
                delegate: Item {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.m.controlHeight
                    activeFocusOnTab: true

                    readonly property bool selected: Tr.language === modelData.code

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.m.radiusMd
                        color: parent.selected ? Theme.c.accent
                             : langHover.hovered ? Theme.c.bgHover : "transparent"
                    }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.m.space3
                        anchors.rightMargin: Theme.m.space3
                        Text {
                            Layout.fillWidth: true
                            text: modelData.name
                            color: parent.parent.selected ? Theme.c.onAccent : Theme.c.text
                            font.pixelSize: Theme.m.fontSizeSm + 1
                        }
                        Text {
                            visible: !modelData.complete
                            text: Tr.s["settings.language.partial"] || ""
                            color: parent.parent.selected
                                ? Theme.c.onAccent : Theme.c.textDisabled
                            opacity: 0.8
                            font.pixelSize: Theme.m.fontSizeXs
                        }
                    }
                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.m.radiusMd
                        color: "transparent"
                        border.width: 2
                        border.color: Theme.c.accent
                        visible: parent.activeFocus
                    }
                    HoverHandler { id: langHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: Actions.invoke("app.set_language", { code: modelData.code })
                    }
                }
            }
        }

        // ── tool positions ────────────────────────────────────────
        CardGroup {
            visible: root.tab === "layout"
            title: Tr.s["settings.section.layout"] || ""

            // The canvas belongs to the PROJECT, not to whichever clip is
            // first. Clips shaped differently get bars, which is the honest
            // result rather than a silent reframe - and now a choice.
            SettingRow {
                label: Tr.s["settings.canvas"] || ""
                hint: Tr.s["settings.canvas.hint"] || ""
                Segmented {
                    value: Shell.v.projectCanvas
                    model: [
                        { value: "auto", text: Tr.s["settings.canvas.auto"] || "" },
                        { value: "16:9", text: "16:9" },
                        { value: "9:16", text: "9:16" },
                        { value: "1:1",  text: "1:1" }
                    ]
                    onPicked: function (v) {
                        Actions.invoke("settings.set",
                                       { key: "project.canvas", value: v });
                    }
                }
            }

            SettingRow {
                label: Tr.s["settings.rail_side"] || ""
                hint: Tr.s["settings.rail_side.hint"] || ""
                Segmented {
                    value: Shell.v.railSide
                    model: [
                        { value: "left",  text: Tr.s["settings.side.left"] || "" },
                        { value: "right", text: Tr.s["settings.side.right"] || "" }
                    ]
                    onPicked: function (v) { Actions.invoke("shell.set_rail_side", { side: v }); }
                }
            }

            SettingRow {
                label: Tr.s["settings.transport_position"] || ""
                Segmented {
                    value: Shell.v.transportPosition
                    model: [
                        { value: "center", text: Tr.s["settings.transport.center"] || "" },
                        { value: "bottom", text: Tr.s["settings.transport.bottom"] || "" }
                    ]
                    onPicked: function (v) {
                        Actions.invoke("shell.set_transport_position", { position: v });
                    }
                }
            }

            SettingRow {
                label: Tr.s["settings.readout_corner"] || ""
                Segmented {
                    value: Shell.v.readoutCorner
                    model: [
                        { value: "top_left",     text: Tr.s["settings.corner.top_left"] || "" },
                        { value: "top_right",    text: Tr.s["settings.corner.top_right"] || "" },
                        { value: "bottom_left",  text: Tr.s["settings.corner.bottom_left"] || "" }
                    ]
                    onPicked: function (v) {
                        Actions.invoke("shell.set_readout_corner", { corner: v });
                    }
                }
            }

            SettingRow {
                label: Tr.s["settings.timeline_height"] || ""
                Segmented {
                    value: String(Shell.v.timelineHeight)
                    model: [
                        { value: "180", text: Tr.s["settings.height.low"] || "" },
                        { value: "232", text: Tr.s["settings.height.medium"] || "" },
                        { value: "312", text: Tr.s["settings.height.high"] || "" }
                    ]
                    onPicked: function (v) {
                        Actions.invoke("shell.set_timeline_height", { height: parseInt(v) });
                    }
                }
            }
        }

        // ── floating panel ────────────────────────────────────────
        CardGroup {
            visible: root.tab === "layout"
            title: Tr.s["settings.section.panel"] || ""

            SwitchRow {
                checked: Shell.v.panelAutohide
                label: Tr.s["settings.panel_autohide"] || ""
                onToggled: function (v) {
                    Actions.invoke("shell.set_panel_autohide", { enabled: v });
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: Tr.s["settings.panel_hide_delay"] || ""
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeSm + 1
                }
                Text {
                    text: (Tr.s["common.milliseconds"] || "{value} ms")
                          .replace("{value}", Math.round(delaySlider.effectiveValue))
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeSm
                    font.family: "monospace"
                }
            }
            AppSlider {
                id: delaySlider
                Layout.fillWidth: true
                enabled: Shell.v.panelAutohide
                opacity: enabled ? 1 : 0.45
                label: Tr.s["settings.panel_hide_delay"] || ""
                from: 0
                to: 2000
                stepSize: 100
                value: Shell.v.panelHideDelay
                onCommitted: function (v) {
                    Actions.invoke("shell.set_panel_hide_delay",
                                   { milliseconds: Math.round(v) });
                }
            }
        }

        // ── appearance ────────────────────────────────────────────
        CardGroup {
            visible: root.tab === "appearance"
            title: Tr.s["settings.section.appearance"] || ""

            SettingRow {
                label: Tr.s["settings.theme"] || ""
                Segmented {
                    value: Theme.id
                    model: Theme.available.map(function (t) {
                        return { value: t.id, text: t.name };
                    })
                    onPicked: function (v) { Actions.invoke("app.set_theme", { theme_id: v }); }
                }
            }

            SwitchRow {
                checked: Shell.v.idleBackground
                label: Tr.s["settings.idle_background"] || ""
                onToggled: Actions.invoke("view.toggle_idle_background")
            }

            SwitchRow {
                checked: Shell.v.ambientBackdrop
                label: Tr.s["settings.ambient"] || ""
                onToggled: Actions.invoke("view.toggle_ambient")
            }

            SettingRow {
                label: Tr.s["settings.glass"] || ""
                Segmented {
                    value: Shell.v.glassMode
                    model: [
                        { value: "auto",   text: Tr.s["settings.glass.auto"] || "" },
                        { value: "always", text: Tr.s["settings.glass.always"] || "" },
                        { value: "never",  text: Tr.s["settings.glass.never"] || "" }
                    ]
                    onPicked: function (v) { Actions.invoke("view.set_glass", { mode: v }); }
                }
            }

            // ── transparency ──────────────────────────────────────
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: Theme.m.space2
                enabled: Shell.v.glassActive
                opacity: enabled ? 1 : 0.45
                Text {
                    Layout.fillWidth: true
                    text: Tr.s["settings.glass_opacity"] || ""
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeSm + 1
                }
                Text {
                    text: Math.round((1 - opacitySlider.effectiveValue) * 100) + "%"
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeSm
                    font.family: "monospace"
                }
            }
            AppSlider {
                id: opacitySlider
                Layout.fillWidth: true
                enabled: Shell.v.glassActive
                opacity: enabled ? 1 : 0.45
                label: Tr.s["settings.glass_opacity"] || ""
                // Inverted on purpose: the slider reads as "transparency", so
                // dragging right must make the surface MORE see-through.
                from: 1.0
                to: 0.15
                stepSize: 0.01
                value: Shell.v.glassOpacity
                // Applied while dragging, so the surfaces respond under the
                // pointer instead of only at release.
                onMoved: function (v) {
                    Actions.invoke("view.set_glass_opacity", { opacity: v });
                }
                onCommitted: function (v) {
                    Actions.invoke("view.set_glass_opacity", { opacity: v });
                }
            }
            Text {
                Layout.fillWidth: true
                visible: Shell.v.glassActive
                wrapMode: Text.WordWrap
                text: Shell.v.glassBelowSafe
                    ? (Tr.s["settings.glass_below_safe"] || "")
                    : (Tr.s["settings.transparency_hint"] || "")
                color: Shell.v.glassBelowSafe ? Theme.c.warning : Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            // ── blur ──────────────────────────────────────────────
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: Theme.m.space2
                enabled: Shell.v.glassActive
                opacity: enabled ? 1 : 0.45
                Text {
                    Layout.fillWidth: true
                    text: Tr.s["settings.glass_blur"] || ""
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeSm + 1
                }
                Text {
                    text: Math.round(blurSlider.effectiveValue) + "%"
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeSm
                    font.family: "monospace"
                }
            }
            AppSlider {
                id: blurSlider
                Layout.fillWidth: true
                enabled: Shell.v.glassActive
                opacity: enabled ? 1 : 0.45
                label: Tr.s["settings.glass_blur"] || ""
                from: 0
                to: 100
                stepSize: 5
                value: Shell.v.glassBlur
                onMoved: function (v) {
                    Actions.invoke("view.set_glass_blur", { radius: Math.round(v) });
                }
                onCommitted: function (v) {
                    Actions.invoke("view.set_glass_blur", { radius: Math.round(v) });
                }
            }

            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: resetLabel.implicitHeight + Theme.m.space2
                visible: Shell.v.glassActive
                Text {
                    id: resetLabel
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: Tr.s["settings.glass_reset"] || ""
                    color: resetHover.hovered ? Theme.c.accent : Theme.c.textDisabled
                    font.pixelSize: Theme.m.fontSizeXs
                    font.underline: resetHover.hovered
                }
                HoverHandler { id: resetHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: Actions.invoke("view.reset_glass") }
            }

            Text {
                Layout.fillWidth: true
                Layout.topMargin: Theme.m.space2
                wrapMode: Text.WordWrap
                text: Shell.v.glassSupported
                    ? (Tr.s["settings.glass.supported"] || "")
                    : (Tr.s["settings.glass.unsupported"] || "")
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            SwitchRow {
                checked: Shell.v.reduceTransparency
                label: Tr.s["settings.reduce_transparency"] || ""
                onToggled: function (v) {
                    Actions.invoke("settings.set",
                                   { key: "appearance.reduce_transparency",
                                     value: v ? "true" : "false" });
                }
            }

            SwitchRow {
                checked: Shell.v.reduceMotion
                label: Tr.s["settings.reduce_motion"] || ""
                onToggled: function (v) {
                    Actions.invoke("settings.set",
                                   { key: "appearance.reduce_motion",
                                     value: v ? "true" : "false" });
                }
            }
        }
    }
}
