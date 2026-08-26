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
    id="timeline.set_clip_karaoke",
    title_key="subtitles.karaoke",
    desc_key="Light the words of one subtitle clip up as they are "
             "spoken (karaoke). Works only on clips that carry word "
             "timestamps - the generated ones do.",
    category="timeline",
    params={
        "clip_id": Param(str, required=True),
        "enabled": Param(bool, required=True),
    },
)
def set_clip_karaoke(ctx, clip_id: str, enabled: bool):
    if not ctx.require("project").set_clip_karaoke(clip_id, enabled):
        raise RuntimeError(f"Clip {clip_id} has no words to light up")


@action(
    id="subtitles.export_file",
    title_key="subtitles.export",
    desc_key="Write the Text lane as a subtitle file; .srt or .vtt "
             "follows the extension of the path.",
    category="timeline",
    params={"path": Param(str, required=True)},
)
def export_file(ctx, path: str):
    count = ctx.require("project").export_subtitles(path)
    if count <= 0:
        raise RuntimeError("Nothing on the Text lane to export, "
                           "or the path is not writable")
    return {"lines": count}


@action(
    id="subtitles.import_file",
    title_key="subtitles.import",
    desc_key="Read an .srt or .vtt file and lay its cues on the Text "
             "lane as editable titles - one undo step.",
    category="timeline",
    params={"path": Param(str, required=True)},
)
def import_file(ctx, path: str):
    count = ctx.require("project").import_subtitles(path)
    if count <= 0:
        raise RuntimeError("No readable cue in that file")
    return {"lines": count}


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
    id="subtitles.set_model",
    title_key="subtitles.model",
    desc_key="Choose which speech model the automatic subtitles use "
             "(whisper-tiny or whisper-small).",
    category="ai",
    params={"model_id": Param(str, required=True)},
)
def set_model(ctx, model_id: str):
    from ive.ai import model_entry

    if model_entry(model_id) is None:
        raise RuntimeError(f"Unknown model {model_id!r}")
    ctx.require("settings").set("ai.subtitles_model", model_id)
    ctx.require("subtitles").refresh()


@action(
    id="subtitles.set_language",
    title_key="subtitles.language",
    desc_key="Spoken language for the automatic subtitles as an ISO "
             "code ('it', 'en', ...); empty detects it from the audio.",
    category="ai",
    params={"language": Param(str, required=False)},
)
def set_language(ctx, language: str = ""):
    ctx.require("settings").set("ai.subtitles_language",
                                str(language).strip().lower())
    ctx.require("subtitles").refresh()


@action(
    id="subtitles.translate",
    title_key="subtitles.translate",
    desc_key="Translate every subtitle on the Text lane into the target "
             "language (optional 'language' overrides the setting). "
             "Timings stay; one undo step brings the original back. The "
             "source is the pinned subtitles language or the detected "
             "one; missing pairs pivot through English.",
    category="timeline",
    params={
        "language": Param(str, required=False,
                          doc="Target ISO code; '' = the setting."),
    },
)
def translate(ctx, language: str = ""):
    service = ctx.require("subtitles")
    if language:
        ctx.require("settings").set("ai.translate_target",
                                    str(language).strip().lower())
        service.refresh()
    if not service.translate():
        state = service.translateState
        if state != "ready":
            raise RuntimeError(f"Translation unavailable: {state}")
        raise RuntimeError(service.translateError or "Nothing to translate")


@action(
    id="subtitles.set_translate_target",
    title_key="subtitles.translate_to",
    desc_key="Choose the language the subtitle translation writes "
             "(en, it, pt, es).",
    category="ai",
    params={"language": Param(str, required=True)},
)
def set_translate_target(ctx, language: str):
    ctx.require("settings").set("ai.translate_target",
                                str(language).strip().lower())
    ctx.require("subtitles").refresh()


@action(
    id="subtitles.download_translate_models",
    title_key="subtitles.translate_dl",
    desc_key="Download the missing translation pair(s) for the current "
             "source and target languages. Explicit and hash-verified.",
    category="ai",
)
def download_translate_models(ctx):
    if not ctx.require("subtitles").download_translate_models():
        raise RuntimeError("Nothing to download, or one is running")


@action(
    id="subtitles.cancel",
    title_key="subtitles.cancel",
    desc_key="Stop the running subtitle generation or model download.",
    category="ai",
)
def cancel(ctx):
    service = ctx.require("subtitles")
    service.cancel()
    service.cancel_translate()
    service.cancel_download()
