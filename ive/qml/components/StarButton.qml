// The favourite star every catalogue card carries, top right.
//
// Hollow when not starred, gold when starred; sits on a dark round
// plate so it reads on any imagery. The caller binds `starred` and acts
// on `toggled` (each panel has its own toggle action, so the persisted
// lists stay separate). One component, three panels - colours,
// stickers, transitions - so they can never drift apart.
import QtQuick
import QtQuick.Shapes

Item {
    id: root

    property bool starred: false
    signal toggled

    width: 22
    height: 22
    z: 5

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: "#66000000"
        visible: root.starred || hover.hovered
    }
    Shape {
        anchors.centerIn: parent
        width: 14
        height: 14
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: root.starred ? "#FFC53D" : "#E6FFFFFF"
            strokeWidth: 1.3
            fillColor: root.starred ? "#FFC53D" : "transparent"
            joinStyle: ShapePath.RoundJoin
            scale: Qt.size(14 / 24, 14 / 24)
            PathSvg {
                path: "M12 2.6l2.8 5.9 6.4.8-4.7 4.4 1.2 6.3-5.7-3.1-5.7 3.1 1.2-6.3-4.7-4.4 6.4-.8z"
            }
        }
    }
    HoverHandler {
        id: hover
        cursorShape: Qt.PointingHandCursor
    }
    TapHandler {
        onTapped: root.toggled()
    }
}
