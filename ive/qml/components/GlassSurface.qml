// A glass surface: what is behind, blurred, plus a scrim that guarantees
// readability. See docs/UI_SHELL.md section 4.
//
// Two things must be right or the effect is silently wrong:
//
// 1. `originX`/`originY` must be the position of this surface **in window
//    coordinates**. The surface normally fills a component that is itself
//    placed in the window, so the component passes its own x/y. Getting this
//    wrong does not fail loudly: the surface blurs a different part of the
//    scene, which looks plausible until something recognisable drifts through
//    it. mapToItem() is not used because its result is not a reactive binding.
// 2. `sceneSource` must NOT be an ancestor of this item, or the scene graph
//    recurses.
//
// The blur is refreshed at Theme.m.glassUpdateHz (10 Hz), not every frame:
// the content is blurred by tens of pixels, so nobody can tell, and it costs
// six times less than a per-frame refresh.
import QtQuick
import QtQuick.Effects
import IVE

Item {
    id: root

    /*! The item to sample. Must fill the window and not be an ancestor. */
    property Item sceneSource: null
    /*! Position of this surface in window coordinates. See the note above. */
    property real originX: 0
    property real originY: 0
    /*! Corner radius. */
    property real radius: 0
    /*! Scrim strength. Use Theme.m.scrimText for surfaces with text,
        Theme.m.scrimIcons for icon-only surfaces. Never go below the floors. */
    property real scrim: Theme.m.scrimText
    /*! Hairline on the edge facing the video. */
    property bool showBorder: true

    // Resolved once so the bindings below stay readable.
    readonly property bool _glass: Shell.v.glassActive && sceneSource !== null

    // Theme.c holds plain strings. Declaring a `color` property forces the
    // string-to-colour conversion; reading .r/.g/.b straight off the map
    // yields undefined, which silently turns every glass surface black -
    // invisible in a dark theme, obvious in a light one.
    readonly property color _tint: Theme.c.glassTint

    // WHY THE BLUR USED TO ESCAPE THE PANELS
    //
    // MultiEffect.autoPaddingEnabled defaults to TRUE: "the item size is
    // padded automatically based on blurMax and blurMultiplier". Qt's own
    // documentation warns that without turning it off "the effect grows
    // outside the window / screen".
    //
    // This surface additionally used to sample a margin of scene around
    // itself and size the effect to that margin, on the belief that a blur
    // kernel needs something to reach into at the edges. The two paddings
    // stacked, so the effect painted roughly 2 x blurMax beyond the panel,
    // and no mask could catch it: the mask covered the manual padding, never
    // the automatic one Qt adds afterwards.
    //
    // The shape below is the one from Qt's "Qt Quick and Blurred Panels":
    // source exactly the size of the surface, autoPaddingEnabled false, mask
    // for the rounded corners. Edges blur very slightly sharper without a
    // sampled margin; containment is worth more than that.

    ShaderEffectSource {
        id: grab
        anchors.fill: parent
        sourceItem: root._glass ? root.sceneSource : null
        sourceRect: Qt.rect(root.originX + root.x, root.originY + root.y,
                            root.width, root.height)
        live: false              // driven by the timer below, not per frame
        visible: false
        hideSource: false
    }

    Rectangle {
        id: mask
        anchors.fill: parent
        radius: root.radius
        color: "black"
        visible: false
        layer.enabled: true
    }

    MultiEffect {
        anchors.fill: parent
        source: grab
        visible: root._glass
        blurEnabled: true
        // blurMax is the REACH of the kernel in pixels and stays fixed;
        // `blur` is the intensity the user actually sets. Driving the reach
        // from the setting is what made the spill scale with the slider.
        blurMax: Theme.m.glassBlurMax
        blur: Math.max(0, Math.min(1, Theme.m.glassBlurIntensity / 100))
        blurMultiplier: 1.0
        autoPaddingEnabled: false
        saturation: 0.35
        maskEnabled: true
        maskSource: mask
        // Without a spread the mask edge aliases against the rounded corner.
        maskThresholdMin: 0.5
        maskSpreadAtMin: 1.0
    }

    Timer {
        running: root._glass && root.visible
        interval: Math.max(16, 1000 / Math.max(1, Theme.m.glassUpdateHz))
        repeat: true
        onTriggered: grab.scheduleUpdate()
    }

    // ── scrim ─────────────────────────────────────────────────────
    // Without glass the same tint goes solid: the layout never changes,
    // only the look. See docs/UI_SHELL.md section 4.
    Rectangle {
        anchors.fill: parent
        radius: root.radius
        color: Qt.rgba(root._tint.r, root._tint.g, root._tint.b,
                       root._glass ? root.scrim : Theme.m.scrimSolidFallback)
    }

    Rectangle {
        anchors.fill: parent
        radius: root.radius
        color: "transparent"
        border.width: root.showBorder ? 1 : 0
        border.color: Theme.c.glassBorder
        antialiasing: true
    }
}
