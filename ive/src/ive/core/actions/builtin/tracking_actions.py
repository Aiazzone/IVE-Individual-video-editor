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
             "VitTrack model is installed; position only otherwise.",
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
    },
)
def track(ctx, clip_id: str, x: float, y: float, w: float, h: float,
          at: float, follow_size: bool = True):
    service = ctx.require("tracking")
    if not service.track(clip_id, {"x": x, "y": y, "w": w, "h": h}, at,
                         follow_size):
        raise RuntimeError(f"Tracking refused: {service.error or 'busy'}")


@action(
    id="overlay.track_cancel",
    title_key="tracking.cancel",
    desc_key="Stop a running track; nothing is applied.",
    category="timeline",
)
def track_cancel(ctx):
    ctx.require("tracking").cancel()
