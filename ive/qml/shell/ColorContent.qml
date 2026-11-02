// Colour effects, in two tabs.
//
//   COLORS      the family cards (name + count, no previews), then inside
//               a family the thumbnails of the SAME frame of the user's
//               own footage, one per effect.
//   FAVORITES   the starred effects, gathered from every family.
//
// Every thumbnail carries a star, top right: hollow when not starred, gold
// when starred; clicking toggles it (action `color.toggle_favorite`, the
// list persists in settings). A thumbnail is DRAGGED onto the timeline to
// apply it. The catalogue itself is JSON on disk (ive/color/library.py).
import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import components
import IVE

Item {
    id: root

    implicitHeight: column.implicitHeight + Theme.m.space3 * 2

    /*! Which half of the catalogue this instance browses: "color"
        (grading families + the manual dials) or "fx" (the Effects
        panel: AI subject looks, artistic stylizations). One catalogue
        underneath - only the browsing is split. */
    property string catalog: "color"

    property string tab: "colors"
    /*! "" = the family grid; a section id = the looks inside it. */
    property string section: ""

    /*! The sections THIS panel browses. */
    readonly property var catalogSections: {
        var all = ColorFx.sections;
        return all.filter(function (s) {
            return s.catalog === root.catalog;
        });
    }

    /*! The effect being dragged towards the timeline, "" when none. Read
        by FloatingPanel as `interacting`: the panel must not retract and
        kill the drag mid-flight. */
    property string draggingEffect: ""
    property point dragScenePos: Qt.point(0, 0)
    readonly property bool interacting: draggingEffect !== ""

    /*! What the grid shows: a family's looks, or the starred ones. */
    readonly property var gridEffects: {
        var all = ColorFx.effects.filter(function (e) {
            return e.catalog === root.catalog;
        });
        if (tab === "favorites") {
            var favs = ColorFx.favorites;
            return all.filter(function (e) { return favs.indexOf(e.id) >= 0; });
        }
        return all.filter(function (e) { return e.section === root.section; });
    }

    function isFavorite(effectId) {
        return ColorFx.favorites.indexOf(effectId) >= 0;
    }

    // The ghost that follows the pointer lives on the WINDOW, not in this
    // panel: the panel clips its children, so a card dragged towards the
    // timeline would vanish at the panel's edge. It also CARRIES the Drag:
    // the attached drag publishes its position when its item moves, and
    // this item really moves - the reliable way to reach a DropArea.
    Rectangle {
        id: dragGhost
        parent: root.Window.window ? root.Window.window.contentItem : root
        visible: root.draggingEffect !== ""
        width: 104
        height: 60
        radius: Theme.m.radiusSm
        color: Theme.c.clipEffect
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, 0.3)
        opacity: 0.9
        x: root.dragScenePos.x - 52
        y: root.dragScenePos.y - 30
        z: 100000

        /*! Read by the timeline's DropArea via drop.source. */
        property string effectId: root.draggingEffect

        Drag.active: root.draggingEffect !== ""
        Drag.keys: ["ive-effect"]
        Drag.hotSpot.x: 52
        Drag.hotSpot.y: 30

        Image {
            anchors.fill: parent
            asynchronous: true
            fillMode: Image.PreserveAspectCrop
            sourceSize.width: 160
            source: root.draggingEffect !== ""
                ? root.thumbSource(root.draggingEffect) : ""
        }
    }

    // The frame every preview is rendered from: the first video on the
    // timeline, else the first video in the pool, else nothing (plain
    // coloured cards - still usable, just not personalised).
    readonly property string sampleSource: {
        var clips = Project.timelineClips;
        for (var i = 0; i < clips.length; i++)
            if (clips[i].hasVideo && clips[i].path)
                return clips[i].path;
        var pool = Project.media;
        for (var k = 0; k < pool.length; k++)
            if (pool[k].width > 0 && !pool[k].missing)
                return pool[k].path;
        return "";
    }

    function thumbSource(effectId) {
        if (sampleSource === "")
            return "";
        // Reading `rev` makes every caller's binding re-resolve when the
        // worker lands a new PNG ("" until then, so the pink card shows).
        return Thumbs.rev >= 0
            ? Thumbs.thumb(sampleSource, effectId) : "";
    }

    function sectionLabel(id) {
        return Tr.s["color.section." + id] || id;
    }

    ColumnLayout {
        id: column
        anchors { left: parent.left; right: parent.right; top: parent.top
                  margins: Theme.m.space3 }
        spacing: Theme.m.space3

        // ── tabs ──────────────────────────────────────────────────
        Segmented {
            Layout.fillWidth: true
            value: root.tab
            model: [
                { value: "colors",
                  text: (root.catalog === "fx"
                         ? Tr.s["fx.tab.effects"]
                         : Tr.s["color.tab.colors"]) || "" },
                { value: "favorites", text: Tr.s["color.tab.favorites"] || "" }
            ]
            onPicked: function (v) { root.tab = v; }
        }

        // ── background removal on the selected video clip ─────────
        // The Effects panel's own tool: the AI subject effects tint
        // the scene, this one REPLACES it.
        CutoutCard {
            objectName: "cutout_card"
            visible: root.catalog === "fx"
                     && root.tab === "colors" && root.section === ""
        }

        // ── the manual grade ──────────────────────────────────────
        // Nine dials on the SELECTED Color-lane clip - an effect gets
        // hand adjustments layered on top of its recipe, an "Adjust"
        // clip is dials alone. Committed on release, one undo each;
        // the default value removes the dial from the grade.
        CardGroup {
            id: adjustCard
            visible: root.catalog === "color"
                     && root.tab === "colors" && root.section === ""
            title: Tr.s["color.adjust_group"] || ""

            readonly property var gradeClip: {
                var id = Shell.v.selectedClipId || "";
                if (id === "")
                    return null;
                var clips = Project.timelineClips;
                for (var i = 0; i < clips.length; i++)
                    if (clips[i].id === id && clips[i].track === 1)
                        return clips[i];
                return null;
            }

            Rectangle {
                objectName: "color_adjust_add"
                visible: adjustCard.gradeClip === null
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.m.controlHeight
                radius: Theme.m.radiusMd
                color: adjHover.hovered && Project.isOpen
                       ? Theme.c.bgHover : Qt.alpha(Theme.c.glassOn, 0.08)
                border.width: 1
                border.color: Theme.c.border
                opacity: Project.isOpen ? 1 : 0.4
                Text {
                    anchors.centerIn: parent
                    text: Tr.s["color.adjust_add"] || ""
                    color: Theme.c.text
                    font.pixelSize: Theme.m.fontSizeSm
                }
                HoverHandler { id: adjHover
                               cursorShape: Qt.PointingHandCursor }
                TapHandler {
                    enabled: Project.isOpen
                    onTapped: {
                        var at = Playback.hasMedia
                            ? Playback.positionSeconds : 0;
                        Actions.invoke("timeline.place_grade", { at: at });
                        // Select what just landed, so the dials open on
                        // it at once.
                        var clips = Project.timelineClips;
                        for (var i = clips.length - 1; i >= 0; i--)
                            if (clips[i].track === 1
                                    && clips[i].start <= at + 0.01
                                    && at < clips[i].end + 0.01
                                    && clips[i].effectId === "") {
                                Shell.set_selected_clip(clips[i].id,
                                                        "color");
                                break;
                            }
                    }
                }
            }
            Text {
                visible: adjustCard.gradeClip === null
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["color.adjust_hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            Repeater {
                model: [
                    { key: "brightness", from: -0.5, to: 0.5, def: 0 },
                    { key: "contrast", from: 0.2, to: 2, def: 1 },
                    { key: "saturation", from: 0, to: 2, def: 1 },
                    { key: "gamma", from: 0.3, to: 2.5, def: 1 },
                    { key: "temperature", from: -1, to: 1, def: 0 },
                    { key: "tint", from: -1, to: 1, def: 0 },
                    { key: "shadows", from: -1, to: 1, def: 0 },
                    { key: "highlights", from: -1, to: 1, def: 0 },
                    { key: "vignette", from: 0, to: 1, def: 0 }
                ]
                delegate: RowLayout {
                    id: dialRow
                    required property var modelData
                    visible: adjustCard.gradeClip !== null
                    Layout.fillWidth: true
                    spacing: Theme.m.space2
                    Text {
                        Layout.preferredWidth: 88
                        text: Tr.s["color.dial." + dialRow.modelData.key]
                              || dialRow.modelData.key
                        color: Theme.c.textMuted
                        font.pixelSize: Theme.m.fontSizeXs
                        elide: Text.ElideRight
                    }
                    AppSlider {
                        id: dial
                        objectName: "color_dial_" + dialRow.modelData.key
                        Layout.fillWidth: true
                        from: dialRow.modelData.from
                        to: dialRow.modelData.to
                        stepSize: 0.01
                        label: Tr.s["color.dial." + dialRow.modelData.key]
                               || dialRow.modelData.key
                        value: {
                            var clip = adjustCard.gradeClip;
                            if (clip === null)
                                return dialRow.modelData.def;
                            var held = clip.grade[dialRow.modelData.key];
                            return held !== undefined ? held
                                                      : dialRow.modelData.def;
                        }
                        onCommitted: function (v) {
                            if (adjustCard.gradeClip !== null)
                                Actions.invoke("timeline.set_clip_grade", {
                                    clip_id: adjustCard.gradeClip.id,
                                    key: dialRow.modelData.key,
                                    value: Math.round(v * 100) / 100
                                });
                        }
                    }
                    Text {
                        Layout.preferredWidth: 36
                        horizontalAlignment: Text.AlignRight
                        text: dial.effectiveValue.toFixed(2)
                        color: Theme.c.textMuted
                        font.pixelSize: Theme.m.fontSizeXs
                        font.family: "monospace"
                    }
                }
            }
        }

        // ── the families (no previews here) ───────────────────────
        CardGroup {
            visible: root.tab === "colors" && root.section === ""
            title: (root.catalog === "fx" ? Tr.s["fx.sections"]
                                          : Tr.s["color.sections"]) || ""

            Repeater {
                model: root.catalogSections
                delegate: Item {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 48

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.m.radiusMd
                        color: sectionHover.hovered ? Theme.c.bgHover
                                                    : Qt.alpha(Theme.c.glassOn, 0.05)
                    }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.m.space3
                        anchors.rightMargin: Theme.m.space2
                        spacing: Theme.m.space3

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                Layout.fillWidth: true
                                text: root.sectionLabel(modelData.id)
                                color: Theme.c.text
                                font.pixelSize: Theme.m.fontSizeSm + 2
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                text: (Tr.s["color.count"] || "{n}")
                                          .replace("{n}", modelData.count)
                                color: Theme.c.textDisabled
                                font.pixelSize: Theme.m.fontSizeXs
                            }
                        }
                        Glyph {
                            width: 15; height: 15
                            rotation: -90
                            path: Icons.chevronDown
                            color: Theme.c.textDisabled
                        }
                    }
                    HoverHandler { id: sectionHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: root.section = modelData.id }
                }
            }

            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["color.hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }
        }

        // ── the looks: one family, or the favourites ──────────────
        CardGroup {
            visible: root.tab === "favorites"
                     || (root.tab === "colors" && root.section !== "")
            title: root.tab === "favorites"
                ? (Tr.s["color.tab.favorites"] || "")
                : root.sectionLabel(root.section)

            // The way back sits first: a sub-page without an exit teaches
            // the user to close the whole panel instead.
            RowLayout {
                visible: root.tab === "colors"
                Layout.fillWidth: true
                spacing: Theme.m.space2
                IconButton {
                    size: 24; iconSize: 14
                    icon: Icons.chevronDown
                    rotation: 90
                    label: Tr.s["color.back"] || ""
                    onTriggered: root.section = ""
                }
                Text {
                    Layout.fillWidth: true
                    text: Tr.s["color.drag_hint"] || ""
                    color: Theme.c.textDisabled
                    font.pixelSize: Theme.m.fontSizeXs
                    wrapMode: Text.WordWrap
                }
            }

            Text {
                visible: root.tab === "favorites" && root.gridEffects.length === 0
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["color.fav_empty"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            Flow {
                Layout.fillWidth: true
                spacing: Theme.m.space2

                Repeater {
                    model: root.gridEffects
                    delegate: Item {
                        id: look
                        required property var modelData
                        objectName: "colorLook_" + modelData.id
                        width: 104
                        height: 82

                        Rectangle {
                            id: lookCard
                            width: 104
                            height: 60
                            radius: Theme.m.radiusSm
                            clip: true
                            color: Theme.c.clipEffect
                            border.width: 1
                            border.color: lookHover.hovered
                                ? Theme.c.accent : Qt.rgba(1, 1, 1, 0.12)
                            opacity: root.draggingEffect === look.modelData.id
                                ? 0.4 : 1.0

                            Image {
                                anchors.fill: parent
                                asynchronous: true
                                fillMode: Image.PreserveAspectCrop
                                sourceSize.width: 160
                                source: root.thumbSource(look.modelData.id)
                            }

                            // ── the star (shared StarButton) ──────
                            StarButton {
                                objectName: "star_" + look.modelData.id
                                anchors.top: parent.top
                                anchors.right: parent.right
                                anchors.margins: 2
                                starred: root.isFavorite(look.modelData.id)
                                onToggled: Actions.invoke(
                                    "color.toggle_favorite",
                                    { effect_id: look.modelData.id })
                            }
                        }
                        Text {
                            anchors.top: lookCard.bottom
                            anchors.topMargin: 3
                            width: parent.width
                            text: look.modelData.name
                            color: Theme.c.textMuted
                            font.pixelSize: Theme.m.fontSizeXs
                            elide: Text.ElideRight
                            horizontalAlignment: Text.AlignHCenter
                        }

                        HoverHandler { id: lookHover; cursorShape: Qt.OpenHandCursor }
                        DragHandler {
                            id: lookDrag
                            target: null
                            // The panel scrolls in a Flickable; without
                            // this the list steals the gesture.
                            grabPermissions:
                                PointerHandler.CanTakeOverFromAnything
                            onCentroidChanged: {
                                if (active)
                                    root.dragScenePos = centroid.scenePosition;
                            }
                            onActiveChanged: {
                                if (active) {
                                    root.dragScenePos = centroid.scenePosition;
                                    root.draggingEffect = look.modelData.id;
                                    return;
                                }
                                // drop() BEFORE clearing: turning Drag.active
                                // off without it is a CANCEL, and the drop
                                // area under the pointer never hears a thing.
                                dragGhost.Drag.drop();
                                root.draggingEffect = "";
                            }
                        }
                    }
                }
            }
        }
    }
}
