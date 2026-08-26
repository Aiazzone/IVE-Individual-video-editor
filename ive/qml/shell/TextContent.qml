// Text and titles.
//
// One button adds a title at the playhead; everything else edits the
// SELECTED title - the selection shared through Shell.v.selectedClipId,
// so tapping a title on the video or on the timeline opens its words
// here. Position, size and rotation are NOT in this panel on purpose:
// they belong to the on-video handles (StickerHandles.qml), where the
// eye is.
//
// Editing is two-phased like the handles: while typing, the live span
// restyles the paused frame (Playback.set_text_live - no undo entries);
// leaving the field commits ONE timeline.set_clip_text. Style buttons
// (colour, outline, bold, italic, font) commit immediately - each is a
// deliberate choice, so each is its own undo step.
import QtQuick
import QtQuick.Dialogs
import QtQuick.Layouts
import components
import IVE

Item {
    id: root

    implicitHeight: column.implicitHeight + Theme.m.space3 * 2

    /*! "" = the editor; "font" = the font list sub-page. */
    property string view: ""

    /*! The selected TEXT clip, or null - live from the project. */
    readonly property var textClip: {
        var id = Shell.v.selectedClipId || "";
        if (id === "")
            return null;
        var clips = Project.timelineClips;
        for (var i = 0; i < clips.length; i++)
            if (clips[i].id === id && clips[i].text)
                return clips[i];
        return null;
    }

    // Re-seed the words field when the selection (or an undo) changes it
    // under us - but never while the user is typing in it.
    onTextClipChanged: {
        if (textClip === null) {
            root.view = "";
            return;
        }
        if (!wordsField.activeFocus && wordsField.text !== textClip.text)
            wordsField.text = textClip.text;
    }

    /*! One commit = one undo step; `over` carries the changed piece. */
    function commitStyle(over) {
        if (textClip === null)
            return;
        Actions.invoke("timeline.set_clip_text", {
            clip_id: textClip.id,
            text: wordsField.text.trim() !== "" ? wordsField.text
                                                : textClip.text,
            font: over.font !== undefined ? over.font : textClip.font,
            color: over.color !== undefined ? over.color : textClip.color,
            outline: over.outline !== undefined ? over.outline
                                                : textClip.outline,
            bold: over.bold !== undefined ? over.bold : textClip.bold,
            italic: over.italic !== undefined ? over.italic : textClip.italic
        });
    }

    function pushLive() {
        if (textClip === null || wordsField.text.trim() === "")
            return;
        Playback.set_text_live(textClip.id, wordsField.text, textClip.font,
                               textClip.color, textClip.outline,
                               textClip.bold, textClip.italic);
    }

    readonly property var swatches: [
        "#FFFFFF", "#111111", "#FFD467", "#E5484D",
        "#46A758", "#3E63DD", "#D6408B"
    ]

    ColumnLayout {
        id: column
        anchors { left: parent.left; right: parent.right; top: parent.top
                  margins: Theme.m.space3 }
        spacing: Theme.m.space3

        // ── add ───────────────────────────────────────────────────
        CardGroup {
            visible: root.view === ""
            title: Tr.s["text.add_group"] || ""

            Rectangle {
                objectName: "text_add_button"
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.m.controlHeight + 6
                radius: Theme.m.radiusMd
                color: addHover.hovered ? Qt.lighter(Theme.c.accent, 1.1)
                                        : Theme.c.accent
                opacity: Project.isOpen ? 1 : 0.4

                Text {
                    anchors.centerIn: parent
                    text: Tr.s["text.add"] || ""
                    color: "#FFFFFF"
                    font.pixelSize: Theme.m.fontSizeSm + 2
                    font.bold: true
                }
                HoverHandler { id: addHover; cursorShape: Qt.PointingHandCursor }
                TapHandler {
                    enabled: Project.isOpen
                    onTapped: {
                        var at = Playback.hasMedia
                            ? Playback.positionSeconds : 0;
                        Actions.invoke("timeline.place_text", {
                            text: Tr.s["text.default"] || "Title",
                            at: at, duration: 3.0
                        });
                        // Select what was just placed, so the editor below
                        // (and the on-video handles) pick it up at once.
                        var clips = Project.timelineClips;
                        for (var i = clips.length - 1; i >= 0; i--)
                            if (clips[i].text
                                    && Math.abs(clips[i].start - at) < 0.01) {
                                Shell.set_selected_clip(clips[i].id, "text");
                                break;
                            }
                    }
                }
            }

            Text {
                visible: root.textClip === null
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["text.hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }
        }

        // ── edit the selected title ───────────────────────────────
        CardGroup {
            visible: root.view === "" && root.textClip !== null
            title: Tr.s["text.edit_group"] || ""

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 76
                radius: Theme.m.radiusMd
                color: Qt.alpha(Theme.c.glassOn, 0.07)
                border.width: 1
                border.color: wordsField.activeFocus ? Theme.c.accent
                                                     : Theme.c.border

                Flickable {
                    anchors.fill: parent
                    anchors.margins: Theme.m.space2
                    contentHeight: wordsField.implicitHeight
                    clip: true

                    TextEdit {
                        id: wordsField
                        objectName: "text_words_field"
                        width: parent.width
                        color: Theme.c.text
                        font.pixelSize: Theme.m.fontSizeSm + 1
                        selectByMouse: true
                        selectionColor: Theme.c.accent
                        wrapMode: TextEdit.Wrap
                        onTextChanged: {
                            if (activeFocus)
                                root.pushLive();
                        }
                        onActiveFocusChanged: {
                            if (activeFocus || root.textClip === null)
                                return;
                            if (text.trim() === "") {
                                // Empty words cannot be committed (they
                                // would erase the clip's identity); put
                                // the real ones back.
                                text = root.textClip.text;
                                return;
                            }
                            if (text !== root.textClip.text)
                                root.commitStyle({});
                        }
                    }
                }
            }

            // Karaoke: only a clip that carries word timestamps (the
            // generated subtitles do) can light its words up in time.
            SwitchRow {
                objectName: "text_karaoke_switch"
                visible: root.textClip !== null
                         && root.textClip.words !== undefined
                         && root.textClip.words.length > 0
                Layout.fillWidth: true
                label: Tr.s["subtitles.karaoke"] || ""
                checked: root.textClip !== null
                         && root.textClip.karaoke === true
                onToggled: function (v) {
                    if (root.textClip !== null)
                        Actions.invoke("timeline.set_clip_karaoke", {
                            clip_id: root.textClip.id, enabled: v
                        });
                }
            }

            // bold / italic / colour swatches
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.m.space2

                Rectangle {
                    objectName: "text_bold_toggle"
                    width: 30; height: 30
                    radius: Theme.m.radiusSm
                    color: root.textClip !== null && root.textClip.bold
                        ? Theme.c.accent : Qt.alpha(Theme.c.glassOn, 0.08)
                    Text {
                        anchors.centerIn: parent
                        text: "B"
                        font.bold: true
                        color: root.textClip !== null && root.textClip.bold
                            ? "#FFFFFF" : Theme.c.text
                    }
                    TapHandler {
                        onTapped: root.commitStyle(
                            { bold: !(root.textClip && root.textClip.bold) })
                    }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                }
                Rectangle {
                    objectName: "text_italic_toggle"
                    width: 30; height: 30
                    radius: Theme.m.radiusSm
                    color: root.textClip !== null && root.textClip.italic
                        ? Theme.c.accent : Qt.alpha(Theme.c.glassOn, 0.08)
                    Text {
                        anchors.centerIn: parent
                        text: "I"
                        font.italic: true
                        color: root.textClip !== null && root.textClip.italic
                            ? "#FFFFFF" : Theme.c.text
                    }
                    TapHandler {
                        onTapped: root.commitStyle(
                            { italic: !(root.textClip
                                        && root.textClip.italic) })
                    }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                }

                Item { Layout.preferredWidth: Theme.m.space1 }

                Repeater {
                    model: root.swatches
                    delegate: Rectangle {
                        required property var modelData
                        objectName: "text_color_" + modelData
                        width: 22; height: 22
                        radius: 11
                        color: modelData
                        border.width: root.textClip !== null
                            && root.textClip.color.toUpperCase()
                               === modelData.toUpperCase() ? 2 : 1
                        border.color: root.textClip !== null
                            && root.textClip.color.toUpperCase()
                               === modelData.toUpperCase()
                            ? Theme.c.accent : Qt.alpha(Theme.c.glassOn, 0.3)
                        TapHandler {
                            onTapped: root.commitStyle({ color: modelData })
                        }
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                    }
                }
            }

            // outline: none / black / white
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.m.space2

                Text {
                    text: Tr.s["text.outline"] || ""
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeSm
                }
                Segmented {
                    Layout.fillWidth: true
                    value: root.textClip === null ? ""
                        : (root.textClip.outline === "" ? "none"
                           : (root.textClip.outline.toUpperCase() === "#FFFFFF"
                              ? "white" : "black"))
                    model: [
                        { value: "none", text: Tr.s["text.outline_none"] || "" },
                        { value: "black", text: Tr.s["text.outline_black"] || "" },
                        { value: "white", text: Tr.s["text.outline_white"] || "" }
                    ]
                    onPicked: function (v) {
                        root.commitStyle({ outline:
                            v === "none" ? "" :
                            v === "white" ? "#FFFFFF" : "#000000" });
                    }
                }
            }

            // the font, as a sub-page with every family in its own face
            Rectangle {
                objectName: "text_font_row"
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                radius: Theme.m.radiusMd
                color: fontHover.hovered ? Theme.c.bgHover
                                         : Qt.alpha(Theme.c.glassOn, 0.05)
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.m.space3
                    anchors.rightMargin: Theme.m.space2
                    Text {
                        Layout.fillWidth: true
                        text: root.textClip !== null && root.textClip.font !== ""
                            ? root.textClip.font
                            : (Tr.s["text.font_default"] || "")
                        color: Theme.c.text
                        font.family: root.textClip !== null
                                     && root.textClip.font !== ""
                            ? root.textClip.font : Theme.m.fontFamily || ""
                        font.pixelSize: Theme.m.fontSizeSm + 1
                        elide: Text.ElideRight
                    }
                    Glyph {
                        width: 15; height: 15
                        rotation: -90
                        path: Icons.chevronDown
                        color: Theme.c.textDisabled
                    }
                }
                HoverHandler { id: fontHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: root.view = "font" }
            }

            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["text.handles_hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }
        }

        // ── the selected title's animation ────────────────────────
        // Same cards as the Stickers panel: every one previews THESE
        // words, in THIS style, moved by THAT preset.
        CardGroup {
            visible: root.view === "" && root.textClip !== null
            title: Tr.s["motion.section"] || ""

            MotionPicker {
                Layout.fillWidth: true
                clip: root.textClip
                subjectKey: root.textClip !== null
                    ? [root.textClip.text, root.textClip.font,
                       root.textClip.color, root.textClip.outline,
                       root.textClip.bold, root.textClip.italic].join("|")
                    : ""
                presets: Motion.presets
                still: root.textClip !== null
                    ? Motion.text_still_url(root.textClip.text,
                                            root.textClip.font,
                                            root.textClip.color,
                                            root.textClip.outline,
                                            root.textClip.bold,
                                            root.textClip.italic) : ""
                stripFor: function (presetId) {
                    var c = root.textClip;
                    return c === null ? null
                        : Motion.text_strip(c.text, c.font, c.color,
                                            c.outline, c.bold, c.italic,
                                            presetId);
                }
            }

            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["text.motion_hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }
        }

        // ── automatic subtitles ───────────────────────────────────
        // The speech in the cut's A/V clips becomes editable titles on
        // the Text lane - one undo step, every line correctable here
        // like any other title. The model is a state: missing means an
        // invitation to download (size and licence on show), never an
        // error. Work runs elsewhere; this card only watches.
        CardGroup {
            visible: root.view === ""
            title: Tr.s["subtitles.group"] || ""

            Text {
                visible: Subtitles.state === "backend_missing"
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["subtitles.backend_missing"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            // What would be (or was) downloaded: name, size, licence.
            Text {
                visible: Subtitles.state !== "backend_missing"
                Layout.fillWidth: true
                text: Subtitles.modelName + " · " + Subtitles.modelSizeMb
                      + " MB · " + Subtitles.modelLicense
                color: Theme.c.textMuted
                font.pixelSize: Theme.m.fontSizeXs
                elide: Text.ElideRight
            }

            Rectangle {
                objectName: "subtitles_download_button"
                visible: Subtitles.state === "model_missing"
                         && !Subtitles.downloading
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.m.controlHeight
                radius: Theme.m.radiusMd
                color: dlHover.hovered ? Theme.c.bgHover
                                       : Qt.alpha(Theme.c.glassOn, 0.08)
                border.width: 1
                border.color: Theme.c.border
                Text {
                    anchors.centerIn: parent
                    text: (Tr.s["subtitles.download"] || "")
                          + " (" + Subtitles.modelSizeMb + " MB)"
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeSm
                }
                HoverHandler { id: dlHover
                               cursorShape: Qt.PointingHandCursor }
                TapHandler {
                    onTapped: Actions.invoke("subtitles.download_model", {})
                }
            }

            RowLayout {
                visible: Subtitles.downloading
                Layout.fillWidth: true
                spacing: Theme.m.space2
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        text: Tr.s["subtitles.downloading"] || ""
                        color: Theme.c.textMuted
                        font.pixelSize: Theme.m.fontSizeXs
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 3
                        radius: 1.5
                        color: Qt.alpha(Theme.c.glassOn, 0.10)
                        Rectangle {
                            width: parent.width * Subtitles.downloadProgress
                            height: parent.height
                            radius: 1.5
                            color: Theme.c.accent
                        }
                    }
                }
                IconButton {
                    objectName: "subtitles_download_cancel"
                    size: 24; iconSize: 12
                    icon: Icons.close
                    label: Tr.s["export.cancel"] || ""
                    onTriggered: Subtitles.cancel_download()
                }
            }

            // The spoken language: auto-detect by default, a chip pins
            // it when the detection guesses wrong on short clips.
            Flow {
                visible: Subtitles.state === "ready"
                Layout.fillWidth: true
                spacing: Theme.m.space1

                Repeater {
                    model: [{ code: "", label: Tr.s["subtitles.lang.auto"]
                                            || "Auto" },
                            { code: "it", label: "IT" },
                            { code: "en", label: "EN" },
                            { code: "pt", label: "PT" },
                            { code: "es", label: "ES" },
                            { code: "fr", label: "FR" },
                            { code: "de", label: "DE" }]
                    delegate: Rectangle {
                        id: langChip
                        required property var modelData
                        objectName: "subtitles_lang_"
                                    + (modelData.code || "auto")
                        readonly property bool current:
                            Subtitles.language === modelData.code
                        width: langText.implicitWidth + Theme.m.space3 * 2
                        height: 24
                        radius: 999
                        color: current ? Qt.alpha(Theme.c.accent, 0.2)
                             : Qt.alpha(Theme.c.glassOn, 0.06)
                        border.width: 1
                        border.color: current ? Theme.c.accent
                                              : Qt.alpha(Theme.c.glassOn, 0.12)
                        Text {
                            id: langText
                            anchors.centerIn: parent
                            text: langChip.modelData.label
                            color: langChip.current ? Theme.c.text
                                                    : Theme.c.textMuted
                            font.pixelSize: Theme.m.fontSizeXs
                            font.bold: langChip.current
                        }
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        TapHandler {
                            onTapped: Actions.invoke(
                                "subtitles.set_language",
                                { language: langChip.modelData.code })
                        }
                    }
                }
            }

            Rectangle {
                objectName: "subtitles_generate_button"
                visible: Subtitles.state === "ready" && !Subtitles.running
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.m.controlHeight + 6
                radius: Theme.m.radiusMd
                color: genHover.hovered ? Qt.lighter(Theme.c.accent, 1.1)
                                        : Theme.c.accent
                opacity: Project.isOpen ? 1 : 0.4
                Text {
                    anchors.centerIn: parent
                    text: Tr.s["subtitles.generate"] || ""
                    color: "#FFFFFF"
                    font.pixelSize: Theme.m.fontSizeSm + 2
                    font.bold: true
                }
                HoverHandler { id: genHover
                               cursorShape: Qt.PointingHandCursor }
                TapHandler {
                    enabled: Project.isOpen
                    onTapped: Actions.invoke("timeline.auto_subtitles", {})
                }
            }

            RowLayout {
                visible: Subtitles.running
                Layout.fillWidth: true
                spacing: Theme.m.space2
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        objectName: "subtitles_progress_label"
                        text: (Tr.s["subtitles.running"] || "") + " "
                              + Math.round(Subtitles.progress * 100) + "%"
                        color: Theme.c.textMuted
                        font.pixelSize: Theme.m.fontSizeXs
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 3
                        radius: 1.5
                        color: Qt.alpha(Theme.c.glassOn, 0.10)
                        Rectangle {
                            width: parent.width * Subtitles.progress
                            height: parent.height
                            radius: 1.5
                            color: Theme.c.accent
                        }
                    }
                }
                IconButton {
                    objectName: "subtitles_cancel"
                    size: 24; iconSize: 12
                    icon: Icons.close
                    label: Tr.s["export.cancel"] || ""
                    onTriggered: Actions.invoke("subtitles.cancel", {})
                }
            }

            // ── translation ───────────────────────────────────
            // The Text lane into another language: timings stay,
            // one undo brings the original back. The pairs are
            // models like the speech one - explicit downloads.
            RowLayout {
                visible: Subtitles.state !== "backend_missing"
                Layout.fillWidth: true
                spacing: Theme.m.space2
                Text {
                    text: Tr.s["subtitles.translate_to"] || ""
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeXs
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: Theme.m.space1
                    Repeater {
                        model: ["en", "it", "pt", "es"]
                        delegate: Rectangle {
                            id: targetChip
                            required property var modelData
                            objectName: "subtitles_target_" + modelData
                            readonly property bool current:
                                Subtitles.translateTarget === modelData
                            width: targetText.implicitWidth
                                   + Theme.m.space3 * 2
                            height: 24
                            radius: 999
                            color: current ? Qt.alpha(Theme.c.accent, 0.2)
                                 : Qt.alpha(Theme.c.glassOn, 0.06)
                            border.width: 1
                            border.color: current ? Theme.c.accent
                                : Qt.alpha(Theme.c.glassOn, 0.12)
                            Text {
                                id: targetText
                                anchors.centerIn: parent
                                text: targetChip.modelData.toUpperCase()
                                color: targetChip.current ? Theme.c.text
                                                          : Theme.c.textMuted
                                font.pixelSize: Theme.m.fontSizeXs
                                font.bold: targetChip.current
                            }
                            HoverHandler {
                                cursorShape: Qt.PointingHandCursor }
                            TapHandler {
                                onTapped: Actions.invoke(
                                    "subtitles.set_translate_target",
                                    { language: targetChip.modelData })
                            }
                        }
                    }
                }
            }

            Rectangle {
                objectName: "subtitles_translate_button"
                visible: Subtitles.state !== "backend_missing"
                         && Subtitles.translateState === "ready"
                         && !Subtitles.translating
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.m.controlHeight
                radius: Theme.m.radiusMd
                color: trHover.hovered && fileRow.hasTitles
                       ? Theme.c.bgHover : Qt.alpha(Theme.c.glassOn, 0.08)
                border.width: 1
                border.color: Theme.c.border
                opacity: fileRow.hasTitles ? 1 : 0.4
                Text {
                    anchors.centerIn: parent
                    text: Tr.s["subtitles.translate"] || ""
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeSm
                }
                HoverHandler { id: trHover
                               cursorShape: Qt.PointingHandCursor }
                TapHandler {
                    enabled: fileRow.hasTitles
                    onTapped: Actions.invoke("subtitles.translate", {})
                }
            }

            Rectangle {
                objectName: "subtitles_translate_download"
                visible: Subtitles.state !== "backend_missing"
                         && Subtitles.translateState === "model_missing"
                         && !Subtitles.downloading
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.m.controlHeight
                radius: Theme.m.radiusMd
                color: trdlHover.hovered ? Theme.c.bgHover
                                         : Qt.alpha(Theme.c.glassOn, 0.08)
                border.width: 1
                border.color: Theme.c.border
                Text {
                    anchors.centerIn: parent
                    text: (Tr.s["subtitles.translate_dl"] || "")
                          + " (" + Subtitles.translateMissingMb + " MB)"
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeSm
                }
                HoverHandler { id: trdlHover
                               cursorShape: Qt.PointingHandCursor }
                TapHandler {
                    onTapped: Actions.invoke(
                        "subtitles.download_translate_models", {})
                }
            }

            Text {
                visible: Subtitles.state !== "backend_missing"
                         && Subtitles.translateState === "no_source"
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["subtitles.err.no_source"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            RowLayout {
                visible: Subtitles.translating
                Layout.fillWidth: true
                spacing: Theme.m.space2
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        objectName: "subtitles_translate_progress"
                        text: (Tr.s["subtitles.translating"] || "") + " "
                              + Math.round(Subtitles.translateProgress
                                           * 100) + "%"
                        color: Theme.c.textMuted
                        font.pixelSize: Theme.m.fontSizeXs
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 3
                        radius: 1.5
                        color: Qt.alpha(Theme.c.glassOn, 0.10)
                        Rectangle {
                            width: parent.width
                                   * Subtitles.translateProgress
                            height: parent.height
                            radius: 1.5
                            color: Theme.c.accent
                        }
                    }
                }
                IconButton {
                    objectName: "subtitles_translate_cancel"
                    size: 24; iconSize: 12
                    icon: Icons.close
                    label: Tr.s["export.cancel"] || ""
                    onTriggered: Subtitles.cancel_translate()
                }
            }

            Text {
                objectName: "subtitles_translate_result"
                visible: !Subtitles.translating
                         && (Subtitles.lastTranslated > 0
                             || (Subtitles.translateError !== ""
                                 && Subtitles.translateError !== "cancelled"))
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: {
                    if (Subtitles.translateError !== ""
                            && Subtitles.translateError !== "cancelled")
                        return Tr.s["subtitles.err."
                                    + Subtitles.translateError]
                            || (Tr.s["subtitles.err.failed"] || "")
                                .replace("{e}", Subtitles.translateError);
                    var note = (Tr.s["subtitles.translated"] || "")
                        .replace("{n}", Subtitles.lastTranslated);
                    if (Subtitles.longLines > 0)
                        note += " " + (Tr.s["subtitles.long_lines"] || "")
                            .replace("{n}", Subtitles.longLines);
                    return note;
                }
                color: Subtitles.translateError !== ""
                       && Subtitles.translateError !== "cancelled"
                       ? Theme.c.danger
                       : (Subtitles.longLines > 0 ? Theme.c.warning
                                                  : Theme.c.textMuted)
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            // The closing note: how many lines landed, or what went
            // wrong. A cancel says nothing - the user did it.
            Text {
                objectName: "subtitles_result"
                visible: !Subtitles.running
                         && (Subtitles.lastCount > 0
                             || (Subtitles.error !== ""
                                 && Subtitles.error !== "cancelled"))
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Subtitles.error !== ""
                          && Subtitles.error !== "cancelled"
                      ? (Tr.s["subtitles.err." + Subtitles.error]
                         || (Tr.s["subtitles.err.failed"] || "")
                            .replace("{e}", Subtitles.error))
                      : (Tr.s["subtitles.done"] || "")
                            .replace("{n}", Subtitles.lastCount)
                color: Subtitles.error !== ""
                       && Subtitles.error !== "cancelled"
                       ? Theme.c.danger : Theme.c.textMuted
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            Text {
                visible: Subtitles.state !== "backend_missing"
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Subtitles.state === "model_missing"
                      ? (Tr.s["subtitles.missing_hint"] || "")
                      : (Tr.s["subtitles.hint"] || "")
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            // Files: the Text lane in and out as .srt/.vtt. No model
            // needed - these work even where the speech engine cannot.
            RowLayout {
                id: fileRow
                Layout.fillWidth: true
                spacing: Theme.m.space2

                readonly property bool hasTitles: {
                    var clips = Project.timelineClips;
                    for (var i = 0; i < clips.length; i++)
                        if (clips[i].track === 3 && clips[i].text)
                            return true;
                    return false;
                }

                Repeater {
                    model: [{ key: "import", enabled: Project.isOpen },
                            { key: "export",
                              enabled: fileRow.hasTitles }]
                    delegate: Rectangle {
                        id: fileButton
                        required property var modelData
                        objectName: "subtitles_" + modelData.key + "_button"
                        Layout.fillWidth: true
                        Layout.preferredHeight: Theme.m.controlHeight - 4
                        radius: Theme.m.radiusMd
                        color: fileHover.hovered && modelData.enabled
                               ? Theme.c.bgHover
                               : Qt.alpha(Theme.c.glassOn, 0.08)
                        border.width: 1
                        border.color: Theme.c.border
                        opacity: modelData.enabled ? 1 : 0.4
                        Text {
                            anchors.centerIn: parent
                            text: Tr.s["subtitles." + fileButton.modelData.key]
                                  || ""
                            color: Theme.c.text
                            font.pixelSize: Theme.m.fontSizeXs + 1
                        }
                        HoverHandler { id: fileHover
                                       cursorShape: Qt.PointingHandCursor }
                        TapHandler {
                            enabled: fileButton.modelData.enabled
                            onTapped: fileButton.modelData.key === "import"
                                      ? importDialog.open()
                                      : exportDialog.open()
                        }
                    }
                }
            }
        }

        FileDialog {
            id: importDialog
            title: Tr.s["subtitles.import"] || ""
            fileMode: FileDialog.OpenFile
            nameFilters: ["SRT / WebVTT (*.srt *.vtt)"]
            onAccepted: Actions.invoke("subtitles.import_file",
                                       { path: String(selectedFile) })
        }

        FileDialog {
            id: exportDialog
            title: Tr.s["subtitles.export"] || ""
            fileMode: FileDialog.SaveFile
            defaultSuffix: "srt"
            nameFilters: ["SRT (*.srt)", "WebVTT (*.vtt)"]
            onAccepted: Actions.invoke("subtitles.export_file",
                                       { path: String(selectedFile) })
        }


        // ── the font list ─────────────────────────────────────────
        CardGroup {
            visible: root.view === "font"
            title: Tr.s["text.font"] || ""

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.m.space2
                IconButton {
                    size: 24; iconSize: 14
                    icon: Icons.chevronDown
                    rotation: 90
                    label: Tr.s["sticker.back"] || ""
                    onTriggered: root.view = ""
                }
                Text {
                    Layout.fillWidth: true
                    text: Tr.s["text.font_hint"] || ""
                    color: Theme.c.textDisabled
                    font.pixelSize: Theme.m.fontSizeXs
                    wrapMode: Text.WordWrap
                }
            }

            ListView {
                Layout.fillWidth: true
                Layout.preferredHeight: 320
                clip: true
                // The default face first, then everything installed.
                model: [""].concat(Qt.fontFamilies())
                delegate: Rectangle {
                    required property var modelData
                    width: ListView.view.width
                    height: 34
                    radius: Theme.m.radiusSm
                    color: rowHover.hovered ? Theme.c.bgHover : "transparent"
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        x: Theme.m.space2
                        width: parent.width - Theme.m.space2 * 2
                        text: modelData === ""
                            ? (Tr.s["text.font_default"] || "") : modelData
                        color: root.textClip !== null
                               && root.textClip.font === modelData
                            ? Theme.c.accent : Theme.c.text
                        font.family: modelData !== "" ? modelData
                                                      : Theme.m.fontFamily || ""
                        font.pixelSize: Theme.m.fontSizeSm + 2
                        elide: Text.ElideRight
                    }
                    HoverHandler { id: rowHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: {
                            root.commitStyle({ font: modelData });
                            root.view = "";
                        }
                    }
                }
            }
        }
    }
}
