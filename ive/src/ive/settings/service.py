"""Settings persistence.

Values live in ``user_data/settings/settings.json``. A missing or corrupt file
is never fatal: the service falls back to the declared defaults, renames the
damaged file aside (never deletes it) and logs a warning.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from ive.settings.schema import SETTINGS, get_setting
from ive.utils.paths import get_data_path

log = logging.getLogger(__name__)

__all__ = ["SettingsService"]

_SAVE_DEBOUNCE_MS = 400


class SettingsService(QObject):
    """Reads and writes user preferences, validated against the schema."""

    #: Emitted after a value actually changed: (key, new value).
    changed = Signal(str, object)

    def __init__(self, path: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # IVE_SETTINGS redirects the whole file elsewhere. Tests and scripts
        # must set it: writing preferences into the real file silently changes
        # what the user sees the next time they launch the app, and the cause
        # is very hard to guess from the symptom.
        override = os.environ.get("IVE_SETTINGS")
        self._path = path or (Path(override) if override
                              else get_data_path("settings/settings.json"))
        self._values: dict[str, Any] = {}
        #: Keys from the file that no declared setting matches - typically a
        #: newer version's. Preserved verbatim by flush(), never consulted.
        self._unknown: dict[str, Any] = {}
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(_SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self.flush)
        self._load()

    # ── public API ────────────────────────────────────────────────────

    @Slot(str, result="QVariant")
    def get(self, key: str) -> Any:
        """Current value of ``key``, or its default when unset."""
        setting = get_setting(key)
        if key in self._values:
            return self._values[key]
        return setting.default

    @Slot(str, "QVariant")
    def set(self, key: str, value: Any) -> None:
        """Validate and store ``value``; persists asynchronously."""
        setting = get_setting(key)
        validated = setting.validate(value)
        if self.get(key) == validated:
            return
        self._values[key] = validated
        log.debug("Setting changed: %s = %r", key, validated)
        self.changed.emit(key, validated)
        self._save_timer.start()

    @Slot(str)
    def reset(self, key: str) -> None:
        """Restore a single key to its factory default."""
        setting = get_setting(key)
        if key in self._values:
            del self._values[key]
            self.changed.emit(key, setting.default)
            self._save_timer.start()

    def as_dict(self) -> dict[str, Any]:
        """Every declared key with its effective value."""
        return {key: self.get(key) for key in SETTINGS}

    @Slot()
    def flush(self) -> None:
        """Write to disk now. Safe to call repeatedly."""
        self._save_timer.stop()
        # Unknown keys ride along unchanged: they may belong to a newer
        # version the user downgraded from. Writing only _values here used
        # to erase them the first time ANY preference changed.
        payload = {
            "_comment": "IVE user settings. Edited by the app; safe to edit by hand.",
            "values": {**self._unknown, **self._values},
        }
        tmp = self._path.with_suffix(".json.tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            tmp.replace(self._path)  # atomic: never leave a half-written file
        except OSError:
            log.exception("Could not save settings to %s", self._path)

    # ── internals ─────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.is_file():
            log.info("No settings file yet, using defaults: %s", self._path)
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            stored = raw.get("values", raw)
            if not isinstance(stored, dict):
                raise ValueError("'values' is not an object")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._quarantine(exc)
            return

        for key, value in stored.items():
            if key not in SETTINGS:
                # Kept out of _values but preserved across saves: they may
                # belong to a newer version the user downgraded from.
                self._unknown[key] = value
                continue
            self._values[key] = SETTINGS[key].validate(value)
        if self._unknown:
            log.warning("Ignoring unknown settings keys: %s",
                        ", ".join(sorted(self._unknown)))
        self._migrate()
        log.info("Loaded %d settings from %s", len(self._values), self._path)

    #: Old defaults that a newer default supersedes: a stored value equal
    #: to the old default was never a choice, so it follows the new one.
    _SUPERSEDED_DEFAULTS = {
        # 232 px hid the sticker and text lanes; 312 shows all five.
        "shell.timeline_height": (232, 312),
    }

    def _migrate(self) -> None:
        for key, (old, new) in self._SUPERSEDED_DEFAULTS.items():
            if self._values.get(key) == old:
                self._values[key] = new
                log.info("Setting %s migrated from old default %s to %s",
                         key, old, new)

    def _quarantine(self, exc: Exception) -> None:
        """Move an unreadable settings file aside and carry on with defaults."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self._path.with_name(f"{self._path.stem}.corrupt-{stamp}.json")
        log.warning("Settings file unreadable (%s); moving to %s", exc, backup.name)
        try:
            self._path.replace(backup)
        except OSError:
            log.exception("Could not move the damaged settings file aside")
