"""Action Registry - the heart of the AI-first architecture.

Every user-facing operation is registered here with a parameter schema. From
one registration the application derives menus, shortcuts, the command
palette, scripting, plugin access and the natural-language assistant.

A feature that is not registered as an action is incomplete, not merely
undocumented::

    @action(
        id="view.toggle_fullscreen",
        title_key="view.fullscreen",
        category="view",
    )
    def toggle_fullscreen(ctx):
        ctx.window.toggle_fullscreen()

An action either performs its work directly, or - when ``undoable`` is set -
returns a :class:`~ive.core.commands.base.Command` that the registry pushes
onto the undo stack. It never touches the UI and never knows who called it.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

log = logging.getLogger(__name__)

__all__ = ["Param", "ActionDef", "ActionRegistry", "action", "ActionError"]


class ActionError(RuntimeError):
    """Raised when an action cannot be invoked as requested."""


@dataclass(frozen=True)
class Param:
    """One action parameter, described well enough for an LLM to fill it in."""

    kind: type
    required: bool = False
    default: Any = None
    doc: str = ""
    choices: tuple[Any, ...] = ()

    def json_schema(self) -> dict[str, Any]:
        """JSON Schema fragment, used by the assistant tool adapter."""
        mapping = {str: "string", int: "integer", float: "number", bool: "boolean",
                   list: "array", dict: "object"}
        schema: dict[str, Any] = {"type": mapping.get(self.kind, "string")}
        if self.doc:
            schema["description"] = self.doc
        if self.choices:
            schema["enum"] = list(self.choices)
        if self.default is not None:
            schema["default"] = self.default
        return schema

    def validate(self, value: Any) -> Any:
        if self.choices and value not in self.choices:
            raise ActionError(f"expected one of {self.choices}, got {value!r}")
        if self.kind is bool and isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        try:
            return self.kind(value) if not isinstance(value, self.kind) else value
        except (TypeError, ValueError) as exc:
            raise ActionError(f"expected {self.kind.__name__}, got {value!r}") from exc


@dataclass(frozen=True)
class ActionDef:
    """A registered action."""

    id: str
    fn: Callable[..., Any]
    title_key: str
    desc_key: str = ""
    category: str = "general"
    params: dict[str, Param] = field(default_factory=dict)
    undoable: bool = False
    shortcut: str = ""

    def json_schema(self) -> dict[str, Any]:
        """Tool definition for the natural-language assistant."""
        required = [name for name, p in self.params.items() if p.required]
        return {
            "name": self.id,
            "description": self.desc_key or self.title_key,
            "input_schema": {
                "type": "object",
                "properties": {n: p.json_schema() for n, p in self.params.items()},
                "required": required,
            },
        }


class ActionRegistry:
    """Holds every action and invokes them uniformly."""

    def __init__(self) -> None:
        self._actions: dict[str, ActionDef] = {}

    # ── registration ──────────────────────────────────────────────────

    def register(self, definition: ActionDef) -> None:
        if definition.id in self._actions:
            raise ValueError(f"Action {definition.id!r} is already registered")
        self._actions[definition.id] = definition
        log.debug("Action registered: %s", definition.id)

    def add_pending(self) -> None:
        """Register every action collected by the ``@action`` decorator."""
        for definition in _pending:
            if definition.id not in self._actions:
                self.register(definition)
        _pending.clear()

    # ── lookup ────────────────────────────────────────────────────────

    def get(self, action_id: str) -> ActionDef:
        try:
            return self._actions[action_id]
        except KeyError:
            raise ActionError(f"Unknown action {action_id!r}") from None

    def all(self) -> Iterable[ActionDef]:
        return tuple(self._actions.values())

    def by_category(self, category: str) -> list[ActionDef]:
        return [a for a in self._actions.values() if a.category == category]

    def tool_schemas(self) -> list[dict[str, Any]]:
        """Every action as an LLM tool definition (automation/tool_adapter)."""
        return [a.json_schema() for a in self._actions.values()]

    # ── invocation ────────────────────────────────────────────────────

    def invoke(self, action_id: str, ctx: Any, **kwargs: Any) -> Any:
        """Run an action. Undoable actions are pushed onto the undo stack.

        Unknown or invalid parameters raise :class:`ActionError`; failures
        inside the action are logged and re-raised so the caller can present
        them, but they never leave the undo stack inconsistent.
        """
        definition = self.get(action_id)
        call_args = self._prepare(definition, kwargs)

        log.info("Invoking action %s(%s)", action_id,
                 ", ".join(f"{k}={v!r}" for k, v in call_args.items()))
        try:
            result = definition.fn(ctx, **call_args)
        except ActionError:
            raise
        except Exception:
            log.exception("Action %s failed", action_id)
            raise

        if definition.undoable and result is not None:
            history = getattr(ctx, "history", None)
            if history is None:
                raise ActionError(
                    f"Action {action_id!r} is undoable but the context has no history"
                )
            history.push(result)
            return None
        return result

    @staticmethod
    def _prepare(definition: ActionDef, kwargs: dict[str, Any]) -> dict[str, Any]:
        unknown = set(kwargs) - set(definition.params)
        if unknown:
            raise ActionError(
                f"Action {definition.id!r} got unknown parameters: "
                f"{', '.join(sorted(unknown))}"
            )
        prepared: dict[str, Any] = {}
        for name, param in definition.params.items():
            if name in kwargs and kwargs[name] is not None:
                try:
                    prepared[name] = param.validate(kwargs[name])
                except ActionError as exc:
                    raise ActionError(f"{definition.id}.{name}: {exc}") from None
            elif param.required:
                raise ActionError(f"Action {definition.id!r} requires {name!r}")
            elif param.default is not None:
                prepared[name] = param.default
        return prepared


# ── decorator ─────────────────────────────────────────────────────────

_pending: list[ActionDef] = []


def action(
    *,
    id: str,
    title_key: str,
    desc_key: str = "",
    category: str = "general",
    params: dict[str, Param] | None = None,
    undoable: bool = False,
    shortcut: str = "",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a function as an action; collected by ``ActionRegistry.add_pending``."""

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        signature = inspect.signature(fn)
        declared = set(params or {})
        accepted = set(list(signature.parameters)[1:])  # skip ctx
        missing = declared - accepted
        if missing:
            raise TypeError(
                f"Action {id!r} declares parameters its function does not accept: "
                f"{', '.join(sorted(missing))}"
            )
        _pending.append(
            ActionDef(
                id=id, fn=fn, title_key=title_key, desc_key=desc_key,
                category=category, params=dict(params or {}),
                undoable=undoable, shortcut=shortcut,
            )
        )
        return fn

    return decorate
