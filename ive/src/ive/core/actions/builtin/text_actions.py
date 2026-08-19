"""Actions for titles on the Text lane."""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


@action(
    id="timeline.place_text",
    title_key="text.place",
    desc_key="Put a title on the Text lane, covering a stretch of the "
             "timeline. It appears centred; move it with "
             "timeline.set_clip_transform, restyle it with "
             "timeline.set_clip_text.",
    category="timeline",
    params={
        "text": Param(str, required=True),
        "at": Param(float, required=True, doc="Timeline seconds."),
        "duration": Param(float, required=True),
        "y": Param(float, required=False,
                   doc="Vertical centre as a canvas fraction; 0.5 default."),
    },
)
def place_text(ctx, text: str, at: float, duration: float, y: float = 0.5):
    if not ctx.require("project").place_text(text, at, duration, y):
        raise RuntimeError("Could not place the title (empty text?)")


@action(
    id="timeline.set_clip_text",
    title_key="text.edit",
    desc_key="Change a title's words and style: font family (empty = the "
             "app's default), fill colour, outline colour (empty = no "
             "outline), bold, italic.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "text": Param(str, required=True),
        "font": Param(str, required=False),
        "color": Param(str, required=False),
        "outline": Param(str, required=False),
        "bold": Param(bool, required=False),
        "italic": Param(bool, required=False),
    },
)
def set_clip_text(ctx, clip_id: str, text: str, font: str = "",
                  color: str = "#FFFFFF", outline: str = "#000000",
                  bold: bool = True, italic: bool = False):
    if not ctx.require("project").set_clip_text(clip_id, text, font, color,
                                                outline, bold, italic):
        raise RuntimeError(f"Unknown text clip {clip_id}")
