"""Actions for online content: the startup question and the Settings
button (ive/ui/online_content.py). Nothing is fetched without one of
these being invoked - by the user, a script or the assistant."""

from __future__ import annotations

from ive.core.actions.registry import Param, action


@action(
    id="online.download",
    title_key="online.download",
    desc_key="Download online content: official packs and the default AI "
             "models. 'ids' picks items (pack or model ids); empty = "
             "everything still missing. Answers the startup question for "
             "good. Runs in the background.",
    category="packs",
    params={
        "ids": Param(list, required=False,
                     doc="Pack/model ids; empty = all missing."),
        "never_ask": Param(bool, required=False,
                           doc="Also switch the startup question off."),
    },
)
def download(ctx, ids: list | None = None, never_ask: bool = False):
    service = ctx.require("online")
    if not ids:
        started = service.download_all()
    else:
        started = service.download([str(i) for i in ids], bool(never_ask))
    if not started and service.missing:
        raise RuntimeError("No download started (unknown ids, or a download "
                           "is already running)")
    return {"started": started}


@action(
    id="online.dismiss_offer",
    title_key="online.later",
    desc_key="Close the startup question about online content without "
             "downloading. It comes back at the next start unless "
             "never_ask is true.",
    category="packs",
    params={"never_ask": Param(bool, required=False)},
)
def dismiss_offer(ctx, never_ask: bool = False):
    ctx.require("online").dismiss(bool(never_ask))


@action(
    id="online.set_ask_on_start",
    title_key="online.ask_on_start",
    desc_key="Whether the app asks at startup to download missing online "
             "content (packs, AI models).",
    category="packs",
    params={"enabled": Param(bool, required=True)},
)
def set_ask_on_start(ctx, enabled: bool):
    ctx.require("settings").set("online.never_ask", not bool(enabled))
