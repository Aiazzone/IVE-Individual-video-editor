// A card preview that comes ALIVE under the mouse.
//
// At rest it shows a still image. On hover it plays a pre-rendered
// FILM STRIP: one PNG holding N frames side by side, generated once by
// the real renderer (the engine blender for transitions, rlottie for
// stickers) and cached on disk. The strip is fetched lazily through
// `provider` on the FIRST hover, so opening a panel costs nothing and
// hovering a card costs one synchronous generation (~tens of ms), then
// only a texture offset per tick - no live rendering, no workers.
import QtQuick

Item {
    id: root

    /*! The resting image (file URL). */
    property string still: ""
    /*! Called on first hover; must return {url, frames, width, height}
        or null. Kept as a closure so the component stays generic. */
    property var provider: null
    /*! Milliseconds per frame of the strip. */
    property int interval: 80
    property int stillFillMode: Image.PreserveAspectCrop
    /*! What the strip depends on. Change it and the strip is forgotten
        and fetched again on the next hover - a delegate reused for a
        different subject (another sticker's cards) must not keep
        showing the previous one's film. */
    property string cacheKey: ""
    onCacheKeyChanged: {
        stripInfo.asked = false;
        stripInfo.url = "";
        stripInfo.frames = 0;
        frame = 0;
        if (hover.hovered)
            fetch();
    }
    function fetch() {
        if (stripInfo.asked || !root.provider)
            return;
        stripInfo.asked = true;
        var info = root.provider();
        if (info && info.frames > 0) {
            stripInfo.url = info.url;
            stripInfo.frames = info.frames;
        }
    }

    readonly property bool playing:
        hover.hovered && stripInfo.frames > 0
        && stripImage.status === Image.Ready
    property int frame: 0

    QtObject {
        id: stripInfo
        property string url: ""
        property int frames: 0
        property bool asked: false
    }

    HoverHandler {
        id: hover
        onHoveredChanged: {
            if (hovered)
                root.fetch();
            root.frame = 0;
        }
    }

    Image {
        anchors.fill: parent
        visible: !root.playing
        fillMode: root.stillFillMode
        asynchronous: true
        source: root.still
    }

    // The viewport: the strip slides behind it, one frame at a time.
    Item {
        anchors.fill: parent
        visible: root.playing
        clip: true

        Image {
            id: stripImage
            height: parent.height
            width: stripInfo.frames > 0
                ? parent.width * stripInfo.frames : 0
            x: -root.frame * parent.width
            fillMode: Image.Stretch
            asynchronous: true
            source: stripInfo.url
        }
    }

    Timer {
        running: hover.hovered && stripInfo.frames > 0
        interval: root.interval
        repeat: true
        onTriggered: root.frame = (root.frame + 1)
                                  % Math.max(1, stripInfo.frames)
    }
}
