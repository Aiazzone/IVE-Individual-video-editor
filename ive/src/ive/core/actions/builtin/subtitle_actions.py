"""Actions for the automatic subtitles: generate, fetch the model, stop.

The AI checklist (docs/AI_FEATURES.md §11) in action form: everything
the panel button does is equally reachable from the palette, a script
or the future assistant. The heavy lifting lives in SubtitleService
(ive/ui/subtitle_service.py); these are the registered doorways.
"""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


@action(
    id="timeline.auto_subtitles",
    title_key="subtitles.generate",
    desc_key="Transcribe the speech in the cut's A/V clips and lay the "
             "lines as editable text clips on the Text lane - one undo "
             "step. Needs the speech model installed (subtitles."
             "download_model). Optional language ISO code ('it', 'en'); "
             "empty detects it.",
    category="timeline",
    params={
        "language": Param(str, required=False,
                          doc="Spoken language; '' = detect."),
    },
)
def auto_subtitles(ctx, language: str = ""):
    service = ctx.require("subtitles")
    if language:
        ctx.require("settings").set("ai.subtitles_language", language)
    if not service.generate():
        state = service.state
        if state != "ready":
            raise RuntimeError(f"Subtitles unavailable: {state}")
        raise RuntimeError(service.error or "Nothing to transcribe")


@action(
    id="subtitles.download_model",
    title_key="subtitles.download",
    desc_key="Download the speech model the automatic subtitles use "
             "(size and licence are in the Text panel). Explicit and "
             "hash-verified; nothing is fetched silently.",
    category="ai",
)
def download_model(ctx):
    if not ctx.require("subtitles").download_model():
        raise RuntimeError("A download is already running")


@action(
    id="subtitles.cancel",
    title_key="subtitles.cancel",
    desc_key="Stop the running subtitle generation or model download.",
    category="ai",
)
def cancel(ctx):
    service = ctx.require("subtitles")
    service.cancel()
    service.cancel_download()
