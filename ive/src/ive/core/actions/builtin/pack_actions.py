"""Actions for the content packs (.ivepack)."""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


@action(
    id="pack.create",
    title_key="pack.create",
    desc_key="Build a shareable .ivepack file from catalogue entries: "
             "colour effects, transitions, stickers, motion presets, export "
             "presets and audio effects by id. Everything inside is data, "
             "never code.",
    category="packs",
    params={
        "name": Param(str, required=True),
        "path": Param(str, required=True, doc="Destination .ivepack file."),
        "author": Param(str, required=False),
        "description": Param(str, required=False),
        "color_ids": Param(list, required=False),
        "transition_ids": Param(list, required=False),
        "sticker_ids": Param(list, required=False),
        "motion_ids": Param(list, required=False),
        "export_preset_ids": Param(list, required=False),
        "audio_effect_ids": Param(list, required=False),
        "track_ids": Param(list, required=False, doc="Music tracks."),
    },
)
def create(ctx, name: str, path: str, author: str = "",
           description: str = "", color_ids: list = None,
           transition_ids: list = None, sticker_ids: list = None,
           motion_ids: list = None, export_preset_ids: list = None,
           audio_effect_ids: list = None, track_ids: list = None):
    selection = {"colors": color_ids or [],
                 "transitions": transition_ids or [],
                 "stickers": sticker_ids or [], "motion": motion_ids or [],
                 "export_presets": export_preset_ids or [],
                 "audio_effects": audio_effect_ids or [],
                 "music": track_ids or []}
    if not ctx.require("packs").create(name, author, description,
                                       selection, path):
        raise RuntimeError("Pack export failed")


@action(
    id="pack.install",
    title_key="pack.install",
    desc_key="Preview a .ivepack file and put it up for the user's "
             "confirmation; the install happens on confirm.",
    category="packs",
    params={"path": Param(str, required=True)},
)
def install(ctx, path: str):
    if not ctx.require("packs").request_install(path):
        raise RuntimeError(f"Not a usable pack: {path}")


@action(
    id="pack.remove",
    title_key="pack.remove",
    desc_key="Remove an installed content pack; its contents leave the "
             "panels. Projects using them still open - those stretches "
             "simply play plain.",
    category="packs",
    params={"pack_id": Param(str, required=True)},
)
def remove(ctx, pack_id: str):
    if not ctx.require("packs").remove(pack_id):
        raise RuntimeError(f"No installed pack {pack_id!r}")
