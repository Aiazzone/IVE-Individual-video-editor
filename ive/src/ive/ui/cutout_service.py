"""What the background-removal card needs to know: can it cut, now?

The work itself is the engine's (engine/cutout.py) and the edit the
project's (``ProjectService.set_clip_cutout``); this only answers the
card's question - is the segmentation model there - as a STATE, never
an error, and follows downloads made anywhere (the card, the AI Models
tab, the startup question) through ``refresh``.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Property, QObject, Signal, Slot

log = logging.getLogger(__name__)

__all__ = ["CutoutService"]


class CutoutService(QObject):
    stateChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = self._probe()

    @staticmethod
    def _probe() -> str:
        from ive.ai.segmentation import availability

        return availability()

    @Property(str, notify=stateChanged)
    def state(self) -> str:
        """ready | model_missing | backend_missing."""
        return self._state

    @Property(int, constant=True)
    def modelMb(self) -> int:
        from ive.ai import model_entry
        from ive.ai.segmentation import MODEL_ID

        entry = model_entry(MODEL_ID) or {}
        return max(1, round(int(entry.get("total_size") or 0) / 1e6))

    @Slot()
    def refresh(self) -> None:
        state = self._probe()
        if state != self._state:
            log.info("Background removal: %s -> %s", self._state, state)
            self._state = state
            self.stateChanged.emit()
