// Content packs, in two tabs (the chosen "Option A" layout).
//
//   CREA        details (name, author, description), the contents as
//               expandable category checklists with counters, the
//               favourites shortcut, and the export button.
//   INSTALLATI  the installed packs as removable units - who made
//               them, what they carry, one trash to take it all out -
//               plus "install from file".
//
// The pack format is a ZIP renamed .ivepack, data only, never code
// (docs/CONTENT_PACKS.md). Installing also works by dropping the file
// anywhere on the window; both paths meet in the confirmation card
// (PackInstallOverlay.qml).
import QtQuick
import QtQuick.Dialogs
import QtQuick.Layouts
import components
import IVE

Item {
    id: root

    implicitHeight: column.implicitHeight + Theme.m.space3 * 2

    property string tab: "create"
    /*! The category checklist currently expanded, "" for none. */
    property string open: ""
    /*! Selected ids per category. Reassigned (never mutated) so every
        binding re-evaluates. */
    property var picked: ({ colors: [], transitions: [], stickers: [],
                            motion: [], export_presets: [],
                            audio_effects: [] })
    property string status: ""

    readonly property int pickedCount:
        picked.colors.length + picked.transitions.length
        + picked.stickers.length + picked.motion.length
        + picked.export_presets.length + picked.audio_effects.length

    function isPicked(category, id) {
        return picked[category].indexOf(id) >= 0;
    }
    function toggle(category, id) {
        var next = { colors: picked.colors.slice(),
                     transitions: picked.transitions.slice(),
                     stickers: picked.stickers.slice(),
                     motion: picked.motion.slice(),
                     export_presets: picked.export_presets.slice(),
                     audio_effects: picked.audio_effects.slice() };
        var at = next[category].indexOf(id);
        if (at >= 0)
            next[category].splice(at, 1);
        else
            next[category].push(id);
        picked = next;
        status = "";
    }
    /*! The favourites of all three catalogues become the selection. */
    function addFavorites() {
        function union(base, extra) {
            var out = base.slice();
            for (var i = 0; i < extra.length; i++)
                if (out.indexOf(extra[i]) < 0)
                    out.push(extra[i]);
            return out;
        }
        picked = {
            colors: union(picked.colors, ColorFx.favorites),
            transitions: union(picked.transitions, Transitions.favorites),
            stickers: union(picked.stickers, Stickers.favorites),
            motion: picked.motion,
            export_presets: picked.export_presets,
            audio_effects: union(picked.audio_effects, AudioFx.favorites)
        };
    }

    // Flat item lists per category, section names included.
    readonly property var colorItems: {
        var out = [];
        var all = ColorFx.effects;
        for (var i = 0; i < all.length; i++)
            out.push({ id: all[i].id, name: all[i].name,
                       section: all[i].section });
        return out;
    }
    readonly property var transitionItems: {
        var out = [];
        var sections = Transitions.sections;
        for (var s = 0; s < sections.length; s++) {
            var inside = Transitions.transitions(sections[s].id);
            for (var i = 0; i < inside.length; i++)
                out.push({ id: inside[i].id, name: inside[i].name,
                           section: sections[s].id });
        }
        return out;
    }
    readonly property var stickerItems: {
        var out = [];
        var kinds = ["static", "animated"];
        for (var k = 0; k < kinds.length; k++) {
            var sections = kinds[k] === "static"
                ? Stickers.staticSections : Stickers.animatedSections;
            for (var s = 0; s < sections.length; s++) {
                var inside = Stickers.stickers(kinds[k], sections[s].id);
                for (var i = 0; i < inside.length; i++)
                    out.push({ id: inside[i].id, name: inside[i].name,
                               section: sections[s].id });
            }
        }
        return out;
    }

    readonly property var motionItems: {
        var out = [];
        var all = Motion.presets;
        for (var i = 0; i < all.length; i++)
            out.push({ id: all[i].id, name: all[i].name,
                       section: Tr.s["motion.kind." + all[i].kind]
                                || all[i].kind });
        return out;
    }

    readonly property var exportItems: {
        var out = [];
        var all = Export.presets;
        var platforms = Export.platforms;
        for (var i = 0; i < all.length; i++) {
            var label = all[i].platform;
            for (var k = 0; k < platforms.length; k++)
                if (platforms[k].id === all[i].platform)
                    label = platforms[k].label;
            out.push({ id: all[i].id, name: all[i].label, section: label });
        }
        return out;
    }

    readonly property var audioItems: {
        var out = [];
        var all = AudioFx.effects;
        for (var i = 0; i < all.length; i++)
            out.push({ id: all[i].id, name: all[i].name,
                       section: Tr.s["audio.section." + all[i].section]
                                || all[i].section });
        return out;
    }

    readonly property var categories: [
        { key: "colors", label: Tr.s["pack.cat.colors"] || "",
          items: colorItems },
        { key: "transitions", label: Tr.s["pack.cat.transitions"] || "",
          items: transitionItems },
        { key: "stickers", label: Tr.s["pack.cat.stickers"] || "",
          items: stickerItems },
        { key: "motion", label: Tr.s["pack.cat.motion"] || "",
          items: motionItems },
        { key: "export_presets", label: Tr.s["pack.cat.export_presets"] || "",
          items: exportItems },
        { key: "audio_effects", label: Tr.s["pack.cat.audio_effects"] || "",
          items: audioItems }
    ]

    Connections {
        target: Packs
        function onCreated(path) {
            root.status = (Tr.s["pack.saved"] || "{p}")
                .replace("{p}", path);
        }
        function onError(message) {
            root.status = (Tr.s["pack.error"] || "{e}")
                .replace("{e}", message);
        }
    }

    FileDialog {
        id: saveDialog
        title: Tr.s["pack.export"] || ""
        fileMode: FileDialog.SaveFile
        defaultSuffix: "ivepack"
        nameFilters: [(Tr.s["pack.filter"] || "Pack") + " (*.ivepack)"]
        onAccepted: Actions.invoke("pack.create", {
            name: nameField.text,
            author: authorField.text,
            description: descriptionField.text,
            color_ids: root.picked.colors,
            transition_ids: root.picked.transitions,
            sticker_ids: root.picked.stickers,
            motion_ids: root.picked.motion,
            export_preset_ids: root.picked.export_presets,
            audio_effect_ids: root.picked.audio_effects,
            path: String(selectedFile)
        })
    }
    FileDialog {
        id: openDialog
        title: Tr.s["pack.install_file"] || ""
        nameFilters: [(Tr.s["pack.filter"] || "Pack") + " (*.ivepack)"]
        onAccepted: Actions.invoke("pack.install",
                                   { path: String(selectedFile) })
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
                { value: "installed", text: Tr.s["pack.tab.installed"] || "" },
                { value: "create", text: Tr.s["pack.tab.create"] || "" }
            ]
            onPicked: function (v) { root.tab = v; }
        }

        // ═══ CREA ═══════════════════════════════════════════════════
        CardGroup {
            visible: root.tab === "create"
            title: Tr.s["pack.details"] || ""

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.m.controlHeight
                radius: Theme.m.radiusMd
                color: Qt.alpha(Theme.c.glassOn, 0.07)
                border.width: 1
                border.color: nameField.activeFocus ? Theme.c.accent
                                                    : Theme.c.border
                TextInput {
                    id: nameField
                    objectName: "pack_name_field"
                    anchors.fill: parent
                    anchors.leftMargin: Theme.m.space2
                    anchors.rightMargin: Theme.m.space2
                    verticalAlignment: TextInput.AlignVCenter
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeSm + 1
                    selectByMouse: true
                    selectionColor: Theme.c.accent
                    Text {
                        anchors.fill: parent
                        verticalAlignment: Text.AlignVCenter
                        visible: nameField.text === ""
                        text: Tr.s["pack.name_hint"] || ""
                        color: Theme.c.textDisabled
                        font.pixelSize: Theme.m.fontSizeSm + 1
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.m.controlHeight
                radius: Theme.m.radiusMd
                color: Qt.alpha(Theme.c.glassOn, 0.07)
                border.width: 1
                border.color: authorField.activeFocus ? Theme.c.accent
                                                      : Theme.c.border
                TextInput {
                    id: authorField
                    anchors.fill: parent
                    anchors.leftMargin: Theme.m.space2
                    anchors.rightMargin: Theme.m.space2
                    verticalAlignment: TextInput.AlignVCenter
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeSm + 1
                    selectByMouse: true
                    selectionColor: Theme.c.accent
                    Text {
                        anchors.fill: parent
                        verticalAlignment: Text.AlignVCenter
                        visible: authorField.text === ""
                        text: Tr.s["pack.author_hint"] || ""
                        color: Theme.c.textDisabled
                        font.pixelSize: Theme.m.fontSizeSm + 1
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.m.controlHeight
                radius: Theme.m.radiusMd
                color: Qt.alpha(Theme.c.glassOn, 0.07)
                border.width: 1
                border.color: descriptionField.activeFocus ? Theme.c.accent
                                                           : Theme.c.border
                TextInput {
                    id: descriptionField
                    anchors.fill: parent
                    anchors.leftMargin: Theme.m.space2
                    anchors.rightMargin: Theme.m.space2
                    verticalAlignment: TextInput.AlignVCenter
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeSm + 1
                    selectByMouse: true
                    selectionColor: Theme.c.accent
                    Text {
                        anchors.fill: parent
                        verticalAlignment: Text.AlignVCenter
                        visible: descriptionField.text === ""
                        text: Tr.s["pack.description_hint"] || ""
                        color: Theme.c.textDisabled
                        font.pixelSize: Theme.m.fontSizeSm + 1
                    }
                }
            }
        }

        CardGroup {
            visible: root.tab === "create"
            title: Tr.s["pack.contents"] || ""

            // The favourites shortcut: the natural starting selection.
            Rectangle {
                objectName: "pack_favorites_chip"
                Layout.alignment: Qt.AlignLeft
                width: favRow.implicitWidth + Theme.m.space3 * 2
                height: 28
                radius: 999
                color: Qt.alpha("#FFC53D", 0.14)
                border.width: 1
                border.color: Qt.alpha("#FFC53D", 0.35)
                Row {
                    id: favRow
                    anchors.centerIn: parent
                    spacing: 6
                    Glyph {
                        width: 12; height: 12
                        anchors.verticalCenter: parent.verticalCenter
                        path: "M12 2.6l2.8 5.9 6.4.8-4.7 4.4 1.2 6.3-5.7-3.1-5.7 3.1 1.2-6.3-4.7-4.4 6.4-.8z"
                        color: "#FFC53D"
                        weight: 2
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: Tr.s["pack.add_favorites"] || ""
                        color: "#FFC53D"
                        font.pixelSize: Theme.m.fontSizeXs
                        font.bold: true
                    }
                }
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: root.addFavorites() }
            }

            // One expandable checklist per category.
            Repeater {
                model: root.categories
                delegate: ColumnLayout {
                    id: category
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 0

                    Rectangle {
                        objectName: "pack_cat_" + category.modelData.key
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        radius: Theme.m.radiusMd
                        color: catHover.hovered ? Theme.c.bgHover
                                                : Qt.alpha(Theme.c.glassOn, 0.05)
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: Theme.m.space3
                            anchors.rightMargin: Theme.m.space2
                            spacing: Theme.m.space2
                            Text {
                                Layout.fillWidth: true
                                text: category.modelData.label
                                color: Theme.c.text
                                font.pixelSize: Theme.m.fontSizeSm + 1
                            }
                            Rectangle {
                                width: countText.implicitWidth + 16
                                height: 20
                                radius: 999
                                color: root.picked[category.modelData.key].length > 0
                                    ? Qt.alpha(Theme.c.accent, 0.14)
                                    : Qt.alpha(Theme.c.glassOn, 0.06)
                                Text {
                                    id: countText
                                    anchors.centerIn: parent
                                    text: (Tr.s["pack.count"] || "{n} / {t}")
                                        .replace("{n}", root.picked[category.modelData.key].length)
                                        .replace("{t}", category.modelData.items.length)
                                    color: root.picked[category.modelData.key].length > 0
                                        ? Theme.c.accent : Theme.c.textDisabled
                                    font.pixelSize: Theme.m.fontSizeXs
                                    font.bold: true
                                }
                            }
                            Glyph {
                                width: 14; height: 14
                                rotation: root.open === category.modelData.key
                                    ? 180 : 0
                                path: Icons.chevronDown
                                color: Theme.c.textDisabled
                            }
                        }
                        HoverHandler { id: catHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler {
                            onTapped: root.open =
                                root.open === category.modelData.key
                                    ? "" : category.modelData.key
                        }
                    }

                    ColumnLayout {
                        visible: root.open === category.modelData.key
                        Layout.fillWidth: true
                        Layout.leftMargin: Theme.m.space2
                        Layout.topMargin: 2
                        spacing: 0

                        Repeater {
                            model: category.modelData.items
                            delegate: Item {
                                id: row
                                required property var modelData
                                objectName: "pack_item_" + modelData.id
                                Layout.fillWidth: true
                                Layout.preferredHeight: 26

                                readonly property bool checked:
                                    root.isPicked(category.modelData.key,
                                                  modelData.id)

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: Theme.m.space2
                                    anchors.rightMargin: Theme.m.space2
                                    spacing: Theme.m.space2
                                    Rectangle {
                                        width: 15; height: 15
                                        radius: 4
                                        color: row.checked ? Theme.c.accent
                                                           : "transparent"
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
                                        color: row.checked ? Theme.c.text
                                                           : Theme.c.textMuted
                                        font.pixelSize: Theme.m.fontSizeSm
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        text: row.modelData.section
                                        color: Theme.c.textDisabled
                                        font.pixelSize: Theme.m.fontSizeXs
                                    }
                                }
                                HoverHandler { cursorShape: Qt.PointingHandCursor }
                                TapHandler {
                                    onTapped: root.toggle(
                                        category.modelData.key,
                                        row.modelData.id)
                                }
                            }
                        }
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["pack.contents_hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }
        }

        Rectangle {
            objectName: "pack_export_button"
            visible: root.tab === "create"
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            radius: Theme.m.radiusLg
            color: enabled ? (exportHover.hovered
                              ? Theme.c.accentHover : Theme.c.accent)
                           : Qt.alpha(Theme.c.accent, 0.35)
            enabled: nameField.text.trim() !== "" && root.pickedCount > 0
            Row {
                anchors.centerIn: parent
                spacing: 8
                Glyph {
                    width: 16; height: 16
                    anchors.verticalCenter: parent.verticalCenter
                    path: Icons.exportIcon
                    color: Theme.c.onAccent
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: (Tr.s["pack.export"] || "") +
                          (root.pickedCount > 0
                           ? "  ·  " + root.pickedCount : "")
                    color: Theme.c.onAccent
                    font.pixelSize: Theme.m.fontSizeMd
                    font.bold: true
                }
            }
            HoverHandler { id: exportHover; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: if (parent.enabled) saveDialog.open() }
        }

        Text {
            visible: root.tab === "create" && root.status !== ""
            Layout.fillWidth: true
            wrapMode: Text.WrapAnywhere
            text: root.status
            color: Theme.c.textMuted
            font.pixelSize: Theme.m.fontSizeXs
        }

        // ═══ INSTALLATI ═════════════════════════════════════════════
        CardGroup {
            visible: root.tab === "installed"
            title: Tr.s["pack.installed"] || ""

            Text {
                visible: Packs.installed.length === 0
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["pack.none_installed"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            Repeater {
                model: Packs.installed
                delegate: Rectangle {
                    id: packRow
                    required property var modelData
                    objectName: "pack_row_" + modelData.id
                    Layout.fillWidth: true
                    Layout.preferredHeight: 56
                    radius: Theme.m.radiusLg
                    color: Qt.alpha(Theme.c.glassOn, 0.05)

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.m.space3
                        anchors.rightMargin: Theme.m.space2
                        spacing: Theme.m.space3
                        Rectangle {
                            width: 34; height: 34
                            radius: Theme.m.radiusLg
                            gradient: Gradient {
                                GradientStop { position: 0; color: "#2C4A8F" }
                                GradientStop { position: 1; color: "#E8964A" }
                            }
                            Glyph {
                                anchors.centerIn: parent
                                width: 17; height: 17
                                path: Icons.pack
                                color: "#FFFFFF"
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                Layout.fillWidth: true
                                text: packRow.modelData.name
                                color: Theme.c.text
                                font.pixelSize: Theme.m.fontSizeSm + 1
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                text: (packRow.modelData.author !== ""
                                       ? (Tr.s["pack.by"] || "{a}")
                                             .replace("{a}",
                                                      packRow.modelData.author)
                                         + " — " : "")
                                      + (Tr.s["pack.summary"] || "")
                                            .replace("{c}", packRow.modelData.colors)
                                            .replace("{t}", packRow.modelData.transitions)
                                            .replace("{s}", packRow.modelData.stickers)
                                            .replace("{m}", packRow.modelData.motion)
                                            .replace("{e}", packRow.modelData.exportPresets)
                                            .replace("{a}", packRow.modelData.audioEffects)
                                color: Theme.c.textDisabled
                                font.pixelSize: Theme.m.fontSizeXs
                                elide: Text.ElideRight
                            }
                        }
                        IconButton {
                            objectName: "pack_remove_" + packRow.modelData.id
                            size: 26; iconSize: 15
                            icon: Icons.trash
                            label: Tr.s["pack.remove"] || ""
                            onTriggered: Actions.invoke("pack.remove",
                                { pack_id: packRow.modelData.id })
                        }
                    }
                }
            }
        }

        Rectangle {
            visible: root.tab === "installed"
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            radius: Theme.m.radiusLg
            color: "transparent"
            border.width: 1
            border.color: Theme.c.borderStrong
            Row {
                anchors.centerIn: parent
                spacing: 8
                Glyph {
                    width: 15; height: 15
                    anchors.verticalCenter: parent.verticalCenter
                    path: Icons.plus
                    color: Theme.c.textMuted
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: Tr.s["pack.install_file"] || ""
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeSm + 1
                }
            }
            HoverHandler { cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: openDialog.open() }
        }
        Text {
            visible: root.tab === "installed"
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: Tr.s["pack.drop_hint"] || ""
            color: Theme.c.textDisabled
            font.pixelSize: Theme.m.fontSizeXs
        }
    }
}
