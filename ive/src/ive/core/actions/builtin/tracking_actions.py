"""Actions for motion tracking: an overlay follows a target.

The AI checklist (docs/AI_FEATURES.md §11) in action form: what the
Track button does is equally reachable from the palette, a script or
the future assistant. The work lives in TrackingService
(ive/ui/tracking_service.py) and ive/ai/tracking; these are the
registered doorways.
"""

from __future__ import annotations

from ive.core.actions.registry import Param, action


@action(
    id="overlay.track",
    title_key="tracking.track",
    desc_key="Make a sticker or title follow something in the video: "
             "draw the target's box in canvas fractions (x, y = top-left "
             "corner, w, h) at timeline second 'at'; the overlay keeps "
             "its gap to the target from there to the end of the shot "
             "(or until the target is lost). The path lands as editable "
             "keyframes - one undo step. Follows size too when the "
             "VitTrack model is installed; position only otherwise. "
             "direction: forward (to the end of the shot), backward (to "
             "its start) or both; empty = the user's setting.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True, doc="The overlay to move."),
        "x": Param(float, required=True),
        "y": Param(float, required=True),
        "w": Param(float, required=True),
        "h": Param(float, required=True),
        "at": Param(float, required=True,
                    doc="Timeline second the box was drawn at."),
        "follow_size": Param(bool, required=False,
                             doc="Scale with the target (default true)."),
        "direction": Param(str, required=False,
                           doc="forward | backward | both; '' = setting."),
    },
)
def track(ctx, clip_id: str, x: float, y: float, w: float, h: float,
          at: float, follow_size: bool = True, direction: str = ""):
    if direction and direction not in ("forward", "backward", "both"):
        raise RuntimeError(f"Unknown direction {direction!r}")
    service = ctx.require("tracking")
    if not service.track(clip_id, {"x": x, "y": y, "w": w, "h": h}, at,
                         follow_size, direction):
        raise RuntimeError(f"Tracking refused: {service.error or 'busy'}")


@action(
    id="overlay.track_cancel",
    title_key="tracking.cancel",
    desc_key="Stop a running track; nothing is applied.",
    category="timeline",
)
def track_cancel(ctx):
    ctx.require("tracking").cancel()


@action(
    id="overlay.set_track_direction",
    title_key="tracking.direction",
    desc_key="Which way tracking runs from the drawn box: forward (to the "
             "end of the shot), backward (to its start) or both.",
    category="timeline",
    params={"direction": Param(str, required=True,
                               doc="forward | backward | both")},
)
def set_track_direction(ctx, direction: str):
    if direction not in ("forward", "backward", "both"):
        raise RuntimeError(f"Unknown direction {direction!r}")
    ctx.require("settings").set("ai.tracking_direction", direction)
