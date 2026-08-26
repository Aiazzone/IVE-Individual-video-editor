// On-video overlay handles: select, move, scale and rotate a sticker OR
// a title by touching it on the preview, CapCut-style.
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
    // Selection is SHARED shell state: the timeline writes it, we write
    // it, and the Text panel reads it to know which title it is editing.
    readonly property string selectedId: Shell.v.selectedClipId || ""

    visible: Playback.hasMedia && Project.isOpen && !Playback.playing

    // ── canvas → item mapping ("cover", centred) ──────────────────
    readonly property real coverH: Math.max(height, width / canvasAspect)
    readonly property real coverW: coverH * canvasAspect
    readonly property real offX: (width - coverW) / 2
    readonly property real offY: (height - coverH) / 2

    // Overlay clips (stickers and titles) under the playhead. The early
    // return while playing is deliberate: positionSeconds is not read
    // then, so the binding does not re-evaluate 30 times a second during
    // playback.
    readonly property var overlayClips: {
        if (!visible)
            return [];
        var pos = Playback.positionSeconds;
        var all = Project.timelineClips;
        var out = [];
        for (var i = 0; i < all.length; i++) {
            var c = all[i];
            if ((c.stickerId || c.text) && c.start <= pos && pos < c.end)
                out.push(c);
            // The A/V clip under the playhead gets handles too - but
            // only when SELECTED: a frame around the whole video at
            // every pause would be noise, the overlays' frames are not.
            else if (c.track === 0 && c.hasVideo
                     && c.id === root.selectedId
                     && c.start <= pos && pos < c.end)
                out.push(c);
        }
        return out;
    }

    Repeater {
        model: root.overlayClips

        delegate: Item {
            id: box
            objectName: "sticker_handle_" + modelData.id

            // An A/V clip, as opposed to a sticker or a title. Unplaced,
            // its EFFECTIVE geometry is the canvas fit: centred, height
            // = min(1, canvas/clip aspect) - the seeds reproduce it so
            // the first drag starts from exactly what is on screen.
            readonly property bool isVideo:
                !modelData.stickerId && !modelData.text

            // Plain mirrors of the delegate's model, for the NESTED
            // delegates (the crop handles): inside a child Repeater
            // whose delegate declares its own required modelData, the
            // parent's model resolves as undefined - these do not.
            readonly property string clipId: modelData.id
            readonly property var clipCrop: modelData.crop || ({})

            // A keyframed video clip: the box must sit where the
            // ANIMATION has it at the paused playhead, and a drag pins
            // a diamond there instead of moving the static transform.
            readonly property bool keyed:
                box.isVideo && (modelData.keyframes || []).length > 0
            readonly property var evaluated: keyed
                ? Project.clip_keyframe_values(
                      modelData.id,
                      Playback.positionSeconds - modelData.start)
                : null
            readonly property real localT:
                Playback.positionSeconds - modelData.start

            // Live values: seeded from the model, driven by the hand
            // during a gesture. The Repeater recreates delegates whenever
            // the timeline changes, so the seeds are always fresh.
            property real vx: box.keyed ? box.evaluated.x
                              : box.isVideo && !modelData.placed
                              ? 0.5 : modelData.x
            property real vy: box.keyed ? box.evaluated.y
                              : box.isVideo && !modelData.placed
                              ? 0.5 : modelData.y
            property real vs: box.keyed ? box.evaluated.scale
                              : box.isVideo && !modelData.placed
                              ? Math.min(1, root.canvasAspect
                                            / box.spriteAspect)
                              : modelData.scale
            property real vr: box.keyed ? box.evaluated.rotation
                              : box.isVideo && !modelData.placed
                              ? 0 : modelData.rotation

            readonly property bool selected: root.selectedId === modelData.id
            // One slot for both kinds: the sticker file's ratio, or the
            // rendered text block's. Delegates are recreated whenever the
            // timeline changes, so an edited title re-measures.
            readonly property real spriteAspect:
                Math.max(0.05, Project.overlay_aspect(modelData.id))

            // The sticker's unrotated bounds on screen; the frame rotates
            // with the item, exactly like the baked raster does.
            readonly property real stickerH: vs * root.coverH
            width: Math.max(28, stickerH * spriteAspect)
            height: Math.max(28, stickerH)
            x: root.offX + vx * root.coverW - width / 2
            y: root.offY + vy * root.coverH - height / 2
            rotation: vr

            function pushLive() {
                Playback.set_overlay_live(modelData.id, vx, vy, vs, vr);
            }
            function commit() {
                if (box.keyed) {
                    // On an animated clip the drag PINS a diamond at
                    // the playhead - the gesture edits the animation,
                    // not the static transform underneath it.
                    Actions.invoke("timeline.set_clip_keyframe", {
                        clip_id: modelData.id, t: box.localT,
                        x: vx, y: vy, scale: vs, rotation: vr
                    });
                    return;
                }
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
                    Shell.set_selected_clip(modelData.id,
                        modelData.stickerId ? "sticker"
                        : modelData.text ? "text" : "video");
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

            // ── reset: a placed video back to the canvas fit ──────
            Rectangle {
                objectName: "video_reset_" + modelData.id
                visible: box.selected && box.isVideo
                         && modelData.placed === true
                width: 20
                height: 20
                radius: 10
                color: "#FFFFFF"
                border.width: 1
                border.color: "#59000000"
                anchors.horizontalCenter: parent.left
                anchors.verticalCenter: parent.top
                Text {
                    anchors.centerIn: parent
                    text: "↺"
                    color: "#111111"
                    font.pixelSize: 13
                }
                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -6
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Actions.invoke(
                        "timeline.reset_clip_transform",
                        { clip_id: modelData.id })
                }
            }

            // ── crop: pull an edge midpoint inwards (video only) ──
            // The video under the frame follows live (the Placement
            // filter reads the span crop); the box itself resizes on
            // release, when the model commits and the aspect updates.
            Repeater {
                model: box.selected && box.isVideo
                       ? ["left", "right", "top", "bottom"] : []
                delegate: Rectangle {
                    id: cropHandle
                    required property var modelData
                    objectName: "video_crop_" + modelData + "_"
                                + box.clipId
                    readonly property bool horizontal:
                        modelData === "left" || modelData === "right"
                    width: 12
                    height: 12
                    radius: 2
                    color: "#FFFFFF"
                    border.width: 1
                    border.color: "#59000000"
                    x: modelData === "left" ? -6
                     : modelData === "right" ? box.width - 6
                     : box.width / 2 - 6
                    y: modelData === "top" ? -6
                     : modelData === "bottom" ? box.height - 6
                     : box.height / 2 - 6

                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -6
                        cursorShape: cropHandle.horizontal
                            ? Qt.SplitHCursor : Qt.SplitVCursor

                        property var crop0: ({})
                        property var live: ({})
                        property point press

                        function clamped(value) {
                            return Math.min(0.45, Math.max(0, value));
                        }
                        onPressed: function (mouse) {
                            var held = box.clipCrop;
                            crop0 = { left: held.left || 0,
                                      top: held.top || 0,
                                      right: held.right || 0,
                                      bottom: held.bottom || 0 };
                            live = crop0;
                            var p = mapToItem(box, mouse.x, mouse.y);
                            press = Qt.point(p.x, p.y);
                        }
                        onPositionChanged: function (mouse) {
                            if (!pressed)
                                return;
                            var p = mapToItem(box, mouse.x, mouse.y);
                            var c = { left: crop0.left, top: crop0.top,
                                      right: crop0.right,
                                      bottom: crop0.bottom };
                            // The box shows the VISIBLE span: a pixel
                            // of drag is a fraction of what remains.
                            var visW = Math.max(0.1,
                                1 - crop0.left - crop0.right);
                            var visH = Math.max(0.1,
                                1 - crop0.top - crop0.bottom);
                            var edge = cropHandle.modelData;
                            if (edge === "left")
                                c.left = clamped(crop0.left
                                    + (p.x - press.x) / box.width * visW);
                            else if (edge === "right")
                                c.right = clamped(crop0.right
                                    + (press.x - p.x) / box.width * visW);
                            else if (edge === "top")
                                c.top = clamped(crop0.top
                                    + (p.y - press.y) / box.height * visH);
                            else
                                c.bottom = clamped(crop0.bottom
                                    + (press.y - p.y) / box.height * visH);
                            live = c;
                            Playback.set_video_crop_live(
                                box.clipId,
                                c.left, c.top, c.right, c.bottom);
                        }
                        onReleased: Actions.invoke("timeline.set_clip_crop", {
                            clip_id: box.clipId,
                            left: live.left, top: live.top,
                            right: live.right, bottom: live.bottom
                        })
                    }
                }
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
