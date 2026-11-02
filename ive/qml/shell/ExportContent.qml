// Export, in two tabs.
//
//   SOCIAL   pick a platform, press export. No decisions to make.
//   CUSTOM   container, video codec, audio codec, resolution, quality.
//
// The split is deliberate: most exports are "put it on YouTube", and forcing
// that through a codec matrix is how editors become intimidating. Everything
// the custom tab exposes is still reachable from the same one action.
import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs
import components
import IVE

Item {
    id: root

    implicitHeight: column.implicitHeight + Theme.m.space3 * 2
    readonly property bool interacting: bitrateSlider.pressed

    property string tab: "social"
    property string platform: "youtube"
    property string presetId: "youtube_1080p"

    // custom tab state
    property string container: "mp4"
    property string videoCodec: "h264"
    property string audioCodec: "aac"
    property string aspect: "16x9"
    property string resolution: "1920x1080"
    property int bitrate: 12000
    /*! Keep a transparent background (custom tab, alpha codecs only). */
    property bool alpha: false
    readonly property bool alphaPossible:
        Export.supportsAlpha(root.container, root.videoCodec)

    // Presets of the platform the user tapped; the icons row filters this.
    readonly property var platformPresets: Export.presets.filter(function (p) {
        return p.platform === root.platform;
    })

    // One resolution ladder per aspect, same three tiers everywhere so
    // switching aspect keeps the tier (720p stays 720p, just reshaped).
    readonly property var aspectLadder: ({
        "16x9": [{ value: "1280x720",  text: "720p" },
                 { value: "1920x1080", text: "1080p" },
                 { value: "3840x2160", text: "4K" }],
        "9x16": [{ value: "720x1280",  text: "720p" },
                 { value: "1080x1920", text: "1080p" },
                 { value: "2160x3840", text: "4K" }],
        "4x3":  [{ value: "960x720",   text: "720p" },
                 { value: "1440x1080", text: "1080p" },
                 { value: "2880x2160", text: "4K" }],
        "1x1":  [{ value: "720x720",   text: "720p" },
                 { value: "1080x1080", text: "1080p" },
                 { value: "2160x2160", text: "4K" }],
        "21x9": [{ value: "1680x720",  text: "720p" },
                 { value: "2560x1080", text: "1080p" },
                 { value: "5120x2160", text: "4K" }]
    })

    readonly property var containerInfo: {
        var list = Export.containers;
        for (var i = 0; i < list.length; i++)
            if (list[i].id === root.container)
                return list[i];
        return list.length ? list[0] : null;
    }

    function currentOptions() {
        if (tab === "social")
            return { preset_id: presetId };
        var wh = resolution.split("x");
        return {
            container: container,
            video_codec: videoCodec,
            audio_codec: audioCodec,
            width: parseInt(wh[0]),
            height: parseInt(wh[1]),
            video_bitrate_kbps: bitrate,
            alpha: alpha && alphaPossible
        };
    }

    // What THIS export would produce, refreshed as the knobs move.
    // Warnings inform; only a missing encoder blocks the button.
    readonly property var flight: {
        if (!Playback.hasMedia)
            return null;
        Playback.durationSeconds;   // re-judge when the cut changes...
        Export.presets;             // ...or the preset list reloads
        return Export.preflight(currentOptions());
    }

    function warningText(w) {
        var base = Tr.s["export.warn." + w.id] || w.id;
        return w.detail ? base + "  ·  " + w.detail : base;
    }

    FolderDialog {
        id: destDialog
        title: Tr.s["export.destination"] || "Destination"
        // Python does the URL -> path conversion: the naive replace() here
        // kept percent-escapes (spaces, accents) and broke POSIX paths.
        onAccepted: Actions.invoke("export.start", {
            options: root.currentOptions(),
            folder: Project.localPath(String(selectedFolder)),
            filename: filenameField.text.trim()
        })
    }

    FileDialog {
        id: importDialog
        title: Tr.s["export.preset.import"] || ""
        nameFilters: ["JSON (*.json)"]
        onAccepted: Actions.invoke("export.import_preset", {
            path: Project.localPath(String(selectedFile))
        })
    }

    property string shareTargetId: ""
    FolderDialog {
        id: shareDialog
        title: Tr.s["export.preset.share"] || ""
        onAccepted: Actions.invoke("export.share_preset", {
            preset_id: root.shareTargetId,
            folder: Project.localPath(String(selectedFolder))
        })
    }

    ColumnLayout {
        id: column
        anchors { left: parent.left; right: parent.right; top: parent.top
                  margins: Theme.m.space3 }
        spacing: Theme.m.space3

        // ── nothing to export ─────────────────────────────────────
        CardGroup {
            visible: !Playback.hasMedia
            title: Tr.s["export.nothing.title"] || ""
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["export.nothing.hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }
        }

        // ── tabs ──────────────────────────────────────────────────
        Segmented {
            visible: Playback.hasMedia
            Layout.fillWidth: true
            value: root.tab
            model: [
                { value: "social", text: Tr.s["export.tab.social"] || "" },
                { value: "custom", text: Tr.s["export.tab.custom"] || "" }
            ]
            onPicked: function (v) { root.tab = v; }
        }

        // ── social ────────────────────────────────────────────────
        CardGroup {
            visible: Playback.hasMedia && root.tab === "social"
            title: Tr.s["export.tab.social"] || ""

            // One icon per platform; tapping it reveals that platform's
            // presets below. Monochrome glyphs, coloured by the theme.
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.m.space1

                Repeater {
                    model: Export.platforms
                    delegate: Item {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: 56
                        readonly property bool selected:
                            root.platform === modelData.id

                        Accessible.role: Accessible.RadioButton
                        Accessible.name: modelData.label
                        Accessible.checked: selected

                        Rectangle {
                            anchors.fill: parent
                            radius: Theme.m.radiusMd
                            color: parent.selected ? Theme.c.accent
                                 : platformHover.hovered ? Theme.c.bgHover
                                 : "transparent"
                            Behavior on color {
                                enabled: !Shell.v.reduceMotion
                                ColorAnimation { duration: Theme.m.durFast }
                            }
                        }
                        ColumnLayout {
                            anchors.centerIn: parent
                            spacing: 4
                            Glyph {
                                Layout.alignment: Qt.AlignHCenter
                                Layout.preferredWidth: 22
                                Layout.preferredHeight: 22
                                path: Icons[modelData.icon] || ""
                                color: parent.parent.selected
                                    ? Theme.c.onAccent : Theme.c.text
                            }
                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: modelData.label
                                color: parent.parent.selected
                                    ? Theme.c.onAccent : Theme.c.textDisabled
                                font.pixelSize: Theme.m.fontSizeXs - 1
                                elide: Text.ElideRight
                            }
                        }
                        HoverHandler {
                            id: platformHover
                            cursorShape: Qt.PointingHandCursor
                        }
                        TapHandler {
                            onTapped: {
                                root.platform = modelData.id;
                                // Land on a preset of the new platform, or
                                // the export button would render the old one.
                                var list = root.platformPresets;
                                var known = false;
                                for (var i = 0; i < list.length; i++)
                                    if (list[i].id === root.presetId)
                                        known = true;
                                if (!known && list.length)
                                    root.presetId = list[0].id;
                            }
                        }
                    }
                }
            }

            Repeater {
                model: root.platformPresets
                delegate: Item {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    readonly property bool selected: root.presetId === modelData.id

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.m.radiusMd
                        color: parent.selected ? Theme.c.accent
                             : presetHover.hovered ? Theme.c.bgHover : "transparent"
                    }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.m.space3
                        anchors.rightMargin: Theme.m.space3
                        spacing: Theme.m.space2
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Text {
                                text: modelData.label
                                color: parent.parent.parent.selected
                                    ? Theme.c.onAccent : Theme.c.text
                                font.pixelSize: Theme.m.fontSizeSm + 1
                            }
                            Text {
                                text: modelData.resolution
                                      + (modelData.note ? "  ·  " + modelData.note : "")
                                color: parent.parent.parent.selected
                                    ? Theme.c.onAccent : Theme.c.textDisabled
                                opacity: parent.parent.parent.selected ? 0.85 : 1
                                font.pixelSize: Theme.m.fontSizeXs
                            }
                        }
                        // A preset the USER saved can leave as a .json or
                        // leave for good; factory and pack presets cannot.
                        IconButton {
                            objectName: "preset_share_" + parent.parent.modelData.id
                            visible: parent.parent.modelData.source === "user"
                            size: 26; iconSize: 14
                            icon: Icons.exportIcon
                            label: Tr.s["export.preset.share"] || ""
                            onTriggered: {
                                root.shareTargetId = parent.parent.modelData.id;
                                shareDialog.open();
                            }
                        }
                        IconButton {
                            objectName: "preset_delete_" + parent.parent.modelData.id
                            visible: parent.parent.modelData.source === "user"
                            size: 26; iconSize: 14
                            icon: Icons.trash
                            label: Tr.s["export.preset.delete"] || ""
                            onTriggered: Actions.invoke("export.delete_preset",
                                { preset_id: parent.parent.modelData.id })
                        }
                        Glyph {
                            visible: parent.parent.selected
                            width: 15; height: 15
                            path: Icons.check
                            color: Theme.c.onAccent
                        }
                    }
                    HoverHandler { id: presetHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: root.presetId = modelData.id }
                }
            }

            // A colleague's preset arrives as one .json: bring it in here.
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.m.space2
                IconButton {
                    objectName: "preset_import"
                    size: 26; iconSize: 14
                    icon: Icons.folderOpen
                    label: Tr.s["export.preset.import"] || ""
                    onTriggered: importDialog.open()
                }
                Text {
                    Layout.fillWidth: true
                    text: Tr.s["export.preset.import"] || ""
                    color: Theme.c.textDisabled
                    font.pixelSize: Theme.m.fontSizeXs
                }
            }
        }

        // ── custom ────────────────────────────────────────────────
        CardGroup {
            visible: Playback.hasMedia && root.tab === "custom"
            title: Tr.s["export.format"] || ""

            SettingRow {
                label: Tr.s["export.container"] || ""
                Segmented {
                    value: root.container
                    model: Export.containers.map(function (c) {
                        return { value: c.id, text: c.label };
                    })
                    onPicked: function (v) {
                        root.container = v;
                        // Keep the codecs legal for the new container instead of
                        // letting the user build a combination FFmpeg refuses.
                        var info = root.containerInfo;
                        if (info && info.video.indexOf(root.videoCodec) < 0)
                            root.videoCodec = info.video[0];
                        if (info && info.audio.indexOf(root.audioCodec) < 0)
                            root.audioCodec = info.audio[0];
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                visible: root.containerInfo && root.containerInfo.note
                text: root.containerInfo ? root.containerInfo.note : ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
            }

            SettingRow {
                label: Tr.s["export.video_codec"] || ""
                Segmented {
                    value: root.videoCodec
                    model: (root.containerInfo ? root.containerInfo.video : [])
                        .map(function (id) {
                            return { value: id, text: Export.codecLabel(id) };
                        })
                    onPicked: function (v) { root.videoCodec = v; }
                }
            }

            // Only where it can survive: ProRes in MOV, VP9 in WebM/MKV.
            SwitchRow {
                objectName: "export_alpha"
                visible: root.alphaPossible
                checked: root.alpha
                label: Tr.s["export.alpha"] || ""
                onToggled: function (v) { root.alpha = v; }
            }
            Text {
                visible: root.alphaPossible
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["export.alpha.hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
            }

            SettingRow {
                label: Tr.s["export.audio_codec"] || ""
                Segmented {
                    value: root.audioCodec
                    model: (root.containerInfo ? root.containerInfo.audio : [])
                        .map(function (id) {
                            return { value: id, text: Export.codecLabel(id) };
                        })
                    onPicked: function (v) { root.audioCodec = v; }
                }
            }

            SettingRow {
                label: Tr.s["export.aspect"] || ""
                Segmented {
                    value: root.aspect
                    model: [
                        { value: "16x9", text: "16:9" },
                        { value: "9x16", text: "9:16" },
                        { value: "4x3",  text: "4:3" },
                        { value: "1x1",  text: "1:1" },
                        { value: "21x9", text: "21:9" }
                    ]
                    onPicked: function (v) {
                        // Keep the tier while reshaping: 1080p stays 1080p,
                        // only the frame changes.
                        var tier = 1;
                        var old = root.aspectLadder[root.aspect] || [];
                        for (var i = 0; i < old.length; i++)
                            if (old[i].value === root.resolution)
                                tier = i;
                        root.aspect = v;
                        root.resolution = root.aspectLadder[v][tier].value;
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["export.aspect." + root.aspect] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
            }

            SettingRow {
                label: Tr.s["export.resolution"] || ""
                Segmented {
                    value: root.resolution
                    model: root.aspectLadder[root.aspect]
                    onPicked: function (v) { root.resolution = v; }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: Theme.m.space2
                Text {
                    Layout.fillWidth: true
                    text: Tr.s["export.bitrate"] || ""
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeSm + 1
                }
                Text {
                    text: Math.round(bitrateSlider.value) + " kbps"
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeSm
                    font.family: "monospace"
                }
            }
            AppSlider {
                id: bitrateSlider
                Layout.fillWidth: true
                label: Tr.s["export.bitrate"] || ""
                from: 1000
                to: 60000
                stepSize: 500
                value: root.bitrate
                onCommitted: function (v) { root.bitrate = Math.round(v); }
            }

            // These knobs, frozen under a name: the preset appears in the
            // social tab under "Other" and travels as one .json.
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: Theme.m.space2
                spacing: Theme.m.space2
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 30
                    radius: Theme.m.radiusMd
                    color: Qt.alpha(Theme.c.glassOn, 0.07)
                    border.width: 1
                    border.color: presetNameField.activeFocus ? Theme.c.accent
                                                              : Theme.c.border
                    TextInput {
                        id: presetNameField
                        objectName: "preset_name_field"
                        anchors.fill: parent
                        anchors.leftMargin: Theme.m.space2
                        anchors.rightMargin: Theme.m.space2
                        verticalAlignment: TextInput.AlignVCenter
                        color: Theme.c.text
                        font.pixelSize: Theme.m.fontSizeSm
                        selectByMouse: true
                        selectionColor: Theme.c.accent
                        clip: true
                    }
                    Text {
                        anchors.fill: presetNameField
                        verticalAlignment: Text.AlignVCenter
                        visible: presetNameField.text === ""
                                 && !presetNameField.activeFocus
                        text: Tr.s["export.preset.name_hint"] || ""
                        color: Theme.c.textDisabled
                        font.pixelSize: Theme.m.fontSizeSm
                        elide: Text.ElideRight
                    }
                }
                Rectangle {
                    objectName: "preset_save"
                    readonly property bool ready:
                        presetNameField.text.trim() !== ""
                    Layout.preferredHeight: 30
                    Layout.preferredWidth: saveLabel.implicitWidth
                                           + Theme.m.space3 * 2
                    radius: Theme.m.radiusMd
                    color: ready ? (saveHover.hovered ? Theme.c.accentHover
                                                      : Theme.c.accent)
                                 : Qt.alpha(Theme.c.glassOn, 0.08)
                    Text {
                        id: saveLabel
                        anchors.centerIn: parent
                        text: Tr.s["export.preset.save"] || ""
                        color: parent.ready ? Theme.c.onAccent
                                            : Theme.c.textDisabled
                        font.pixelSize: Theme.m.fontSizeXs
                    }
                    HoverHandler { id: saveHover
                                   cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: {
                            if (!parent.ready)
                                return;
                            Actions.invoke("export.save_preset", {
                                name: presetNameField.text.trim(),
                                options: root.currentOptions()
                            });
                            presetNameField.text = "";
                        }
                    }
                }
            }
        }

        // ── file name ─────────────────────────────────────────────
        CardGroup {
            visible: Playback.hasMedia
            title: Tr.s["export.filename"] || ""

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.m.controlHeight
                radius: Theme.m.radiusMd
                color: Qt.alpha(Theme.c.glassOn, 0.07)
                border.width: 1
                border.color: filenameField.activeFocus ? Theme.c.accent
                                                        : Theme.c.border

                TextInput {
                    id: filenameField
                    anchors.fill: parent
                    anchors.leftMargin: Theme.m.space2
                    anchors.rightMargin: Theme.m.space2
                    verticalAlignment: TextInput.AlignVCenter
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeSm + 1
                    selectByMouse: true
                    selectionColor: Theme.c.accent
                    clip: true
                }
                // Placeholder, not a preset value: an empty field means
                // "name it after the source", and typing replaces nothing.
                Text {
                    anchors.fill: filenameField
                    verticalAlignment: Text.AlignVCenter
                    visible: filenameField.text === ""
                             && !filenameField.activeFocus
                    text: Tr.s["export.filename.hint"] || ""
                    color: Theme.c.textDisabled
                    font.pixelSize: Theme.m.fontSizeSm + 1
                    elide: Text.ElideRight
                }
            }
        }

        // ── preflight: what this export would produce ─────────────
        // The estimate is always there; warnings appear when the
        // arithmetic says so. Only a missing encoder disables the
        // button - everything else informs and steps aside.
        CardGroup {
            visible: Playback.hasMedia && root.flight !== null
            objectName: "export_preflight"

            Text {
                objectName: "export_estimate"
                Layout.fillWidth: true
                text: {
                    if (!root.flight)
                        return "";
                    var s = Math.round(root.flight.durationSeconds);
                    var clock = Math.floor(s / 60) + ":"
                                + ("0" + (s % 60)).slice(-2);
                    return (Tr.s["export.estimate"] || "~%1 MB · %2")
                        .replace("%1", root.flight.sizeMb)
                        .replace("%2", clock)
                        + (root.flight.encoder
                           ? "  ·  " + root.flight.encoder : "");
                }
                color: Theme.c.textMuted
                font.pixelSize: Theme.m.fontSizeXs
            }
            Repeater {
                model: root.flight ? root.flight.warnings : []
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: Theme.m.space1
                    Glyph {
                        Layout.preferredWidth: 13
                        Layout.preferredHeight: 13
                        path: Icons.alert
                        color: modelData.id === "no_encoder"
                            ? Theme.c.danger : Theme.c.warning
                    }
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: root.warningText(modelData)
                        color: modelData.id === "no_encoder"
                            ? Theme.c.danger : Theme.c.warning
                        font.pixelSize: Theme.m.fontSizeXs
                        lineHeight: 1.3
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["export.limits"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }
        }

        // ── run / queue another ───────────────────────────────────
        // The button always QUEUES: while a job renders, tapping it
        // lines up the current settings as the next job - three
        // platforms in three taps. Stopping lives on the queue rows.
        Rectangle {
            visible: Playback.hasMedia
            objectName: "export_run"
            readonly property bool blocked: root.flight !== null
                                            && root.flight.ok === false
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.m.controlHeight
            radius: Theme.m.radiusMd
            color: blocked ? Qt.alpha(Theme.c.glassOn, 0.08)
                 : exportHover.hovered ? Theme.c.accentHover : Theme.c.accent

            Text {
                anchors.centerIn: parent
                text: parent.blocked ? (Tr.s["export.blocked"] || "")
                    : Export.running ? (Tr.s["export.enqueue"] || "")
                    : (Tr.s["export.start"] || "")
                color: parent.blocked ? Theme.c.textDisabled : Theme.c.onAccent
                font.pixelSize: Theme.m.fontSizeSm + 1
                font.bold: !parent.blocked
            }
            HoverHandler { id: exportHover; cursorShape: Qt.PointingHandCursor }
            TapHandler {
                onTapped: {
                    if (!parent.blocked)
                        destDialog.open();
                }
            }
        }

        // ── the queue ─────────────────────────────────────────────
        CardGroup {
            visible: Export.queue.length > 0
            objectName: "export_queue"
            title: Tr.s["export.queue"] || ""

            Repeater {
                model: Export.queue
                delegate: Rectangle {
                    id: jobRow
                    required property var modelData
                    objectName: "export_job_" + modelData.id
                    Layout.fillWidth: true
                    Layout.preferredHeight: 34
                    radius: Theme.m.radiusMd
                    color: modelData.state === "running"
                        ? Qt.alpha(Theme.c.accent, 0.10)
                        : Qt.alpha(Theme.c.glassOn, 0.05)

                    // Progress paints the row itself, like the old button.
                    Rectangle {
                        anchors { left: parent.left; top: parent.top
                                  bottom: parent.bottom }
                        width: parent.width
                               * (jobRow.modelData.state === "running"
                                  ? Export.progress : 0)
                        radius: Theme.m.radiusMd
                        color: Theme.c.accent
                        opacity: 0.3
                    }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.m.space2
                        anchors.rightMargin: 4
                        spacing: Theme.m.space2
                        Text {
                            Layout.fillWidth: true
                            text: jobRow.modelData.name
                            color: jobRow.modelData.state === "error"
                                ? Theme.c.danger : Theme.c.text
                            font.pixelSize: Theme.m.fontSizeXs
                            elide: Text.ElideMiddle
                        }
                        Text {
                            text: jobRow.modelData.state === "running"
                                ? Math.round(Export.progress * 100) + "%"
                                : (Tr.s["export.queue."
                                        + jobRow.modelData.state] || "")
                            color: jobRow.modelData.state === "done"
                                ? Theme.c.success
                                : jobRow.modelData.state === "error"
                                  ? Theme.c.danger : Theme.c.textMuted
                            font.pixelSize: Theme.m.fontSizeXs
                        }
                        Glyph {
                            visible: jobRow.modelData.state === "done"
                            Layout.preferredWidth: 13
                            Layout.preferredHeight: 13
                            path: Icons.check
                            color: Theme.c.success
                        }
                        IconButton {
                            objectName: "export_job_stop_" + jobRow.modelData.id
                            visible: jobRow.modelData.state === "running"
                                     || jobRow.modelData.state === "waiting"
                            size: 24; iconSize: 12
                            icon: Icons.close
                            label: Tr.s["export.cancel"] || ""
                            onTriggered: jobRow.modelData.state === "running"
                                ? Actions.invoke("export.cancel")
                                : Export.remove_job(jobRow.modelData.id)
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.m.space2
                Item { Layout.fillWidth: true }
                Text {
                    objectName: "export_queue_clear"
                    visible: Export.queue.some(function (j) {
                        return j.state !== "waiting" && j.state !== "running";
                    })
                    text: Tr.s["export.queue.clear"] || ""
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeXs
                    font.underline: clearHover.hovered
                    HoverHandler { id: clearHover
                                   cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: Export.clear_finished() }
                }
                Text {
                    objectName: "export_queue_cancel_all"
                    visible: Export.pendingCount > 1
                    text: Tr.s["export.queue.cancel_all"] || ""
                    color: Theme.c.danger
                    font.pixelSize: Theme.m.fontSizeXs
                    font.underline: cancelAllHover.hovered
                    HoverHandler { id: cancelAllHover
                                   cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: Actions.invoke("export.cancel_all")
                    }
                }
            }
        }
    }
}
