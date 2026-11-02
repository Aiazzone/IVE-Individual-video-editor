// Background removal for the selected video clip.
//
// The subject stays, the scene behind it becomes a solid colour or a
// still image. The card only reads the selection and invokes
// timeline.set_clip_cutout (one undo step per change); the cutting is
// the engine's (ive/engine/cutout.py), on the same subject mask the
// masked effects use. Without the segmentation model the card says so
// and offers the download - a state, never an error.
import QtQuick
import QtQuick.Dialogs
import QtQuick.Layouts
import IVE

CardGroup {
    id: root

    /*! The selected A/V clip with a picture, or null. */
    readonly property var clip: {
        var id = Shell.v.selectedClipId || "";
        if (id === "")
            return null;
        var clips = Project.timelineClips;
        for (var i = 0; i < clips.length; i++)
            if (clips[i].id === id && clips[i].track === 0
                    && clips[i].hasVideo)
                return clips[i];
        return null;
    }
    readonly property var cut: root.clip !== null ? (root.clip.cutout || {}) : ({})
    readonly property bool on: root.cut.mode === "color"
                               || root.cut.mode === "image"
                               || root.cut.mode === "transparent"
    readonly property bool ready: Cutout.state === "ready"
    readonly property bool downloading:
        Subtitles.downloading && Subtitles.downloadingId === "u2netp"

    readonly property var swatches: ["#00B140", "#0047BB", "#FFFFFF",
                                     "#000000", "#808080"]

    title: Tr.s["cutout.group"] || ""

    function commit(changes) {
        if (root.clip === null)
            return;
        var c = root.cut;
        var args = {
            clip_id: root.clip.id,
            mode: changes.mode !== undefined ? changes.mode
                  : (c.mode || "color"),
            color: changes.color !== undefined ? changes.color
                   : (c.color || "#00B140"),
            image: changes.image !== undefined ? changes.image
                   : (c.image || ""),
            feather: changes.feather !== undefined ? changes.feather
                     : (c.feather !== undefined ? c.feather : 0.3),
            shrink: changes.shrink !== undefined ? changes.shrink
                    : (c.shrink !== undefined ? c.shrink : 0.1)
        };
        Actions.invoke("timeline.set_clip_cutout", args);
    }

    function fileName(path) {
        var s = String(path || "");
        var i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
        return i >= 0 ? s.substring(i + 1) : s;
    }

    Text {
        objectName: "cutout_hint"
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        text: root.clip === null ? (Tr.s["cutout.select_hint"] || "")
              : (Tr.s["cutout.hint"] || "")
        color: Theme.c.textDisabled
        font.pixelSize: Theme.m.fontSizeXs
        lineHeight: 1.35
    }

    // ── the model is not there yet ───────────────────────────────
    Text {
        visible: Cutout.state === "backend_missing"
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        text: Tr.s["cutout.backend_missing"] || ""
        color: Theme.c.danger
        font.pixelSize: Theme.m.fontSizeXs
    }
    Rectangle {
        objectName: "cutout_download"
        visible: Cutout.state === "model_missing"
        Layout.fillWidth: true
        Layout.preferredHeight: Theme.m.controlHeight + 6
        radius: Theme.m.radiusMd
        color: root.downloading ? Qt.alpha(Theme.c.glassOn, 0.12)
               : dlHover.hovered ? Qt.lighter(Theme.c.accent, 1.1)
               : Theme.c.accent
        Text {
            anchors.centerIn: parent
            text: root.downloading
                  ? (Tr.s["cutout.downloading"] || "") + " "
                    + Math.round(Subtitles.downloadProgress * 100) + "%"
                  : (Tr.s["cutout.download"] || "")
                    .replace("{mb}", Cutout.modelMb)
            color: root.downloading ? Theme.c.text : "#FFFFFF"
            font.pixelSize: Theme.m.fontSizeSm + 1
            font.bold: true
        }
        HoverHandler { id: dlHover; cursorShape: Qt.PointingHandCursor }
        TapHandler {
            enabled: !root.downloading && !Subtitles.downloading
            onTapped: Actions.invoke("cutout.download_model", {})
        }
    }

    // ── on / off ─────────────────────────────────────────────────
    SwitchRow {
        objectName: "cutout_switch"
        visible: root.clip !== null && root.ready
        checked: root.on
        label: Tr.s["cutout.remove"] || ""
        onToggled: function (v) { root.commit({ mode: v ? "color" : "off" }); }
    }

    ColumnLayout {
        visible: root.clip !== null && root.ready && root.on
        Layout.fillWidth: true
        spacing: Theme.m.space2

        Segmented {
            objectName: "cutout_mode"
            Layout.fillWidth: true
            value: root.cut.mode || "color"
            model: [
                { value: "color", text: Tr.s["cutout.mode.color"] || "" },
                { value: "image", text: Tr.s["cutout.mode.image"] || "" },
                { value: "transparent",
                  text: Tr.s["cutout.mode.transparent"] || "" }
            ]
            onPicked: function (v) {
                if (v === "image" && !root.cut.image)
                    imageDialog.open();
                else
                    root.commit({ mode: v });
            }
        }

        // The colour: a few that matter - green and blue are there to
        // be keyed again elsewhere, the rest are plain backdrops.
        Row {
            visible: (root.cut.mode || "color") === "color"
            spacing: Theme.m.space2
            Repeater {
                model: root.swatches
                delegate: Rectangle {
                    required property var modelData
                    objectName: "cutout_swatch_" + modelData.substring(1)
                    width: 30; height: 30
                    radius: 15
                    color: modelData
                    border.width: (root.cut.color || "").toUpperCase()
                                  === modelData ? 3 : 1
                    border.color: (root.cut.color || "").toUpperCase()
                                  === modelData ? Theme.c.accent
                                  : Qt.alpha(Theme.c.glassOn, 0.3)
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: root.commit({ mode: "color",
                                                color: parent.modelData })
                    }
                }
            }
        }

        // Nothing behind the subject: black in the preview (like any
        // hole in the sequence), see-through in an alpha export.
        Text {
            objectName: "cutout_transparent_hint"
            visible: root.cut.mode === "transparent"
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: Tr.s["cutout.transparent_hint"] || ""
            color: Theme.c.textDisabled
            font.pixelSize: Theme.m.fontSizeXs
            lineHeight: 1.35
        }

        RowLayout {
            visible: root.cut.mode === "image"
            Layout.fillWidth: true
            spacing: Theme.m.space2
            Text {
                objectName: "cutout_image_name"
                Layout.fillWidth: true
                elide: Text.ElideMiddle
                text: root.fileName(root.cut.image)
                color: Theme.c.textMuted
                font.pixelSize: Theme.m.fontSizeXs
            }
            Rectangle {
                objectName: "cutout_pick_image"
                Layout.preferredWidth: pickText.implicitWidth + 20
                Layout.preferredHeight: Theme.m.controlHeightSm + 4
                radius: Theme.m.radiusSm
                color: pickHover.hovered ? Theme.c.bgHover
                       : Qt.alpha(Theme.c.glassOn, 0.10)
                Text {
                    id: pickText
                    anchors.centerIn: parent
                    text: Tr.s["cutout.pick_image"] || ""
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeXs
                }
                HoverHandler { id: pickHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: imageDialog.open() }
            }
        }

        // The edge: soft, and pulled in - u2netp's mask bleeds a rim of
        // the old scene around hair; a touch of shrink hides it.
        Text {
            text: Tr.s["cutout.feather"] || ""
            color: Theme.c.textMuted
            font.pixelSize: Theme.m.fontSizeXs
        }
        AppSlider {
            objectName: "cutout_feather"
            Layout.fillWidth: true
            from: 0; to: 1; stepSize: 0.05
            label: Tr.s["cutout.feather"] || ""
            value: root.cut.feather !== undefined ? root.cut.feather : 0.3
            onCommitted: function (v) {
                root.commit({ feather: Math.round(v * 100) / 100 });
            }
        }
        Text {
            text: Tr.s["cutout.shrink"] || ""
            color: Theme.c.textMuted
            font.pixelSize: Theme.m.fontSizeXs
        }
        AppSlider {
            objectName: "cutout_shrink"
            Layout.fillWidth: true
            from: 0; to: 1; stepSize: 0.05
            label: Tr.s["cutout.shrink"] || ""
            value: root.cut.shrink !== undefined ? root.cut.shrink : 0.1
            onCommitted: function (v) {
                root.commit({ shrink: Math.round(v * 100) / 100 });
            }
        }
    }

    FileDialog {
        id: imageDialog
        title: Tr.s["cutout.pick_image"] || ""
        fileMode: FileDialog.OpenFile
        nameFilters: ["Images (*.png *.jpg *.jpeg *.webp *.bmp)"]
        onAccepted: root.commit({ mode: "image", image: String(selectedFile) })
    }
}
