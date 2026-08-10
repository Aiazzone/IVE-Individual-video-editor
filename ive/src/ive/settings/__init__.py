"""User preferences: schema and persistence."""

from ive.settings.schema import SETTINGS, Setting, get_setting
from ive.settings.service import SettingsService

__all__ = ["SETTINGS", "Setting", "get_setting", "SettingsService"]
