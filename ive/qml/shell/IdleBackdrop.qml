// The backdrop behind the empty state: the PS4-menu wave field, built as a
// fragment shader (shaders/waves.frag, compiled to .qsb next to it).
//
// Why a shader and not geometry: a polyline is segments, and on slow wide
// curves the eye finds every one of them. The shader evaluates the sines
// PER PIXEL on the GPU, so the ribbons are as smooth as the screen and the
// CPU does nothing but bump one float per tick.
//
// The motion is an ENDLESS phase, not a loop: `time` grows forever and the
// sines wrap it naturally, so there is no restart for the eye to catch.
import QtQuick
import IVE

Item {
    id: root

    property real intensity: 1.0

    /*! Seconds of animation time; grows forever, wrapped by the sines. */
    property real phase: 0

    Timer {
        interval: 33                 // ~30 fps; only runs while on show
        repeat: true
        running: root.visible && !Shell.v.reduceMotion
        onTriggered: root.phase += 0.033
    }

    // Painted ground behind the shader, and the whole backdrop when the
    // shader cannot load (an exotic GPU stack): the window must never be
    // a black hole.
    //
    // The colours are FIXED, not themed, on purpose: this is the app's
    // opening image - its identity, like the PS4's own wave field - and
    // switching to the light theme must not repaint it (reported: "ho
    // messo la ui chiara e ha cambiato tutto il colore delle onde").
    // The glass panels above it stay themed; the stage does not.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#232b3a" }
            GradientStop { position: 1.0; color: "#12161f" }
        }
    }

    ShaderEffect {
        anchors.fill: parent
        opacity: root.intensity
        fragmentShader: Qt.resolvedUrl("shaders/waves.frag.qsb")

        // Names must match the uniform block members in waves.frag.
        property real time: root.phase
        property color topColor: "#232b3a"
        property color bottomColor: "#12161f"
        // Additive ribbon tint: steel blue.
        property color waveColor: "#31435f"
    }
}
