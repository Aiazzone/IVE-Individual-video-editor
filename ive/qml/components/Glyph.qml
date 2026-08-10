// A single icon, stroked in the current theme colour.
//
// The path data comes from the Icons singleton and is drawn on a 24x24 grid,
// so the item scales to any size without a second asset.
import QtQuick
import QtQuick.Shapes

Item {
    id: root

    /*! SVG path data, normally one of the Icons.* strings. */
    property string path: ""
    /*! Stroke colour. */
    property color color: "white"
    /*! Stroke width, expressed on the 24 px design grid. */
    property real weight: 1.5
    /*! Drop shadow behind the stroke; needed when the icon sits on video. */
    property bool shadow: false

    implicitWidth: 20
    implicitHeight: 20

    // The shadow is a second, darker copy offset by one pixel. Cheaper than a
    // blur effect and enough to hold the edge on a bright frame.
    Shape {
        anchors.fill: parent
        anchors.topMargin: 1
        visible: root.shadow
        preferredRendererType: Shape.CurveRenderer
        opacity: 0.8
        ShapePath {
            strokeColor: "#000000"
            strokeWidth: root.weight * (root.width / 24) + 0.5
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            scale: Qt.size(root.width / 24, root.height / 24)
            PathSvg { path: root.path }
        }
    }

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: root.color
            strokeWidth: root.weight * (root.width / 24)
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            scale: Qt.size(root.width / 24, root.height / 24)
            PathSvg { path: root.path }
        }
    }
}
