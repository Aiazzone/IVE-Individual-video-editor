// Continuous value control.
//
// `moved` fires while dragging (live preview); `committed` fires once on
// release. Only the second one should produce an undo step - see the
// coalescing rule in docs/ARCHITECTURE.md.
//
// `pressed` is watched by the floating panel: it must never retract while the
// user is dragging (docs/UI_SHELL.md section 7, rule 1).
import QtQuick
import IVE

Item {
    id: root

    property real from: 0
    property real to: 100
    property real value: 0
    property real stepSize: 1
    property string label: ""

    readonly property bool pressed: drag.active

    // While dragging, the handle follows the pointer rather than the bound
    // value: the binding only catches up once the change is applied, and
    // reading it back mid-drag reports the old value.
    property real _live: NaN
    readonly property real effectiveValue: isNaN(_live) ? value : _live

    // Must work with an INVERTED range (from > to), which is how the
    // transparency slider reads left-to-right as "more see-through". The old
    // `to > from ? ... : 0` silently returned 0 for those, pinning the handle
    // to the left: the control still worked, it just looked broken, which is
    // worse than not working.
    readonly property real position: {
        var span = to - from;
        if (span === 0)
            return 0;
        return Math.max(0, Math.min(1, (effectiveValue - from) / span));
    }

    signal moved(real value)
    signal committed(real value)

    implicitWidth: 200
    implicitHeight: 22
    activeFocusOnTab: true

    Accessible.role: Accessible.Slider
    Accessible.name: root.label

    function _valueAt(px) {
        var t = Math.max(0, Math.min(1, px / Math.max(1, root.width)));
        var raw = root.from + t * (root.to - root.from);
        return root.stepSize > 0
            ? Math.round(raw / root.stepSize) * root.stepSize
            : raw;
    }

    Rectangle {                       // groove
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width
        height: 4
        radius: 2
        color: Theme.c.borderStrong
    }

    Rectangle {                       // filled part
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width * root.position
        height: 4
        radius: 2
        color: Theme.c.accent
    }

    Rectangle {                       // handle
        id: handle
        width: 14
        height: 14
        radius: 7
        color: "#FFFFFF"
        anchors.verticalCenter: parent.verticalCenter
        x: root.position * (root.width - width)
        border.width: root.activeFocus ? 2 : 0
        border.color: Theme.c.accent
    }

    DragHandler {
        id: drag
        target: null
        xAxis.enabled: true
        yAxis.enabled: false
        onCentroidChanged: {
            if (!active)
                return;
            root._live = root._valueAt(centroid.position.x);
            root.moved(root._live);
        }
        onActiveChanged: {
            if (active)
                return;
            var endValue = isNaN(root._live) ? root.value : root._live;
            root._live = NaN;
            root.committed(endValue);
        }
    }

    TapHandler {
        onTapped: function (point) {
            var target = root._valueAt(point.position.x);
            root.moved(target);
            root.committed(target);
        }
    }

    Keys.onPressed: function (event) {
        var step = event.modifiers & Qt.ShiftModifier ? root.stepSize * 10 : root.stepSize;
        // `from` may be greater than `to` on an inverted slider, so clamp
        // against the actual ends rather than assuming an order.
        var lo = Math.min(root.from, root.to);
        var hi = Math.max(root.from, root.to);
        var dir = root.to >= root.from ? 1 : -1;
        if (event.key === Qt.Key_Left || event.key === Qt.Key_Down) {
            var down = Math.max(lo, Math.min(hi, root.value - step * dir));
            root.moved(down);
            root.committed(down);
            event.accepted = true;
        } else if (event.key === Qt.Key_Right || event.key === Qt.Key_Up) {
            var up = Math.max(lo, Math.min(hi, root.value + step * dir));
            root.moved(up);
            root.committed(up);
            event.accepted = true;
        }
    }

    HoverHandler { cursorShape: Qt.PointingHandCursor }
}
