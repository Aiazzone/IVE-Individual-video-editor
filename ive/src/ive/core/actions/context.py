"""Execution context handed to every action.

An action resolves omitted parameters from here, which is what lets the same
action serve both "split here" from the UI (everything implicit) and a fully
explicit programmatic call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["ActionContext"]


@dataclass
class ActionContext:
    """Everything an action may need, without reaching for globals."""

    settings: Any = None
    theme: Any = None
    translations: Any = None
    history: Any = None
    events: Any = None
    window: Any = None

    #: Editing state, populated from stage 1 onwards.
    project: Any = None
    selection: Any = None
    playhead: int = 0

    extras: dict[str, Any] = field(default_factory=dict)

    def require(self, name: str) -> Any:
        """Fetch a context member, failing loudly when it is not wired up.

        "Not wired up" means None - and only None. An `or` here would
        reject perfectly valid falsy values: a playhead at 0 (the start of
        the timeline, and its default), an empty selection, an empty string.
        """
        value = getattr(self, name, None)
        if value is None:
            value = self.extras.get(name)
        if value is None:
            raise RuntimeError(
                f"ActionContext.{name} is not available in this session"
            )
        return value
