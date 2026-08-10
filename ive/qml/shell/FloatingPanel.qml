// The single floating panel. Every option, effect and setting appears here.
//
// Glass, and floating OVER the video rather than beside it. It carries dense
// controls, so it uses the secondary-text scrim - the strictest tier - which
// keeps labels legible over any frame while still showing the video through.
//
// It retracts into a 48x48 square when the pointer leaves - but NEVER while:
//   1. a slider or handle is being dragged
//   2. something inside has keyboard focus
//   3. it is pinned
//   4. the pointer is over it
//   5. fewer than `hideDelay` ms have passed since the pointer left
//
// Those rules are the feature, not polish on top of it: without them the panel
// closes while you are using it, and the whole idea becomes an annoyance.
import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import components
import IVE

Item {
    id: root

    /*! Item sampled for the blur; see GlassSurface. */
    property Item sceneSource: null

    /*! Section currently shown; "" means closed. */
    property string section: ""
    property string title: ""
    property string icon: ""

    signal closeRequested()

    // ── retraction state ──────────────────────────────────────────
    readonly property bool pinned: Shell.v.panelPinned
    readonly property bool autohide: Shell.v.panelAutohide
    readonly property int hideDelay: Shell.v.panelHideDelay

    property bool hovered: false
    readonly property bool interacting:
        contentLoader.item && contentLoader.item.interacting !== undefined
            ? contentLoader.item.interacting : false

    // True when anything inside the panel holds keyboard focus.
    readonly property bool focusInside: {
        var win = root.Window.window;
        var item = win ? win.activeFocusItem : null;
        while (item) {
            if (item === root)
                return true;
            item = item.parent;
        }
        return false;
    }

    readonly property bool held: hovered || interacting || focusInside || pinned || !autohide
    property bool collapsed: false

    /*! Reason the panel is being held open; shown in the status strip. */
    readonly property string holdReason:
        !autohide   ? "panel.hold.disabled"
      : pinned      ? "panel.hold.pinned"
      : interacting ? "panel.hold.dragging"
      : focusInside ? "panel.hold.focus"
      : hovered     ? "panel.hold.hover"
                    : "panel.hold.idle"

    onHeldChanged: {
        if (held) {
            hideTimer.stop();
            graceTimer.stop();      // the pointer arrived; the grace is over
            collapsed = false;
        } else if (!graceTimer.running) {
            // Restarting while the grace period is running stacks the two
            // delays, which is what made the retraction feel unpredictable.
            hideTimer.restart();
        }
    }

    Timer {
        id: hideTimer
        interval: root.hideDelay
        onTriggered: if (!root.held) root.collapsed = true
    }

    /*! Open a section and keep it visible long enough to reach with the mouse. */
    function open(sectionKey, sectionTitle, sectionIcon) {
        section = sectionKey;
        title = sectionTitle;
        icon = sectionIcon;
        collapsed = false;
        hideTimer.stop();
        graceTimer.restart();
    }

    // Grace period after opening from the rail: long enough to reach the
    // panel with the mouse. It must not then add its own wait on top of the
    // configured delay, which is why `held` cancels it outright.
    Timer {
        id: graceTimer
        interval: 1200
        onTriggered: if (!root.held) hideTimer.restart()
    }

    /*! Width when open; the caller uses it to pin the docked edge. */
    readonly property real expandedWidth: Theme.m.floatPanelWidth
    /*! True when the panel is docked on the right, so it grows leftwards. */
    readonly property bool dockedRight: Shell.v.railSide === "left"

    width: collapsed ? Theme.m.floatPanelCollapsed : expandedWidth

    // The collapsed square sits on the docked edge, so the panel unfolds away
    // from that edge in one motion instead of jumping.
    transform: Translate {
        x: root.dockedRight && root.collapsed
            ? root.expandedWidth - Theme.m.floatPanelCollapsed : 0
        Behavior on x {
            enabled: !Shell.v.reduceMotion
            NumberAnimation { duration: Theme.m.durNormal; easing.type: Easing.OutCubic }
        }
    }
    /*! How far down the panel may grow. Set by the shell to the top of the
        timeline, so a long panel uses the room it actually has instead of
        scrolling inside an arbitrary fraction of the window. */
    property real availableHeight: parent ? parent.height * 0.72 : 600

    height: collapsed
        ? Theme.m.floatPanelCollapsed
        : Math.min(implicitContentHeight, availableHeight)
    readonly property real implicitContentHeight:
        header.height + (contentLoader.item ? contentLoader.item.implicitHeight : 0)
        + status.height + Theme.m.space3 * 2

    Behavior on width {
        enabled: !Shell.v.reduceMotion
        NumberAnimation { duration: Theme.m.durNormal; easing.type: Easing.OutCubic }
    }
    Behavior on height {
        enabled: !Shell.v.reduceMotion
        NumberAnimation { duration: Theme.m.durNormal; easing.type: Easing.OutCubic }
    }

    HoverHandler {
        onHoveredChanged: root.hovered = hovered
    }

    // The only element in the shell that casts a shadow: that is what makes it
    // read as floating above everything else.
    Rectangle {
        anchors.fill: parent
        anchors.margins: -1
        radius: Theme.m.floatPanelRadius + 1
        color: "transparent"
        border.width: 1
        border.color: Qt.rgba(0, 0, 0, 0.45)
        opacity: 0.6
    }

    GlassSurface {
        anchors.fill: parent
        sceneSource: root.sceneSource
        originX: root.x
        originY: root.y
        radius: Theme.m.floatPanelRadius
        // Densest surface in the shell, so it takes the strictest tier.
        scrim: Theme.m.scrimTextSecondary
    }

    Item {
        id: surface
        anchors.fill: parent
        clip: true

        // ── collapsed badge ───────────────────────────────────────
        Glyph {
            anchors.centerIn: parent
            visible: root.collapsed
            width: Theme.m.toolRailIcon
            height: Theme.m.toolRailIcon
            path: root.icon
            color: Theme.c.accent
        }

        // ── header ────────────────────────────────────────────────
        RowLayout {
            id: header
            visible: !root.collapsed
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: 42
            spacing: Theme.m.space2

            Item { width: Theme.m.space3 - Theme.m.space2; height: 1 }

            Text {
                Layout.fillWidth: true
                Layout.leftMargin: Theme.m.space2
                text: root.title.toUpperCase()
                color: Theme.c.textMuted
                font.pixelSize: Theme.m.fontSizeSm
                font.letterSpacing: 1.0
                elide: Text.ElideRight
            }

            IconButton {
                size: 26
                iconSize: 15
                icon: Icons.pin
                checked: root.pinned
                label: root.pinned ? (Tr.s["panel.unpin"] || "") : (Tr.s["panel.pin"] || "")
                tipSide: Shell.v.railSide === "left" ? "left" : "right"
                onTriggered: Actions.invoke("settings.set",
                                            { key: "shell.panel_pinned",
                                              value: root.pinned ? "false" : "true" })
            }
            IconButton {
                size: 26
                iconSize: 15
                icon: Icons.close
                label: Tr.s["panel.close"] || ""
                tipSide: Shell.v.railSide === "left" ? "left" : "right"
                onTriggered: root.closeRequested()
            }
            Item { width: Theme.m.space1; height: 1 }
        }

        Rectangle {
            visible: !root.collapsed
            anchors.top: header.bottom
            width: parent.width
            height: 1
            color: Qt.alpha(Theme.c.glassOn, 0.12)
        }

        // ── content ───────────────────────────────────────────────
        Flickable {
            id: scroll
            visible: !root.collapsed
            anchors {
                top: header.bottom
                left: parent.left
                right: parent.right
                bottom: status.top
                topMargin: 1
            }
            clip: true
            contentHeight: contentLoader.item ? contentLoader.item.implicitHeight : 0
            boundsBehavior: Flickable.StopAtBounds
            HoverHandler { id: scrollHover }

            Loader {
                id: contentLoader
                width: scroll.width
                source: {
                    switch (root.section) {
                    case "settings": return "SettingsContent.qml";
                    case "new":      return "NewProjectContent.qml";
                    case "project":  return "ProjectContent.qml";
                    case "export":   return "ExportContent.qml";
                    case "color":    return "ColorContent.qml";
                    case "stickers": return "StickersContent.qml";
                    default: return "";
                    }
                }
                onStatusChanged: if (status === Loader.Error)
                    console.warn("Panel section failed to load:", root.section)
            }

            // Scroll indicator. Without it the panel silently hides half its
            // content: the transparency sliders sat below the fold for a whole
            // session because nothing said there was more to see.
            Rectangle {
                id: scrollBar
                anchors.right: parent.right
                anchors.rightMargin: 2
                width: 3
                radius: 1.5
                color: Theme.c.borderStrong
                visible: scroll.contentHeight > scroll.height + 1
                opacity: scroll.moving || scrollHover.hovered ? 0.9 : 0.35
                height: Math.max(28, scroll.height * scroll.height
                                     / Math.max(1, scroll.contentHeight))
                y: scroll.contentHeight > scroll.height
                    ? (scroll.contentY / (scroll.contentHeight - scroll.height))
                      * (scroll.height - height)
                    : 0
                Behavior on opacity {
                    enabled: !Shell.v.reduceMotion
                    NumberAnimation { duration: Theme.m.durFast }
                }
            }

            // Placeholder for the sections that arrive in later stages.
            Text {
                visible: contentLoader.source === "" && root.section !== ""
                anchors.centerIn: parent
                width: parent.width - Theme.m.space5 * 2
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: root.title
                color: Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeMd
            }
        }

        // ── status strip: why the panel is staying open ───────────
        Item {
            id: status
            visible: !root.collapsed
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            height: 26

            Rectangle {
                anchors.top: parent.top
                width: parent.width
                height: 1
                color: Theme.c.border
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: Theme.m.space3
                text: Tr.s[root.holdReason] || ""
                color: root.held && root.autohide ? Theme.c.accent : Theme.c.textDisabled
                font.pixelSize: Theme.m.fontSizeXs
                font.family: "monospace"
            }
        }
    }
}
