"""Runtime translations, JSON based.

Design notes
------------
* English (``en.json``) is the source and must be complete. Other locales may
  be partial: missing keys fall back to English, then to the key itself.
* The manager exposes a **merged** dictionary (``strings``) where the current
  locale is overlaid on English. QML binds to it directly, so switching
  language re-evaluates every binding with no per-widget work::

      Text { text: Tr.s["timeline.title"] }

* Python code calls :meth:`t`, which also supports named placeholders::

      tr("export.progress", current=12, total=300)

Placeholders are always **named**, never positional: word order changes
between languages.
"""

from __future__ import annotations

import json
import locale as _locale
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ive.utils.paths import get_data_path

log = logging.getLogger(__name__)

__all__ = ["TranslationManager", "tr", "set_manager"]

SOURCE_LOCALE = "en"

#: Native names shown in the language picker - never translated.
LOCALE_NAMES = {
    "en": "English",
    "it": "Italiano",
    "pt": "Português",
    "es": "Español",
}


class TranslationManager(QObject):
    """Loads locale files and serves translated strings."""

    languageChanged = Signal()

    def __init__(self, locales_dir: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dir = locales_dir or Path(__file__).resolve().parent / "locales"
        self._user_dir = get_data_path("packs")  # locales shipped by content packs
        self._source: dict[str, str] = {}
        self._merged: dict[str, str] = {}
        self._language = SOURCE_LOCALE
        self._missing: set[str] = set()
        self._load_source()

    # ── properties exposed to QML ─────────────────────────────────────

    @Property(str, notify=languageChanged)
    def language(self) -> str:
        """Currently active locale code."""
        return self._language

    @Property("QVariantMap", notify=languageChanged)
    def s(self) -> dict[str, str]:
        """Merged strings: current locale overlaid on English.

        This is the property QML binds to. Because it is a property (not a
        method), every binding that reads it updates on a language change.
        """
        return self._merged

    @Property("QVariantList", notify=languageChanged)
    def availableLanguages(self) -> list[dict[str, str]]:
        """``[{code, name, complete}]`` for the language picker."""
        out = []
        for code in self.discover():
            data = self._read(code)
            complete = bool(self._source) and len(data) >= len(self._source)
            out.append(
                {
                    "code": code,
                    "name": LOCALE_NAMES.get(code, code.upper()),
                    "complete": complete,
                }
            )
        return out

    # ── public API ────────────────────────────────────────────────────

    def discover(self) -> list[str]:
        """Locale codes available, source locale first."""
        codes = {SOURCE_LOCALE}
        for path in self._dir.glob("*.json"):
            codes.add(path.stem)
        for path in self._user_dir.glob("*/locales/*.json"):
            codes.add(path.stem)
        return [SOURCE_LOCALE] + sorted(codes - {SOURCE_LOCALE})

    @Slot(str)
    def set_language(self, code: str) -> None:
        """Switch locale at runtime and notify every binding."""
        code = self.resolve(code)
        if code == self._language and self._merged:
            return
        overlay = self._read(code) if code != SOURCE_LOCALE else {}
        merged = dict(self._source)
        merged.update({k: v for k, v in overlay.items() if isinstance(v, str) and v})
        self._merged = merged
        self._language = code
        self._missing.clear()
        log.info(
            "Language set to %s (%d/%d strings translated)",
            code, len(overlay), len(self._source) or 1,
        )
        self.languageChanged.emit()

    def resolve(self, code: str) -> str:
        """Map ``'system'`` or an unknown code onto an available locale."""
        available = self.discover()
        if code and code != "system":
            if code in available:
                return code
            base = code.split("-")[0].split("_")[0].lower()
            if base in available:
                return base
            log.warning("Locale %r not available, falling back to %s", code, SOURCE_LOCALE)
            return SOURCE_LOCALE

        try:
            system = (_locale.getdefaultlocale()[0] or "").split("_")[0].lower()
        except (ValueError, TypeError):  # pragma: no cover - exotic environments
            system = ""
        return system if system in available else SOURCE_LOCALE

    @Slot(str, result=str)
    def t(self, key: str, **kwargs: Any) -> str:
        """Translate ``key``, formatting named placeholders when given."""
        text = self._merged.get(key)
        if text is None:
            if key not in self._missing:
                self._missing.add(key)
                log.warning("Missing translation key: %s", key)
            text = key
        if not kwargs:
            return text
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            log.warning("Bad placeholders for key %s: %r", key, text)
            return text

    @Slot(str, int, result=str)
    def plural(self, key: str, count: int) -> str:
        """Pick ``key_one`` or ``key_other`` and format ``{count}``."""
        suffix = "one" if abs(count) == 1 else "other"
        return self.t(f"{key}_{suffix}", count=count)

    @property
    def missing_keys(self) -> set[str]:
        """Keys requested but absent from the source locale (test helper)."""
        return set(self._missing)

    # ── internals ─────────────────────────────────────────────────────

    def _load_source(self) -> None:
        self._source = self._read(SOURCE_LOCALE)
        self._merged = dict(self._source)
        if not self._source:
            log.error("Source locale %s.json is empty or missing", SOURCE_LOCALE)

    def _read(self, code: str) -> dict[str, str]:
        """Read one locale, merging any files contributed by content packs."""
        data: dict[str, str] = {}
        candidates = [self._dir / f"{code}.json"]
        candidates += sorted(self._user_dir.glob(f"*/locales/{code}.json"))
        for path in candidates:
            if not path.is_file():
                continue
            try:
                # utf-8-sig: a locale file that passed through a Windows
                # editor (or PowerShell) may carry a BOM, and refusing it
                # silently blanked EVERY string in the interface once.
                raw = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                log.exception("Could not read locale file %s", path)
                continue
            if isinstance(raw, dict):
                data.update({k: v for k, v in raw.items() if isinstance(v, str)})
        return data


# ── module level convenience ──────────────────────────────────────────

_manager: TranslationManager | None = None


def set_manager(manager: TranslationManager) -> None:
    """Install the process-wide manager used by :func:`tr`."""
    global _manager
    _manager = manager


def tr(key: str, **kwargs: Any) -> str:
    """Translate ``key`` using the process-wide manager.

    Safe before initialisation: returns the key itself.
    """
    if _manager is None:
        return key
    return _manager.t(key, **kwargs)
