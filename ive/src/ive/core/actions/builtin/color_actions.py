"""Actions for the colour-effect catalogue."""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


@action(
    id="color.toggle_favorite",
    title_key="color.favorite",
    desc_key="Star a colour effect, or unstar it. Starred effects gather "
             "in the Favorites tab of the Color panel.",
    category="color",
    params={"effect_id": Param(str, required=True)},
)
def toggle_favorite(ctx, effect_id: str):
    settings = ctx.require("settings")
    favorites = [str(v) for v in (settings.get("color.favorites") or [])]
    if effect_id in favorites:
        favorites.remove(effect_id)
    else:
        favorites.append(effect_id)
    settings.set("color.favorites", favorites)
    log.info("Colour favourites now: %s", favorites)
