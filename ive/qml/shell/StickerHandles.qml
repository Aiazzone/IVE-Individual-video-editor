// On-video sticker handles: select, move, scale and rotate a sticker by
// touching it on the preview, CapCut-style.
//
// Geometry: the item is laid exactly over the video item, and the canvas
// is mapped with the SAME "cover" rule PreviewItem paints with - the
// canvas (Playback.aspect) scaled to cover this item and centred. With an
// explicit project canvas the two ratios match and the mapping is the
// identity; on "auto" it reproduces the crop, so the frame sits exactly
// on the composited pixels.
//
// The gesture is two-phased on purpose (see transport.set_sticker_live):
// while the hand moves, Playback.set_sticker_live mutates the live spans
// and the paused frame re-renders - no undo entries, no graph rebuild;
// the release commits ONE timeline.set_clip_transform action, which is
// the single undo step for the whole drag.
//
// Handles appear while PAUSED only: during playback the playhead sweeps
// spans continuously and boxes flickering in and out would just be noise.
// Everything drawn here is fixed white with a shadow - it sits on the
// video, which does not follow the theme (docs/UI_SHELL.md).
import QtQuick
import IVE

Item {
    id: root

    /*! The aspect the sequence composites at: Playback.aspect. */
    property real canvasAspect: 16 / 9
    /*! The sticker clip currently selected on the video, "" for none. */
    property string selectedId: ""

    visible: Playback.hasMedia && Project.isOpen && !Playback.playing

    // ── canvas → item mapping ("cover", centred) ──────────────────
    readonly property real coverH: Math.max(height, width / canvasAspect)
    readonly property real coverW: coverH * canvasAspect
    readonly property real offX: (width - coverW) / 2
    readonly property real offY: (height - coverH) / 2

    // Sticker clips under the playhead. The early return while playing is
    // deliberate: positionSeconds is not read then, so the binding does
    // not re-evaluate 30 times a second during playback.
    readonly property var stickerClips: {
        if (!visible)
            return [];
        var pos = Playback.positionSeconds;
        var all = Project.timelineClips;
        var out = [];
        for (var i = 0; i < all.length; i++) {
            var c = all[i];
            if (c.stickerId && c.start <= pos && pos < c.end)
                out.push(c);
        }
        return out;
    }

    Repeater {
        model: root.stickerClips

        delegate: Item {
            id: box
            objectName: "sticker_handle_" + modelData.id

            // Live values: seeded from the model, driven by the hand
            // during a gesture. The Repeater recreates delegates whenever
            // the timeline changes, so the seeds are always fresh.
            property real vx: modelData.x
            property real vy: modelData.y
            property real vs: modelData.scale
            property real vr: modelData.rotation

            readonly property bool selected: root.selectedId === modelData.id
            readonly property real spriteAspect:
                Math.max(0.05, Stickers.aspect(modelData.stickerId))

            // The sticker's unrotated bounds on screen; the frame rotates
            // with the item, exactly like the baked raster does.
            readonly property real stickerH: vs * root.coverH
            width: Math.max(28, stickerH * spriteAspect)
            height: Math.max(28, stickerH)
            x: root.offX + vx * root.coverW - width / 2
            y: root.offY + vy * root.coverH - height / 2
            rotation: vr

            function pushLive() {
                Playback.set_sticker_live(modelData.id, vx, vy, vs, vr);
            }
            function commit() {
                Actions.invoke("timeline.set_clip_transform", {
                    clip_id: modelData.id,
                    x: vx, y: vy, scale: vs, rotation: vr
                });
            }
            // Centre of the box in ROOT coordinates, for scale/rotate math.
            function centre() {
                return Qt.point(root.offX + vx * root.coverW,
                                root.offY + vy * root.coverH);
            }

            // ── the frame ─────────────────────────────────────────
            Rectangle {
                anchors.fill: parent
                color: "transparent"
                radius: 3
                border.width: box.selected ? 2 : 1
                border.color: box.selected ? "#FFFFFF"
                    : (moveArea.containsMouse ? "#E6FFFFFF" : "#66FFFFFF")
            }
            // A hairline shadow so the white frame reads on a white video.
            Rectangle {
                anchors.fill: parent
                anchors.margins: box.selected ? -1 : 0
                color: "transparent"
                radius: 4
                border.width: 1
                border.color: "#33000000"
                z: -1
            }

            // ── move: press anywhere on the sticker ───────────────
            MouseArea {
                id: moveArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor

                property point press
                property real x0: 0
                property real y0: 0

                onPressed: function (mouse) {
                    root.selectedId = modelData.id;
                    var p = mapToItem(root, mouse.x, mouse.y);
                    press = Qt.point(p.x, p.y);
                    x0 = box.vx;
                    y0 = box.vy;
                }
                onPositionChanged: function (mouse) {
                    if (!pressed)
                        return;
                    var p = mapToItem(root, mouse.x, mouse.y);
                    box.vx = Math.min(1, Math.max(0,
                        x0 + (p.x - press.x) / root.coverW));
                    box.vy = Math.min(1, Math.max(0,
                        y0 + (p.y - press.y) / root.coverH));
                    box.pushLive();
                }
                onReleased: box.commit()
            }

            // ── scale: the bottom-right corner ────────────────────
            Rectangle {
                id: scaleHandle
                objectName: "sticker_scale_" + modelData.id
                width: 14
                height: 14
                radius: 7
                color: "#FFFFFF"
                border.width: 1
                border.color: "#59000000"
                anchors.horizontalCenter: parent.right
                anchors.verticalCenter: parent.bottom
                visible: box.selected

                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -8
                    cursorShape: Qt.SizeFDiagCursor

                    property real d0: 1
                    property real s0: 1

                    onPressed: function (mouse) {
                        var p = mapToItem(root, mouse.x, mouse.y);
                        var c = box.centre();
                        d0 = Math.max(8, Math.hypot(p.x - c.x, p.y - c.y));
                        s0 = box.vs;
                    }
                    onPositionChanged: function (mouse) {
                        if (!pressed)
                            return;
                        var p = mapToItem(root, mouse.x, mouse.y);
                        var c = box.centre();
                        var d = Math.max(8, Math.hypot(p.x - c.x, p.y - c.y));
                        box.vs = Math.min(2, Math.max(0.02, s0 * d / d0));
                        box.pushLive();
                    }
                    onReleased: box.commit()
                }
            }

            // ── rotate: the stalk above the top edge ──────────────
            Rectangle {
                width: 1
                height: 18
                color: "#B3FFFFFF"
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.top
                visible: box.selected
            }
            Rectangle {
                id: rotateHandle
                objectName: "sticker_rotate_" + modelData.id
                width: 14
                height: 14
                radius: 7
                color: "#FFFFFF"
                border.width: 1
                border.color: "#59000000"
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.top
                anchors.bottomMargin: 16
                visible: box.selected

                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -8
                    cursorShape: Qt.CrossCursor

                    property real a0: 0
                    property real r0: 0

                    function angleTo(mouse) {
                        var p = mapToItem(root, mouse.x, mouse.y);
                        var c = box.centre();
                        return Math.atan2(p.y - c.y, p.x - c.x) * 180 / Math.PI;
                    }
                    onPressed: function (mouse) {
                        a0 = angleTo(mouse);
                        r0 = box.vr;
                    }
                    onPositionChanged: function (mouse) {
                        if (!pressed)
                            return;
                        var r = r0 + angleTo(mouse) - a0;
                        // Snap to the right angles: a hand-drawn 89.2
                        // degrees is an unmade decision, not a choice.
                        var snapped = Math.round(r / 90) * 90;
                        if (Math.abs(r - snapped) < 3)
                            r = snapped;
                        box.vr = r;
                        box.pushLive();
                    }
                    onReleased: box.commit()
                }
            }
        }
    }
}
