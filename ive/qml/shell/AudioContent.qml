// The sound of the selected clip, and the audio-effect catalogue.
//
// Tapping a clip with sound on the timeline (its video lane or its audio
// lane) opens this panel on it: volume, fade in / fade out, mute - then
// the effects, as cards grouped by family, one tap applies (one undo
// step), "As recorded" takes the effect off. Effects are JSON recipes
// (docs/AUDIO.md): the same ops play in the preview and in the export.
import QtQuick
import QtQuick.Layouts
import components
import IVE

Item {
    id: root

    implicitHeight: column.implicitHeight + Theme.m.space3 * 2

    /*! "clip" = the selected clip's sound and effects; "music" = the
        library. Selecting a clip with sound flips to "clip". */
    property string tab: "clip"
    /*! Music library: the open category ("" = all), and the repeat switch. */
    property string musicCategory: ""
    property bool coverCut: true

    onAudioClipChanged: if (audioClip !== null) tab = "clip"

    /*! The selected clip WITH sound, or null - live from the project. */
    readonly property var audioClip: {
        var id = Shell.v.selectedClipId || "";
        if (id === "")
            return null;
        var clips = Project.timelineClips;
        for (var i = 0; i < clips.length; i++)
            if (clips[i].id === id && clips[i].mediaId && clips[i].hasAudio)
                return clips[i];
        return null;
    }

    function isFavorite(id) {
        return AudioFx.favorites.indexOf(id) >= 0;
    }
    function sectionLabel(id) {
        return Tr.s["audio.section." + id] || id;
    }
    function applyEffect(id) {
        if (audioClip === null)
            return;
        Actions.invoke("timeline.set_clip_audio_effect",
                       { clip_id: audioClip.id, effect_id: id });
    }
    function commitFades(fadeIn, fadeOut) {
        if (audioClip === null)
            return;
        Actions.invoke("timeline.set_clip_fades", {
            clip_id: audioClip.id,
            fade_in: Math.round(fadeIn * 10) / 10,
            fade_out: Math.round(fadeOut * 10) / 10
        });
    }

    readonly property var favoriteEffects: {
        var out = [];
        var all = AudioFx.effects;
        var stars = AudioFx.favorites;
        for (var k = 0; k < stars.length; k++)
            for (var i = 0; i < all.length; i++)
                if (all[i].id === stars[k])
                    out.push(all[i]);
        return out;
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
                { value: "clip", text: Tr.s["audio.tab.clip"] || "" },
                { value: "music", text: Tr.s["audio.tab.music"] || "" }
            ]
            onPicked: function (v) { root.tab = v; }
        }

        // ── the selected clip's sound ─────────────────────────────
        CardGroup {
            visible: root.tab === "clip"
            title: Tr.s["audio.clip_group"] || ""

            Text {
                visible: root.audioClip === null
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["audio.no_selection"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            Text {
                visible: root.audioClip !== null
                Layout.fillWidth: true
                text: root.audioClip !== null ? root.audioClip.name : ""
                color: Theme.c.text
                font.pixelSize: Theme.m.fontSizeSm + 1
                elide: Text.ElideRight
            }

            RowLayout {
                visible: root.audioClip !== null
                Layout.fillWidth: true
                spacing: Theme.m.space2
                Text {
                    Layout.preferredWidth: 96
                    text: Tr.s["audio.volume"] || ""
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeXs
                    elide: Text.ElideRight
                }
                AppSlider {
                    id: volumeSlider
                    objectName: "audio_volume_slider"
                    Layout.fillWidth: true
                    from: 0; to: 2; stepSize: 0.05
                    label: Tr.s["audio.volume"] || ""
                    value: root.audioClip !== null ? root.audioClip.volume : 1
                    onCommitted: function (v) {
                        if (root.audioClip !== null)
                            Actions.invoke("timeline.set_clip_volume", {
                                clip_id: root.audioClip.id,
                                volume: Math.round(v * 100) / 100
                            });
                    }
                }
                Text {
                    Layout.preferredWidth: 44
                    horizontalAlignment: Text.AlignRight
                    text: Math.round(volumeSlider.value * 100) + "%"
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeXs
                }
                IconButton {
                    objectName: "audio_mute_toggle"
                    size: 28; iconSize: 15
                    icon: Icons.audio
                    label: Tr.s["audio.mute"] || ""
                    checked: root.audioClip !== null && root.audioClip.muted
                    onTriggered: if (root.audioClip !== null)
                        Actions.invoke("timeline.set_clip_muted", {
                            clip_id: root.audioClip.id,
                            muted: !root.audioClip.muted
                        });
                }
            }

            RowLayout {
                visible: root.audioClip !== null
                Layout.fillWidth: true
                spacing: Theme.m.space2
                Text {
                    Layout.preferredWidth: 96
                    text: Tr.s["audio.fade_in"] || ""
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeXs
                    elide: Text.ElideRight
                }
                AppSlider {
                    id: fadeInSlider
                    objectName: "audio_fade_in_slider"
                    Layout.fillWidth: true
                    from: 0
                    to: root.audioClip !== null
                        ? Math.max(0.5, Math.min(10, root.audioClip.duration / 2)) : 5
                    stepSize: 0.1
                    label: Tr.s["audio.fade_in"] || ""
                    value: root.audioClip !== null ? root.audioClip.fadeIn : 0
                    onCommitted: function (v) {
                        root.commitFades(v, root.audioClip.fadeOut);
                    }
                }
                Text {
                    Layout.preferredWidth: 44
                    horizontalAlignment: Text.AlignRight
                    text: fadeInSlider.value.toFixed(1) + "s"
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeXs
                }
            }
            RowLayout {
                visible: root.audioClip !== null
                Layout.fillWidth: true
                spacing: Theme.m.space2
                Text {
                    Layout.preferredWidth: 96
                    text: Tr.s["audio.fade_out"] || ""
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeXs
                    elide: Text.ElideRight
                }
                AppSlider {
                    id: fadeOutSlider
                    objectName: "audio_fade_out_slider"
                    Layout.fillWidth: true
                    from: 0
                    to: root.audioClip !== null
                        ? Math.max(0.5, Math.min(10, root.audioClip.duration / 2)) : 5
                    stepSize: 0.1
                    label: Tr.s["audio.fade_out"] || ""
                    value: root.audioClip !== null ? root.audioClip.fadeOut : 0
                    onCommitted: function (v) {
                        root.commitFades(root.audioClip.fadeIn, v);
                    }
                }
                Text {
                    Layout.preferredWidth: 44
                    horizontalAlignment: Text.AlignRight
                    text: fadeOutSlider.value.toFixed(1) + "s"
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeXs
                }
            }
        }

        // ── ducking: the bed dips under the cut's speech ──────────
        // Only for Music-lane clips: the choice and the amount are the
        // clip's; HOW speech is detected is a global preference
        // (Settings → Audio).
        CardGroup {
            visible: root.tab === "clip" && root.audioClip !== null
                     && root.audioClip.track === 4
            title: Tr.s["audio.duck_group"] || ""

            SwitchRow {
                objectName: "audio_duck_switch"
                Layout.fillWidth: true
                label: Tr.s["audio.duck"] || ""
                checked: root.audioClip !== null && root.audioClip.duck
                onToggled: function (v) {
                    if (root.audioClip !== null)
                        Actions.invoke("timeline.set_clip_ducking", {
                            clip_id: root.audioClip.id, enabled: v,
                            depth_db: root.audioClip.duckDb
                        });
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.m.space2
                enabled: root.audioClip !== null && root.audioClip.duck
                opacity: enabled ? 1 : 0.5
                Text {
                    Layout.preferredWidth: 96
                    text: Tr.s["audio.duck_depth"] || ""
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeXs
                    elide: Text.ElideRight
                }
                AppSlider {
                    id: duckSlider
                    objectName: "audio_duck_slider"
                    Layout.fillWidth: true
                    from: 3; to: 24; stepSize: 1
                    label: Tr.s["audio.duck_depth"] || ""
                    value: root.audioClip !== null ? root.audioClip.duckDb : 12
                    onCommitted: function (v) {
                        if (root.audioClip !== null)
                            Actions.invoke("timeline.set_clip_ducking", {
                                clip_id: root.audioClip.id,
                                enabled: root.audioClip.duck,
                                depth_db: Math.round(v)
                            });
                    }
                }
                Text {
                    Layout.preferredWidth: 44
                    horizontalAlignment: Text.AlignRight
                    text: "-" + Math.round(duckSlider.value) + " dB"
                    color: Theme.c.textMuted
                    font.pixelSize: Theme.m.fontSizeXs
                }
            }
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: (Tr.s["audio.duck_hint"] || "")
                      .replace("{m}", Tr.s["settings.ducking." + Shell.v.duckingMode]
                                      || Shell.v.duckingMode)
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }
        }

        // ── the effects ───────────────────────────────────────────
        CardGroup {
            visible: root.tab === "clip"
            title: Tr.s["audio.effects_group"] || ""

            // "As recorded": no recipe, and the way back to it.
            Rectangle {
                objectName: "audio_effect_none"
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                radius: Theme.m.radiusMd
                color: root.audioClip !== null && root.audioClip.audioEffectId === ""
                    ? Qt.alpha(Theme.c.accent, 0.18)
                    : (noneHover.hovered ? Theme.c.bgHover
                                         : Qt.alpha(Theme.c.glassOn, 0.05))
                border.width: root.audioClip !== null
                              && root.audioClip.audioEffectId === "" ? 1 : 0
                border.color: Theme.c.accent
                opacity: root.audioClip !== null ? 1 : 0.5
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.m.space3
                    anchors.rightMargin: Theme.m.space3
                    Glyph {
                        width: 14; height: 14
                        path: Icons.close
                        color: Theme.c.textDisabled
                    }
                    Text {
                        Layout.fillWidth: true
                        text: Tr.s["audio.none"] || ""
                        color: Theme.c.text
                        font.pixelSize: Theme.m.fontSizeSm + 1
                    }
                }
                HoverHandler { id: noneHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: root.applyEffect("") }
            }

            // Favourites first, then every family.
            Repeater {
                model: [{ id: "favorites", effects: root.favoriteEffects }]
                       .concat(AudioFx.sections.map(function (s) {
                           return { id: s.id, effects: AudioFx.effects.filter(
                               function (e) { return e.section === s.id; }) };
                       }))
                delegate: ColumnLayout {
                    id: family
                    required property var modelData
                    visible: modelData.effects.length > 0
                    Layout.fillWidth: true
                    spacing: Theme.m.space1

                    Text {
                        Layout.topMargin: Theme.m.space1
                        text: family.modelData.id === "favorites"
                            ? (Tr.s["audio.favorites"] || "")
                            : root.sectionLabel(family.modelData.id)
                        color: Theme.c.textMuted
                        font.pixelSize: Theme.m.fontSizeXs
                        font.bold: true
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: Theme.m.space2

                        Repeater {
                            model: family.modelData.effects
                            delegate: Rectangle {
                                id: card
                                required property var modelData
                                objectName: "audio_effect_" + modelData.id
                                width: 104
                                height: 56
                                radius: Theme.m.radiusSm
                                readonly property bool current:
                                    root.audioClip !== null
                                    && root.audioClip.audioEffectId === modelData.id
                                color: current ? Qt.alpha(Theme.c.accent, 0.18)
                                     : (cardHover.hovered ? Theme.c.bgHover
                                        : Qt.alpha(Theme.c.glassOn, 0.06))
                                border.width: current ? 2 : 1
                                border.color: current || cardHover.hovered
                                    ? Theme.c.accent
                                    : Qt.alpha(Theme.c.glassOn, 0.12)
                                opacity: root.audioClip !== null ? 1 : 0.6

                                Text {
                                    anchors { left: parent.left; right: parent.right
                                              bottom: parent.bottom
                                              margins: Theme.m.space2 }
                                    text: card.modelData.name
                                    color: Theme.c.text
                                    font.pixelSize: Theme.m.fontSizeXs
                                    wrapMode: Text.WordWrap
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                }
                                StarButton {
                                    objectName: "audio_star_" + card.modelData.id
                                    anchors.top: parent.top
                                    anchors.right: parent.right
                                    anchors.margins: 2
                                    starred: root.isFavorite(card.modelData.id)
                                    onToggled: Actions.invoke(
                                        "audio.toggle_favorite",
                                        { effect_id: card.modelData.id })
                                }
                                HoverHandler { id: cardHover
                                               cursorShape: Qt.PointingHandCursor }
                                TapHandler {
                                    onTapped: root.applyEffect(card.modelData.id)
                                }
                            }
                        }
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["audio.hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }
        }
        // ── the music library ─────────────────────────────────────
        // Tracks from installed packs and user_data/music, by category.
        // Preview plays the file on its own (the transport pauses);
        // "Add at playhead" lays it on the Music lane, repeating until
        // the cut ends when the switch is on.
        CardGroup {
            visible: root.tab === "music"
            title: Tr.s["music.group"] || ""

            Text {
                visible: Music.categories.length === 0
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["music.empty"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }

            Flow {
                visible: Music.categories.length > 0
                Layout.fillWidth: true
                spacing: Theme.m.space1

                Repeater {
                    model: [{ id: "", label: Tr.s["music.all"] || "",
                              count: -1 }]
                           .concat(Music.categories.map(function (c) {
                               return { id: c.id, count: c.count,
                                        label: c.mine
                                            ? (Tr.s["music.mine"] || "")
                                            : c.id.charAt(0).toUpperCase()
                                              + c.id.slice(1) };
                           }))
                    delegate: Rectangle {
                        id: chip
                        required property var modelData
                        objectName: "music_cat_" + (modelData.id || "all")
                        readonly property bool current:
                            root.musicCategory === modelData.id
                        width: chipRow.implicitWidth + Theme.m.space3 * 2
                        height: 26
                        radius: 999
                        color: current ? Qt.alpha(Theme.c.accent, 0.2)
                             : Qt.alpha(Theme.c.glassOn, 0.06)
                        border.width: 1
                        border.color: current ? Theme.c.accent
                                              : Qt.alpha(Theme.c.glassOn, 0.12)
                        Row {
                            id: chipRow
                            anchors.centerIn: parent
                            spacing: 6
                            Text {
                                text: chip.modelData.label
                                color: chip.current ? Theme.c.text
                                                    : Theme.c.textMuted
                                font.pixelSize: Theme.m.fontSizeXs
                                font.bold: chip.current
                            }
                            Text {
                                visible: chip.modelData.count >= 0
                                text: chip.modelData.count
                                color: Theme.c.textDisabled
                                font.pixelSize: Theme.m.fontSizeXs
                            }
                        }
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        TapHandler {
                            onTapped: root.musicCategory = chip.modelData.id
                        }
                    }
                }
            }

            SwitchRow {
                visible: Music.categories.length > 0
                Layout.fillWidth: true
                label: Tr.s["music.cover"] || ""
                checked: root.coverCut
                onToggled: function (v) { root.coverCut = v; }
            }

            Repeater {
                model: Music.tracks(root.musicCategory)
                delegate: Rectangle {
                    id: row
                    required property var modelData
                    objectName: "music_track_" + modelData.id
                    Layout.fillWidth: true
                    Layout.preferredHeight: 52
                    radius: Theme.m.radiusMd
                    readonly property bool previewing:
                        Music.previewing === modelData.id
                    color: previewing ? Qt.alpha(Theme.c.accent, 0.14)
                         : (rowHover.hovered ? Theme.c.bgHover
                            : Qt.alpha(Theme.c.glassOn, 0.05))

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.m.space2
                        anchors.rightMargin: Theme.m.space2
                        spacing: Theme.m.space2

                        IconButton {
                            objectName: "music_play_" + row.modelData.id
                            size: 30; iconSize: 16
                            icon: row.previewing ? Icons.pause : Icons.play
                            label: row.previewing
                                ? (Tr.s["music.stop"] || "")
                                : (Tr.s["music.preview"] || "")
                            checked: row.previewing
                            onTriggered: Music.preview(row.modelData.id)
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Text {
                                Layout.fillWidth: true
                                text: row.modelData.title
                                color: Theme.c.text
                                font.pixelSize: Theme.m.fontSizeSm + 1
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                text: [row.modelData.artist,
                                       row.modelData.duration > 0
                                           ? Math.floor(row.modelData.duration / 60)
                                             + ":" + ("0" + Math.floor(
                                                 row.modelData.duration % 60)).slice(-2)
                                           : "",
                                       row.modelData.bpm > 0
                                           ? row.modelData.bpm + " bpm" : "",
                                       row.modelData.vocals ? ""
                                           : (Tr.s["music.no_vocals"] || ""),
                                       row.modelData.license]
                                      .filter(function (v) { return v !== ""; })
                                      .join(" · ")
                                color: Theme.c.textDisabled
                                font.pixelSize: Theme.m.fontSizeXs
                                elide: Text.ElideRight
                            }
                        }
                        StarButton {
                            objectName: "music_star_" + row.modelData.id
                            starred: Music.favorites.indexOf(row.modelData.id) >= 0
                            onToggled: Actions.invoke("music.toggle_favorite",
                                                      { track_id: row.modelData.id })
                        }
                        IconButton {
                            objectName: "music_add_" + row.modelData.id
                            size: 30; iconSize: 16
                            icon: Icons.plus
                            label: Tr.s["music.add_at_playhead"] || ""
                            enabled: Project.isOpen
                            onTriggered: {
                                Music.stop();
                                Actions.invoke("timeline.place_music", {
                                    track_id: row.modelData.id,
                                    at: Playback.hasMedia
                                        ? Playback.positionSeconds : 0,
                                    cover: root.coverCut
                                });
                            }
                        }
                    }
                    HoverHandler { id: rowHover }
                }
            }

            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tr.s["music.licence_hint"] || ""
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                lineHeight: 1.35
            }
        }
    }
}
