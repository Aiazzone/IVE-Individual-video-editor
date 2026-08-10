// Stand-in for the video preview until stage 2.
//
// It is not decoration: the ambient backdrop and the glass surfaces need real
// content behind them to be judged, and a flat grey would hide exactly the
// legibility problems this shell has to solve. Replace the whole item with
// PreviewItem (ui/preview_item.py) when the video engine lands - nothing else
// in the shell changes.
import QtQuick
import QtQuick.Shapes
import IVE

Item {
    id: root

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.00; color: "#16222E" }
            GradientStop { position: 0.38; color: "#33506A" }
            GradientStop { position: 0.62; color: "#8FB0C4" }
            GradientStop { position: 0.63; color: "#26424F" }
            GradientStop { position: 1.00; color: "#0F1C25" }
        }
    }

    // Sun glow, high key: this is what stresses the scrim thresholds.
    Rectangle {
        width: parent.height * 0.68
        height: width
        radius: width / 2
        x: parent.width * 0.72 - width / 2
        y: parent.height * 0.30 - height / 2
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#D9FFE8BE" }
            GradientStop { position: 1.0; color: "#00FFE8BE" }
        }
    }

    Shape {                         // distant ridge
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: "#3C5468"
            strokeColor: "transparent"
            startX: 0; startY: root.height * 0.62
            PathLine { x: root.width * 0.18; y: root.height * 0.44 }
            PathLine { x: root.width * 0.34; y: root.height * 0.58 }
            PathLine { x: root.width * 0.52; y: root.height * 0.38 }
            PathLine { x: root.width * 0.74; y: root.height * 0.56 }
            PathLine { x: root.width; y: root.height * 0.46 }
            PathLine { x: root.width; y: root.height * 0.62 }
            PathLine { x: 0; y: root.height * 0.62 }
        }
    }

    Shape {                         // near ridge
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: "#22323F"
            strokeColor: "transparent"
            startX: 0; startY: root.height * 0.62
            PathLine { x: root.width * 0.12; y: root.height * 0.52 }
            PathLine { x: root.width * 0.28; y: root.height * 0.62 }
            PathLine { x: root.width * 0.44; y: root.height * 0.47 }
            PathLine { x: root.width * 0.62; y: root.height * 0.62 }
            PathLine { x: root.width * 0.82; y: root.height * 0.50 }
            PathLine { x: root.width; y: root.height * 0.62 }
            PathLine { x: 0; y: root.height * 0.62 }
        }
    }

    // Water ripples.
    Repeater {
        model: 9
        delegate: Rectangle {
            required property int index
            x: root.width * (0.05 + (index % 3) * 0.28)
            y: root.height * (0.66 + index * 0.033)
            width: root.width * (0.18 + (index % 4) * 0.09)
            height: 1
            color: "#FFFFFF"
            opacity: 0.12
        }
    }

    // Sun reflection on the water.
    Rectangle {
        x: root.width * 0.72 - width / 2
        y: root.height * 0.63
        width: root.width * 0.07
        height: root.height * 0.37
        color: "#33FFE8BE"
    }

    // Empty state, honest about what this is. Kept above centre so the
    // transport pill does not land on top of it.
    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height * 0.17
        spacing: Theme.m.space2
        opacity: 0.92

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Tr.s["placeholder.title"] || ""
            color: "#FFFFFF"
            font.pixelSize: Theme.m.fontSizeXl
            style: Text.Raised
            styleColor: "#000000"
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Tr.s["placeholder.hint"] || ""
            color: "#DDFFFFFF"
            font.pixelSize: Theme.m.fontSizeMd
            style: Text.Raised
            styleColor: "#000000"
        }
    }
}
