// Motion tracking for the selected overlay (sticker or title).
//
// The card only ARMS the mode and watches: "Draw the target" sets
// Tracking.drawingFor, the preview layer (StickerHandles.qml) takes the
// box and invokes overlay.track at the playhead; the run happens on a
// worker (ive/ui/tracking_service.py) and lands as keyframes, one undo
// step. Without the VitTrack model tracking still works, position only
// (MIL baseline) - said plainly, with the way to get size too.
//
// On an overlay that already follows a path the same button RE-tracks:
// from the playhead, in the chosen direction, only that stretch is
// rewritten - and, with the switch on (default), with the relation to
// the target stored at the first track, so a drifted stretch is laid
// right instead of inheriting the drift.
import QtQuick
import QtQuick.Layouts
import IVE

CardGroup {
    id: root

    /*! The selected overlay clip dict (sticker or title), or null. */
    property var clip: null

    readonly property bool drawing:
        root.clip !== null && Tracking.drawingFor === root.clip.id
    readonly property bool hasPath:
        root.clip !== null && (root.clip.keyframes || []).length > 0
    readonly property bool hasRelation:
        root.clip !== null && root.clip.trackRef !== undefined
        && Object.keys(root.clip.trackRef || {}).length > 0
    readonly property bool failed:
        Tracking.error !== "" && Tracking.error !== "cancelled"

    title: Tr.s["tracking.group"] || ""
    visible: root.clip !== null

    Text {
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        text: root.drawing ? (Tr.s["tracking.draw_hint"] || "")
              : root.hasPath ? (Tr.s["tracking.has_path"] || "")
              : (Tr.s["tracking.hint"] || "")
        color: root.drawing ? Theme.c.text : Theme.c.textDisabled
        font.pixelSize: Theme.m.fontSizeXs
        lineHeight: 1.35
    }

    Text {
        objectName: "tracking_retrack_hint"
        visible: root.hasPath && !root.drawing && !Tracking.running
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        text: Tr.s["tracking.retrack_hint"] || ""
        color: Theme.c.textDisabled
        font.pixelSize: Theme.m.fontSizeXs
        lineHeight: 1.35
    }

    // Which way the track runs from the drawn box. "Both" by default:
    // a box drawn mid-shot follows the target over the whole shot.
    Segmented {
        objectName: "tracking_direction"
        visible: !Tracking.running && !root.drawing
        Layout.fillWidth: true
        value: Shell.v.trackingDirection || "both"
        model: [
            { value: "backward", text: Tr.s["tracking.dir.backward"] || "" },
            { value: "both",     text: Tr.s["tracking.dir.both"] || "" },
            { value: "forward",  text: Tr.s["tracking.dir.forward"] || "" }
        ]
        onPicked: function (v) {
            Actions.invoke("overlay.set_track_direction", { direction: v });
        }
    }

    SwitchRow {
        objectName: "tracking_keep_relation"
        visible: root.hasRelation && !root.drawing && !Tracking.running
        checked: Tracking.keepRelation
        label: Tr.s["tracking.keep_relation"] || ""
        onToggled: function (v) { Tracking.set_keep_relation(v); }
    }

    // Draw the target: arms the preview, and pauses - boxes are drawn
    // on a still frame, the one the track starts from.
    Rectangle {
        objectName: "tracking_draw_button"
        visible: !Tracking.running && Tracking.state !== "backend_missing"
        Layout.fillWidth: true
        Layout.preferredHeight: Theme.m.controlHeight + 6
        radius: Theme.m.radiusMd
        color: root.drawing ? Qt.alpha(Theme.c.glassOn, 0.12)
               : drawHover.hovered ? Qt.lighter(Theme.c.accent, 1.1)
               : Theme.c.accent
        opacity: Playback.hasMedia ? 1 : 0.4
        Text {
            anchors.centerIn: parent
            text: root.drawing ? (Tr.s["tracking.draw_cancel"] || "")
                  : root.hasPath ? (Tr.s["tracking.retrack"] || "")
                  : (Tr.s["tracking.draw"] || "")
            color: root.drawing ? Theme.c.text : "#FFFFFF"
            font.pixelSize: Theme.m.fontSizeSm + 2
            font.bold: true
        }
        HoverHandler { id: drawHover; cursorShape: Qt.PointingHandCursor }
        TapHandler {
            enabled: Playback.hasMedia
            onTapped: {
                if (root.drawing) {
                    Tracking.end_draw();
                    return;
                }
                if (Playback.playing)
                    Actions.invoke("playback.toggle", {});
                Tracking.begin_draw(root.clip.id);
            }
        }
    }

    RowLayout {
        visible: Tracking.running
        Layout.fillWidth: true
        spacing: Theme.m.space2
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3
            Text {
                objectName: "tracking_progress_label"
                text: (Tr.s["tracking.running"] || "") + " "
                      + Math.round(Tracking.progress * 100) + "%"
                color: Theme.c.textMuted
                font.pixelSize: Theme.m.fontSizeXs
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 3
                radius: 1.5
                color: Qt.alpha(Theme.c.glassOn, 0.10)
                Rectangle {
                    width: parent.width * Tracking.progress
                    height: parent.height
                    radius: 1.5
                    color: Theme.c.accent
                }
            }
        }
        IconButton {
            objectName: "tracking_cancel"
            size: 24; iconSize: 12
            icon: Icons.close
            label: Tr.s["tracking.cancel"] || ""
            onTriggered: Actions.invoke("overlay.track_cancel", {})
        }
    }

    // The closing note: pins landed (and where the target was lost),
    // or what went wrong. A cancel says nothing - the user did it.
    Text {
        objectName: "tracking_result"
        visible: !Tracking.running && !root.drawing
                 && (Tracking.lastPins > 0 || root.failed)
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        text: {
            if (root.failed)
                return Tr.s["tracking.err." + Tracking.error]
                       || Tr.s["tracking.err.failed"] || "";
            var done = (Tr.s["tracking.done"] || "")
                .replace("{n}", Tracking.lastPins);
            if (Tracking.lostBefore >= 0)
                done += " " + (Tr.s["tracking.lost_before"] || "")
                    .replace("{t}", Tracking.lostBefore.toFixed(1) + " s");
            if (Tracking.lostAt >= 0)
                done += " " + (Tr.s["tracking.lost"] || "")
                    .replace("{t}", Tracking.lostAt.toFixed(1) + " s");
            return done;
        }
        color: root.failed ? Theme.c.danger : Theme.c.textMuted
        font.pixelSize: Theme.m.fontSizeXs
        lineHeight: 1.35
    }

    // Baseline only: say so, and where size-following comes from.
    Text {
        objectName: "tracking_baseline"
        visible: Tracking.state === "model_missing"
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        text: Tr.s["tracking.baseline"] || ""
        color: Theme.c.textDisabled
        font.pixelSize: Theme.m.fontSizeXs
        lineHeight: 1.35
    }
}
