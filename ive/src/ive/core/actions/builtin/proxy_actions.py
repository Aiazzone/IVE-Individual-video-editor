"""Actions for the proxy cache."""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


@action(
    id="proxy.build_for_project",
    title_key="proxy.build",
    desc_key="Build stand-in copies for every clip in the project that needs "
             "one. Editing 4K without them is not real-time.",
    category="media",
)
def build_for_project(ctx, ):
    project = ctx.require("project")
    proxies = ctx.require("proxies")
    paths = [m["path"] for m in project.media if not m.get("missing")]
    queued = proxies.request_many(paths)
    log.info("Queued %d proxy build(s)", queued)


@action(
    id="proxy.set_enabled",
    title_key="proxy.enabled",
    desc_key="Use proxies for the preview. The export is unaffected: it always "
             "reads the originals.",
    category="media",
    params={"enabled": Param(bool, required=True)},
)
def set_enabled(ctx, enabled: bool):
    ctx.require("settings").set("media.proxy_enabled", enabled)


@action(
    id="proxy.cancel",
    title_key="proxy.cancel",
    desc_key="Stop building proxies.",
    category="media",
)
def cancel(ctx):
    ctx.require("proxies").cancel()


@action(
    id="proxy.clear_cache",
    title_key="proxy.clear",
    desc_key="Delete every proxy. They can all be rebuilt.",
    category="media",
)
def clear_cache(ctx):
    ctx.require("proxies").clear_cache()
