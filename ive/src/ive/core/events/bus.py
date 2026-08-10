"""Lightweight publish/subscribe bus.

Modules talk through events rather than calling into each other, which is what
keeps the dependency direction in docs/ARCHITECTURE.md section 1 enforceable.

A subscriber that raises is logged and *unsubscribed* rather than allowed to
break the publisher: one faulty listener must not take the app down.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

log = logging.getLogger(__name__)

__all__ = ["EventBus"]

Handler = Callable[..., None]


class EventBus:
    """Named events with keyword payloads."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event: str, handler: Handler) -> Callable[[], None]:
        """Register ``handler``; returns a callable that unsubscribes it."""
        self._handlers[event].append(handler)

        def unsubscribe() -> None:
            self.unsubscribe(event, handler)

        return unsubscribe

    def unsubscribe(self, event: str, handler: Handler) -> None:
        try:
            self._handlers[event].remove(handler)
        except (KeyError, ValueError):
            pass

    def publish(self, event: str, **payload: Any) -> None:
        """Notify every subscriber of ``event``."""
        handlers = list(self._handlers.get(event, ()))
        if not handlers:
            log.debug("Event %s has no subscribers", event)
            return
        for handler in handlers:
            try:
                handler(**payload)
            except Exception:
                log.exception(
                    "Handler %r failed on event %s; unsubscribing it",
                    getattr(handler, "__qualname__", handler), event,
                )
                self.unsubscribe(event, handler)

    def clear(self) -> None:
        self._handlers.clear()
