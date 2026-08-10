// Icon path data, drawn on a 24x24 grid with a 1.5 px stroke.
//
// Outline style after Lucide (ISC licence), redrawn as SVG path data so the
// stroke takes its colour straight from the theme - no per-theme asset copies,
// no runtime tinting. Circles are expressed as arc pairs because PathSvg has
// no circle primitive.
pragma Singleton
import QtQuick

QtObject {
    // helper used when composing the strings below: circle(cx, cy, r)
    function circle(cx, cy, r) {
        return "M" + (cx - r) + "," + cy
             + " a" + r + "," + r + " 0 1,0 " + (2 * r) + ",0"
             + " a" + r + "," + r + " 0 1,0 " + (-2 * r) + ",0"
    }

    // ── project ────────────────────────────────────────────────────
    readonly property string plus: "M12 5v14 M5 12h14"
    readonly property string project:
        "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z M3 11h18"
    readonly property string trash:
        "M3 6h18 M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"
        + " M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"
    readonly property string folderOpen:
        "M2 8a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v1"
        + " M2 8l1.5 10a2 2 0 0 0 2 2h13a2 2 0 0 0 2-1.6L22 11H6.2a2 2 0 0 0-1.9 1.4Z"
    readonly property string check: "M20 6 9 17l-5-5"
    readonly property string alert:
        "M12 9v4 M12 17h.01"
        + " M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"

    // ── tool rail ──────────────────────────────────────────────────
    // The film clapperboard: the slate top at an angle over the body.
    readonly property string clapper:
        "M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.3Z"
        + " M6.2 5.3l3.1 3.9 M12.4 3.4l3.1 4"
        + " M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"
    // A sticker: square with a peeling corner and a little face.
    readonly property string sticker:
        "M15.5 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8.5L15.5 3Z"
        + " M15 3v4a2 2 0 0 0 2 2h4"
        + " M8 13h.01 M13 13h.01 M8.5 16.5c.9.7 2.6.7 3.5 0"
    readonly property string media:
        "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"
    readonly property string text:
        "M4 7V4h16v3 M9 20h6 M12 4v16"
    readonly property string effects:
        "M12 3l-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"
    readonly property string audio:
        "M2 10v3 M6 6v11 M10 3v18 M14 8v7 M18 5v13 M22 10v3"
    readonly property string color:
        "M12 2a10 10 0 1 0 0 20 2 2 0 0 0 2-2v-1a2 2 0 0 1 2-2h1a4 4 0 0 0 4-4 10 10 0 0 0-9-11Z"
        + " " + circle(8.5, 7.5, 0.6) + " " + circle(13.5, 6.5, 0.6)
        + " " + circle(6.5, 12.5, 0.6) + " " + circle(17.5, 10.5, 0.6)
    readonly property string ai:
        "M3 10a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"
        + " M12 8V5 M9 2h6 " + circle(8.5, 14, 1) + " " + circle(15.5, 14, 1)
    readonly property string assistant:
        "M7.9 20A9 9 0 1 0 4 16.1L2 22Z"
    readonly property string settings:
        "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"
        + " " + circle(12, 12, 3)

    // ── export ─────────────────────────────────────────────────────
    readonly property string exportIcon:
        "M12 3v12 M8 11l4 4 4-4"
        + " M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"

    // ── platforms (export social tab) ──────────────────────────────
    // Same outline language as the rest: monochrome strokes, no brand
    // colours, so they follow the theme like every other glyph.
    readonly property string youtube:
        "M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17"
        + " M10 15l5-3-5-3z"
    readonly property string instagram:
        "M2 7a5 5 0 0 1 5-5h10a5 5 0 0 1 5 5v10a5 5 0 0 1-5 5H7a5 5 0 0 1-5-5Z"
        + " M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37Z"
        + " M17.5 6.5h.01"
    // The note from the logo, not the wordmark: stem, head, sound wave.
    readonly property string tiktok:
        "M15 4v11.5a4.5 4.5 0 1 1-4.5-4.5"
        + " M15 4a5 5 0 0 0 5 5"
    readonly property string linkedin:
        "M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4V8h4v2"
        + " M2 9h4v12H2Z " + circle(4, 4, 2)
    readonly property string facebook:
        "M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"
    // Speech bubble with the handset inside, as the logo reads at a glance.
    readonly property string whatsapp:
        "M7.9 20A9 9 0 1 0 4 16.1L2 22Z"
        + " M8.6 8.1a1 1 0 0 1 1.5-.6l1.5 1a1 1 0 0 1 .3 1.35l-.5.85a7.2 7.2 0 0 0 2.4 2.4l.85-.5a1 1 0 0 1 1.35.3l1 1.5a1 1 0 0 1-.6 1.5c-3 .75-8.55-4.8-7.8-7.8Z"

    // ── panel ──────────────────────────────────────────────────────
    readonly property string pin:
        "M12 17v5 M9 10.76V7a3 3 0 1 1 6 0v3.76a2 2 0 0 0 .55 1.38l1.9 2A1 1 0 0 1 16.72 15H7.28a1 1 0 0 1-.73-1.86l1.9-2A2 2 0 0 0 9 10.76Z"
    readonly property string close:
        "M18 6 6 18 M6 6l12 12"
    readonly property string chevronDown:
        "M6 9l6 6 6-6"

    // ── transport ──────────────────────────────────────────────────
    readonly property string play:      "M6 3l14 9-14 9z"
    readonly property string pause:     "M7 4h4v16H7z M13 4h4v16h-4z"
    readonly property string skipStart: "M19 20 9 12l10-8z M5 19V5"
    readonly property string skipEnd:   "M5 4l10 8-10 8z M19 5v14"
    readonly property string stepBack:    "M15 18l-6-6 6-6"
    readonly property string stepForward: "M9 18l6-6-6-6"
    readonly property string volume:
        "M11 5 6 9H2v6h4l5 4z M19.07 4.93a10 10 0 0 1 0 14.14 M15.54 8.46a5 5 0 0 1 0 7.07"
    readonly property string volumeOff:
        "M11 5 6 9H2v6h4l5 4z M22 9l-6 6 M16 9l6 6"

    // ── timeline ───────────────────────────────────────────────────
    readonly property string cut:
        circle(6, 6, 3) + " " + circle(6, 18, 3)
        + " M20 4 8.12 15.88 M14.47 14.48 20 20 M8.12 8.12 12 12"
    readonly property string split:
        "M12 3v18 M8 7l4-4 4 4 M8 17l4 4 4-4"
    readonly property string undo:
        "M3 7v6h6 M3 13a9 9 0 1 0 3-7.7L3 8"
    readonly property string redo:
        "M21 7v6h-6 M21 13a9 9 0 1 1-3-7.7L21 8"
    readonly property string zoomIn:  "M12 5v14 M5 12h14"
    readonly property string zoomOut: "M5 12h14"
    // Arrows pushing both edges out: "make it all fit".
    readonly property string zoomFit:
        "M9 12H3 M15 12h6 M7 8l-4 4 4 4 M17 8l4 4-4 4"
    readonly property string volumeUp:
        "M11 5 6 9H2v6h4l5 4z M18 9v6 M15 12h6"
    readonly property string volumeDown:
        "M11 5 6 9H2v6h4l5 4z M15 12h6"
    readonly property string eye:
        "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z " + circle(12, 12, 3)
    readonly property string lock:
        "M4 13a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z M8 11V7a4 4 0 0 1 8 0v4"

    // ── misc ───────────────────────────────────────────────────────
    // Arrows pointing outwards: "go bigger".
    readonly property string fullscreen:
        "M8 3H5a2 2 0 0 0-2 2v3 M21 8V5a2 2 0 0 0-2-2h-3"
        + " M3 16v3a2 2 0 0 0 2 2h3 M16 21h3a2 2 0 0 0 2-2v-3"
    // Arrows pointing inwards: "come back". Reversing the direction is what
    // makes the state readable without a label.
    readonly property string fullscreenExit:
        "M8 3v3a2 2 0 0 1-2 2H3 M21 8h-3a2 2 0 0 1-2-2V3"
        + " M3 16h3a2 2 0 0 1 2 2v3 M16 21v-3a2 2 0 0 1 2-2h3"
    readonly property string power:
        "M12 2v10 M18.36 6.64a9 9 0 1 1-12.73 0"
    readonly property string film:
        "M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"
        + " M7 3v18 M17 3v18 M3 9h4 M17 9h4 M3 15h4 M17 15h4"
}
