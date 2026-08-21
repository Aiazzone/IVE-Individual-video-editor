"""Theme loading and live switching.

Themes are **data**, not code: one JSON file per theme, so a user can add a
theme by dropping a file into ``user_data/themes/`` (and later ship one inside
a content pack) without touching the application.

QML reads two map properties::

    Rectangle { color: Theme.c.bgPanel; radius: Theme.m.radiusLg }

Because ``c`` and ``m`` are properties, every binding re-evaluates when the
theme changes. Nothing else has to be notified.

The readability thresholds in ``metrics`` (``scrimText``, ``scrimIcons``) are
computed on the worst case - see docs/UI_SHELL.md section 4. A theme may raise
them, never lower them: :meth:`_clamp_scrims` enforces it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ive.utils.paths import get_data_path, get_defaults_path

log = logging.getLogger(__name__)

__all__ = ["ThemeService", "MIN_SCRIM_TEXT", "MIN_SCRIM_ICONS"]

#: Hard floors. Below these, white text / icons stop being legible on a
#: worst-case frame. Themes cannot go under them.
MIN_SCRIM_TEXT = 0.55
MIN_SCRIM_TEXT_SECONDARY = 0.68
MIN_SCRIM_ICONS = 0.42

#: Metrics shared by every theme. A theme may override any of these.
BASE_METRICS: dict[str, Any] = {
    # spacing scale (4 px)
    "space1": 4, "space2": 8, "space3": 12, "space4": 16, "space5": 24, "space6": 32,
    # radii
    "radiusSm": 4, "radiusMd": 6, "radiusLg": 8, "radiusFull": 999,
    # type
    # Bumped one step across the board: at 11 px the panel labels were hard
    # to read on a high-density screen, which is where this app lives.
    "fontSizeXs": 11, "fontSizeSm": 12, "fontSizeMd": 14,
    "fontSizeLg": 16, "fontSizeXl": 21,
    # controls
    "controlHeight": 34, "controlHeightSm": 26, "iconSize": 18,
    # motion
    "durFast": 120, "durNormal": 180, "durSlow": 280,
    # glass (docs/UI_SHELL.md 4)
    "scrimText": 0.62, "scrimTextSecondary": 0.72, "scrimIcons": 0.45,
    "scrimSolidFallback": 0.92, "glassUpdateHz": 10,
    # glassBlurMax is the kernel REACH in pixels and is deliberately a
    # constant: the user sets glassBlurIntensity (0-100), which drives
    # MultiEffect.blur. Driving the reach from the setting instead made the
    # effect's own footprint grow with the slider, which is how the blur
    # ended up painting outside the toolbars.
    "glassBlurMax": 64, "glassBlurIntensity": 66, "glassBlurRadius": 48,
    "backdropDim": 0.45, "backdropBlurRadius": 96,
    # The idle clip fills the whole window, so it needs a much
    # heavier veil than the ambient backdrop or it drains the
    # contrast out of the entire interface.
    "idleBackdropDim": 0.58,
    # shell
    "toolRailWidth": 56, "toolRailButton": 40, "toolRailIcon": 20,
    "toolRailRadius": 16,
    "floatPanelWidth": 392, "floatPanelRadius": 14, "floatPanelCollapsed": 48,
    # Ruler: just the timecode text plus 5px of air; the playhead head is
    # allowed to overlap the labels, so it costs no extra height.
    "timelineToolbarHeight": 32, "rulerHeight": 16,
    # Header width fits the track NAME alone: the per-track controls were
    # non-functional placeholders and were removed until they do something.
    "trackHeightVideo": 64, "trackHeightAudio": 48, "trackHeaderWidth": 64,
    "trackLanePadding": 6, "clipGap": 3, "clipRadius": 6,
    "readoutIdleOpacity": 0.55,
}

_FALLBACK_COLORS: dict[str, str] = {
    "bgRoot": "#0E0E11", "bgPanel": "#16161A", "bgElevated": "#1E1E24",
    "bgSunken": "#0A0A0C", "bgHover": "#24242C", "bgPressed": "#2C2C36",
    "border": "#2A2A32", "borderStrong": "#3A3A46",
    # Contrast floor: muted ~7:1 and disabled ~4:1 on the dark panels -
    # the old #54545E "disabled" grey was 2.2:1 and simply unreadable.
    "text": "#EDEDF2", "textMuted": "#B0B0BE", "textDisabled": "#84848F",
    "accent": "#4C8DFF", "accentHover": "#6BA1FF", "accentPressed": "#3A78E6",
    "onAccent": "#FFFFFF", "danger": "#FF4D4F", "warning": "#F5A623",
    "success": "#22C55E",
    "clipVideo": "#2D6BD4", "clipAudio": "#1F8A5C", "clipText": "#8B5CF6",
    "clipMusic": "#B8741A",
    "clipEffect": "#D6408B", "clipSticker": "#0F8B96",
    "clipText": "#6E56C8",
    "clipImage": "#D97706", "clipAdjustment": "#6B7280", "clipSelected": "#FFFFFF",
    "playhead": "#FF4D4F", "trackHeaderBg": "#131318", "rulerBg": "#101014",
    "gridLine": "#22222A",
    "glassTint": "#0A0A0C", "glassBorder": "#2EFFFFFF", "shadow": "#000000",
    # Referenced by every glass surface; leaving it out of the fallback made
    # Theme.c.glassOn undefined when no theme file could be loaded, and QML
    # errored on each binding ("Unable to assign [undefined] to QColor").
    "glassOn": "#FFFFFF",
}


class ThemeService(QObject):
    """Serves the active theme to QML and switches it at runtime."""

    themeChanged = Signal()

    def __init__(self, settings=None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._themes: dict[str, dict[str, Any]] = {}
        self._id = "dark"
        self._colors: dict[str, str] = dict(_FALLBACK_COLORS)
        self._metrics: dict[str, Any] = dict(BASE_METRICS)
        self._glass_enabled = True
        self._glass_opacity: float | None = None
        self._glass_blur: int | None = None
        if settings is not None:
            self._glass_opacity = float(settings.get("appearance.glass_opacity"))
            self._glass_blur = int(settings.get("appearance.glass_blur"))
        self.reload()

    @Slot(float, int)
    def set_glass_overrides(self, opacity: float, blur: int) -> None:
        """Apply the user's live transparency and blur preferences.

        These override the theme's own scrim values. Unlike a theme file - which
        is authored for other people and is therefore clamped to the readability
        floors - this is the user's own screen, so the range extends below the
        safe threshold. The settings panel says so where it matters.
        """
        if opacity == self._glass_opacity and blur == self._glass_blur:
            return
        self._glass_opacity = float(opacity)
        self._glass_blur = int(blur)
        log.info("Glass overrides: opacity=%.2f blur=%d", opacity, blur)
        self.set_theme(self._id, persist=False)

    # ── properties exposed to QML ─────────────────────────────────────

    @Property("QVariantMap", notify=themeChanged)
    def c(self) -> dict[str, str]:
        """Colour tokens of the active theme."""
        return self._colors

    @Property("QVariantMap", notify=themeChanged)
    def m(self) -> dict[str, Any]:
        """Metric tokens (sizes, radii, durations, scrims)."""
        return self._metrics

    @Property(str, notify=themeChanged)
    def id(self) -> str:
        """Identifier of the active theme."""
        return self._id

    @Property(bool, notify=themeChanged)
    def isDark(self) -> bool:
        """True when the active theme is a dark one."""
        return bool(self._themes.get(self._id, {}).get("dark", True))

    @Property(bool, notify=themeChanged)
    def glassEnabled(self) -> bool:
        """False when glass surfaces must fall back to a solid tint."""
        return self._glass_enabled

    @Property("QVariantList", notify=themeChanged)
    def available(self) -> list[dict[str, Any]]:
        """``[{id, name, dark}]`` for the theme picker."""
        out = []
        for theme_id, data in sorted(self._themes.items()):
            names = data.get("name", {})
            label = names.get("en") if isinstance(names, dict) else str(names)
            out.append(
                {"id": theme_id, "name": label or theme_id, "dark": bool(data.get("dark", True))}
            )
        return out

    # ── public API ────────────────────────────────────────────────────

    def reload(self) -> None:
        """Rescan the theme folders and re-apply the active theme."""
        self._themes = self._discover()
        wanted = self._settings.get("app.theme") if self._settings else self._id
        self.set_theme(wanted or self._id, persist=False)

    @Slot(str)
    def set_theme(self, theme_id: str, persist: bool = True) -> None:
        """Activate a theme by id, falling back when it is unknown."""
        if theme_id not in self._themes:
            if self._themes:
                fallback = "dark" if "dark" in self._themes else next(iter(self._themes))
                log.warning("Unknown theme %r, using %r", theme_id, fallback)
                theme_id = fallback
            else:
                log.error("No theme files found; using built-in fallback colours")
                self._id = theme_id
                self.themeChanged.emit()
                return

        data = self._themes[theme_id]
        colors = dict(_FALLBACK_COLORS)
        colors.update({k: v for k, v in data.get("colors", {}).items() if isinstance(v, str)})
        metrics = dict(BASE_METRICS)
        metrics.update(data.get("metrics", {}))
        self._clamp_scrims(metrics, theme_id)
        self._apply_glass_overrides(metrics)

        self._id = theme_id
        self._colors = colors
        self._metrics = metrics
        log.info("Theme applied: %s (dark=%s)", theme_id, data.get("dark", True))
        if persist and self._settings is not None:
            self._settings.set("app.theme", theme_id)
        self.themeChanged.emit()

    @Slot(bool)
    def set_glass_enabled(self, enabled: bool) -> None:
        """Turn glass surfaces on or off (support, performance or preference)."""
        if enabled == self._glass_enabled:
            return
        self._glass_enabled = enabled
        log.info("Glass surfaces %s", "enabled" if enabled else "disabled")
        self.themeChanged.emit()

    # ── internals ─────────────────────────────────────────────────────

    def _discover(self) -> dict[str, dict[str, Any]]:
        """Load themes: shipped first, then user themes (which may override)."""
        themes: dict[str, dict[str, Any]] = {}
        for folder in (get_defaults_path("themes"), get_data_path("themes")):
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.json")):
                data = self._read(path)
                if data is not None:
                    themes[data["id"]] = data
        if not themes:
            log.warning("No theme files found in defaults or user_data")
        else:
            log.info("Themes available: %s", ", ".join(sorted(themes)))
        return themes

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.exception("Could not read theme %s", path.name)
            return None
        if not isinstance(data, dict) or not isinstance(data.get("colors"), dict):
            log.warning("Theme %s has no 'colors' object; ignored", path.name)
            return None
        data.setdefault("id", path.stem)
        return data

    def _apply_glass_overrides(self, metrics: dict[str, Any]) -> None:
        """Overlay the user's transparency and blur on the theme's values.

        The icon tier keeps its usual head start over the text tier: icons only
        need 3:1 contrast, so they can stay more see-through at the same
        setting. Both move together as the user drags one slider.
        """
        if self._glass_opacity is not None:
            gap = BASE_METRICS["scrimText"] - BASE_METRICS["scrimIcons"]  # 0.17
            metrics["scrimText"] = self._glass_opacity
            metrics["scrimTextSecondary"] = min(1.0, self._glass_opacity + 0.10)
            metrics["scrimIcons"] = max(0.05, self._glass_opacity - gap)
        if self._glass_blur is not None:
            # Intensity 0-100 -> a sane radius. The top end is capped well
            # below what MultiEffect accepts: past this the sampled margin
            # would have to grow with it, and the cost climbs for an effect
            # nobody can tell apart.
            intensity = max(0, min(100, int(self._glass_blur)))
            metrics["glassBlurIntensity"] = intensity
            metrics["glassBlurRadius"] = int(round(intensity * 0.72))

    @staticmethod
    def _clamp_scrims(metrics: dict[str, Any], theme_id: str) -> None:
        """Enforce the readability floors from docs/UI_SHELL.md section 4."""
        floors = (
            ("scrimText", MIN_SCRIM_TEXT),
            ("scrimTextSecondary", MIN_SCRIM_TEXT_SECONDARY),
            ("scrimIcons", MIN_SCRIM_ICONS),
        )
        for key, floor in floors:
            try:
                value = float(metrics.get(key, floor))
            except (TypeError, ValueError):
                value = floor
            if value < floor:
                log.warning(
                    "Theme %r sets %s=%.2f, below the readability floor %.2f; clamped",
                    theme_id, key, value, floor,
                )
                value = floor
            metrics[key] = value
