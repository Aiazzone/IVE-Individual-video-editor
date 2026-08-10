// The current frame, enlarged to cover the window, blurred and dimmed.
//
// Why it exists: the timeline sits over the video, so a full-bleed frame would
// permanently hide its bottom band - exactly where subtitles and logos live.
// With the backdrop the sharp video stays entirely inside the free area while
// the window still reads as edge-to-edge. See docs/UI_SHELL.md section 3.
//
// It costs nothing extra to decode: it samples the frame that is already on
// screen, and refreshes at 10 Hz because a 96 px blur hides the difference.
import QtQuick
import QtQuick.Effects
import IVE

Item {
    id: root

    /*! The item holding the sharp frame. */
    property Item sourceItem: null

    readonly property bool _active:
        Shell.v.ambientBackdrop && sourceItem !== null && !Shell.v.windowHidden

    ShaderEffectSource {
        id: grab
        anchors.fill: parent
        sourceItem: root._active ? root.sourceItem : null
        live: false
        visible: false
        hideSource: false
        // Sample at reduced resolution: it is about to be blurred anyway.
        textureSize: Qt.size(Math.max(64, width / 6), Math.max(36, height / 6))
    }

    Timer {
        running: root._active && root.visible
        interval: Math.max(16, 1000 / Math.max(1, Theme.m.glassUpdateHz))
        repeat: true
        onTriggered: grab.scheduleUpdate()
    }

    MultiEffect {
        anchors.fill: parent
        source: grab
        visible: root._active
        blurEnabled: true
        blur: 1.0
        blurMax: Theme.m.backdropBlurRadius
        blurMultiplier: 1.2
        saturation: 0.15
        // This effect covers the WHOLE window, which is the case Qt's
        // documentation singles out: leave autoPaddingEnabled at its default
        // and "the effect grows outside the window / screen", here by
        // blurMax * blurMultiplier on every side.
        autoPaddingEnabled: false
        // Enlarged so the blur has no visible edges at the window border.
        // 12% of the window, not a multiple of the blur radius: this one is
        // deliberate and bounded, and the window clips it.
        scale: 1.12
    }

    // Dim layer. Also the whole background when the backdrop is off.
    Rectangle {
        anchors.fill: parent
        color: Theme.c.bgRoot
        opacity: root._active ? Theme.m.backdropDim : 1.0
        Behavior on opacity {
            enabled: !Shell.v.reduceMotion
            NumberAnimation { duration: Theme.m.durNormal }
        }
    }
}
