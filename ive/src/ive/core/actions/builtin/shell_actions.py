"""Actions for the immersive shell: appearance, layout and language.

Everything the settings panel offers goes through these actions, so the same
operations are reachable from the command palette, a script, a plugin and the
natural-language assistant - not only by clicking.
"""

from __future__ import annotations

import logging

from ive.core.actions.registry import Param, action

log = logging.getLogger(__name__)


# ── appearance ────────────────────────────────────────────────────────

@action(
    id="app.set_theme",
    title_key="settings.theme",
    desc_key="Switch the interface theme. Theme ids come from the theme files.",
    category="appearance",
    params={"theme_id": Param(str, required=True, doc="Theme id, e.g. 'dark' or 'light'.")},
)
def set_theme(ctx, theme_id: str):
    ctx.require("theme").set_theme(theme_id)


@action(
    id="app.toggle_theme",
    title_key="settings.theme",
    desc_key="Switch between the dark and light theme.",
    category="appearance",
    shortcut="Ctrl+Shift+T",
)
def toggle_theme(ctx):
    theme = ctx.require("theme")
    theme.set_theme("light" if theme.isDark else "dark")


@action(
    id="app.set_language",
    title_key="settings.language",
    desc_key="Change the interface language at runtime.",
    category="appearance",
    params={"code": Param(str, required=True,
                          doc="Locale code such as 'en', 'it', 'pt', 'es', or 'system'.")},
)
def set_language(ctx, code: str):
    ctx.require("translations").set_language(code)
    ctx.require("settings").set("app.language", code)


@action(
    id="view.toggle_ambient",
    title_key="settings.ambient",
    desc_key="Toggle the blurred ambient backdrop behind the video.",
    category="view",
)
def toggle_ambient(ctx):
    settings = ctx.require("settings")
    settings.set("shell.ambient_backdrop", not settings.get("shell.ambient_backdrop"))


@action(
    id="view.toggle_idle_background",
    title_key="settings.idle_background",
    desc_key="Toggle the looping clip shown when no project is open.",
    category="view",
)
def toggle_idle_background(ctx):
    settings = ctx.require("settings")
    settings.set("appearance.idle_background",
                 not settings.get("appearance.idle_background"))


@action(
    id="view.set_glass",
    title_key="settings.glass",
    desc_key="Glass surfaces: 'auto' degrades on its own, 'always' or 'never' force it.",
    category="view",
    params={"mode": Param(str, required=True, choices=("auto", "always", "never"))},
)
def set_glass(ctx, mode: str):
    ctx.require("settings").set("appearance.glass", mode)


@action(
    id="view.set_glass_opacity",
    title_key="settings.glass_opacity",
    desc_key="How see-through the glass surfaces are. 0.15 is almost clear, "
             "1.0 is fully solid.",
    category="view",
    params={"opacity": Param(float, required=True, doc="Between 0.15 and 1.0.")},
)
def set_glass_opacity(ctx, opacity: float):
    ctx.require("settings").set("appearance.glass_opacity", opacity)


@action(
    id="view.set_glass_blur",
    title_key="settings.glass_blur",
    desc_key="Blur radius of the glass surfaces in pixels; 0 leaves a plain tint.",
    category="view",
    params={"radius": Param(int, required=True, doc="Between 0 and 120.")},
)
def set_glass_blur(ctx, radius: int):
    ctx.require("settings").set("appearance.glass_blur", radius)


@action(
    id="view.reset_glass",
    title_key="settings.glass_reset",
    desc_key="Restore the default transparency and blur.",
    category="view",
)
def reset_glass(ctx):
    settings = ctx.require("settings")
    settings.reset("appearance.glass_opacity")
    settings.reset("appearance.glass_blur")


@action(
    id="view.toggle_fullscreen",
    title_key="view.fullscreen",
    desc_key="Switch between fullscreen and windowed.",
    category="view",
    shortcut="F11",
)
def toggle_fullscreen(ctx):
    window = ctx.require("window")
    fullscreen = not bool(window.property("isFullscreen"))
    window.setProperty("isFullscreen", fullscreen)
    ctx.require("settings").set("window.fullscreen", fullscreen)


@action(
    id="app.quit",
    title_key="app.quit",
    desc_key="Close the application. Same path as closing the window: "
             "settings are flushed and every service shuts down cleanly.",
    category="app",
)
def quit_app(ctx):
    # close(), not exit(): the window's close path is where the orderly
    # shutdown lives (state saved, threads stopped). A direct process exit
    # would skip all of it.
    ctx.require("window").close()


# ── shell layout (docs/UI_SHELL.md 8-ter) ─────────────────────────────

@action(
    id="shell.set_rail_side",
    title_key="settings.rail_side",
    desc_key="Move the tool rail; the floating panel takes the opposite side.",
    category="layout",
    params={"side": Param(str, required=True, choices=("left", "right"))},
)
def set_rail_side(ctx, side: str):
    ctx.require("settings").set("shell.rail_side", side)


@action(
    id="shell.set_transport_position",
    title_key="settings.transport_position",
    desc_key="Place the playback controls at the video centre or above the timeline.",
    category="layout",
    params={"position": Param(str, required=True, choices=("center", "bottom"))},
)
def set_transport_position(ctx, position: str):
    ctx.require("settings").set("shell.transport_position", position)


@action(
    id="shell.set_readout_corner",
    title_key="settings.readout_corner",
    desc_key="Corner where the timecode and volume readout sits.",
    category="layout",
    params={"corner": Param(str, required=True,
                            choices=("top_left", "top_right", "bottom_left"))},
)
def set_readout_corner(ctx, corner: str):
    ctx.require("settings").set("shell.readout_corner", corner)


@action(
    id="shell.set_timeline_height",
    title_key="settings.timeline_height",
    desc_key="Height of the timeline panel in pixels.",
    category="layout",
    params={"height": Param(int, required=True, doc="Between 140 and 520.")},
)
def set_timeline_height(ctx, height: int):
    ctx.require("settings").set("shell.timeline_height", height)


@action(
    id="shell.set_panel_autohide",
    title_key="settings.panel_autohide",
    desc_key="Whether the floating panel retracts when the pointer leaves it.",
    category="layout",
    params={"enabled": Param(bool, required=True)},
)
def set_panel_autohide(ctx, enabled: bool):
    ctx.require("settings").set("shell.panel_autohide", enabled)


@action(
    id="shell.set_panel_hide_delay",
    title_key="settings.panel_hide_delay",
    desc_key="Delay in milliseconds before the floating panel retracts.",
    category="layout",
    params={"milliseconds": Param(int, required=True, doc="Between 0 and 3000.")},
)
def set_panel_hide_delay(ctx, milliseconds: int):
    ctx.require("settings").set("shell.panel_hide_delay_ms", milliseconds)


# ── generic escape hatch ──────────────────────────────────────────────

@action(
    id="settings.set",
    title_key="rail.settings",
    desc_key="Set any declared preference by key. Prefer the specific actions.",
    category="settings",
    params={
        "key": Param(str, required=True, doc="A key declared in settings/schema.py."),
        "value": Param(str, required=True, doc="Value; coerced to the declared type."),
    },
)
def settings_set(ctx, key: str, value):
    ctx.require("settings").set(key, value)
