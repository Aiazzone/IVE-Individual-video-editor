"""Background removal on an A/V clip: the subject over a colour or an image."""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


@action(
    id="timeline.set_clip_cutout",
    title_key="cutout.label",
    desc_key="Remove the background of a video clip: the subject (person, "
             "animal or object, found by the segmentation model) stays, "
             "the scene behind it becomes a solid colour (mode 'color') "
             "or a still image (mode 'image', a file path), or nothing "
             "(mode 'transparent': kept as alpha by an export in ProRes/MOV "
             "or VP9/WebM with alpha=true; black in the preview). mode 'off' "
             "restores the picture as shot. feather (0..1) softens the "
             "edge, shrink (0..1) pulls it in. Undoable. Needs the "
             "subject-segmentation model; without it the clip plays "
             "unchanged.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "mode": Param(str, required=True,
                      doc="color | image | transparent | off"),
        "color": Param(str, required=False, doc="#RRGGBB (default green)"),
        "image": Param(str, required=False, doc="Path of a still image."),
        "feather": Param(float, required=False, doc="0..1, default 0.3"),
        "shrink": Param(float, required=False, doc="0..1, default 0.1"),
    },
)
def set_clip_cutout(ctx, clip_id: str, mode: str, color: str = "#00B140",
                    image: str = "", feather: float = 0.3,
                    shrink: float = 0.1):
    if mode not in ("color", "image", "transparent", "off", ""):
        raise RuntimeError(f"Unknown background mode {mode!r}")
    if mode == "image" and not image:
        raise RuntimeError("An image background needs an image path")
    project = ctx.require("project")
    clip = next((c for c in project.timelineClips if c["id"] == clip_id),
                None)
    if clip is None or int(clip.get("track") or 0) != 0 \
            or not clip.get("hasVideo"):
        raise RuntimeError(f"Clip {clip_id} has no picture to cut out")
    current = clip.get("cutout") or {}
    if mode in ("off", "") and not current:
        return {"changed": False}
    project.set_clip_cutout(clip_id, "" if mode == "off" else mode,
                            color or "#00B140", image or "",
                            float(feather), float(shrink))
    return {"changed": True}


@action(
    id="cutout.download_model",
    title_key="cutout.download",
    desc_key="Download the subject-segmentation model background removal "
             "uses (u2netp, ~4.6 MB, Apache-2.0). Explicit and "
             "hash-verified; nothing is fetched silently.",
    category="ai",
)
def download_model(ctx):
    from ive.ai.segmentation import MODEL_ID

    if not ctx.require("subtitles").download(MODEL_ID):
        raise RuntimeError("A download is already running")
