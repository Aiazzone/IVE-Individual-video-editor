"""Objects exposed to QML.

Three singletons, all following the same shape: a **map property** that QML
binds to, so a change re-evaluates every binding with no per-widget work.

===========  =========================  ==================================
``Theme``    ``Theme.c`` / ``Theme.m``  colours and metrics
``Tr``       ``Tr.s["key"]``            translated strings
``Shell``    ``Shell.v.railSide``       shell layout state
``Actions``  ``Actions.invoke(id, {})`` the only way QML mutates anything
===========  =========================  ==================================

QML never writes a setting directly: it invokes an action. That is what keeps
every operation reachable from the command palette, a script, a plugin and the
assistant, not only by clicking.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

log = logging.getLogger(__name__)

__all__ = ["ActionBridge", "ShellState", "register_singletons"]


#: Settings keys mirrored into ``Shell.v``, with their QML-side names.
_SHELL_KEYS = {
    "shell.rail_side": "railSide",
    "shell.transport_position": "transportPosition",
    "shell.readout_corner": "readoutCorner",
    "shell.timeline_height": "timelineHeight",
    "shell.panel_autohide": "panelAutohide",
    "shell.panel_hide_delay_ms": "panelHideDelay",
    "shell.panel_pinned": "panelPinned",
    "shell.ambient_backdrop": "ambientBackdrop",
    "appearance.idle_background": "idleBackground",
    "appearance.glass": "glassMode",
    "appearance.glass_opacity": "glassOpacity",
    "appearance.glass_blur": "glassBlur",
    "appearance.reduce_transparency": "reduceTransparency",
    "appearance.reduce_motion": "reduceMotion",
    "project.canvas": "projectCanvas",
    "media.proxy_enabled": "proxyEnabled",
    "playback.volume": "volume",
    "playback.muted": "muted",
}


class ShellState(QObject):
    """Shell layout and appearance, mirrored from settings for QML binding."""

    changed = Signal()

    def __init__(self, settings, theme, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._theme = theme
        self._glass_supported = True
        self._window_hidden = False
        #: The timeline clip the UI is focused on. Shared shell state, not
        #: project state: the timeline, the on-video handles and the Text
        #: panel all read and write the SAME selection, which is what lets
        #: selecting a title on the video open its words in the panel.
        self._selected_clip = ""
        self._selected_kind = ""
        self._values: dict[str, Any] = {}
        self._rebuild()
        settings.changed.connect(self._on_setting_changed)

    @Property("QVariantMap", notify=changed)
    def v(self) -> dict[str, Any]:
        """Every shell value QML needs, in one reactive map."""
        return self._values

    @property
    def windowHidden(self) -> bool:
        return self._window_hidden

    @Slot(bool)
    def set_window_hidden(self, hidden: bool) -> None:
        """Minimised or hidden: every per-frame effect must stop."""
        if hidden == self._window_hidden:
            return
        self._window_hidden = hidden
        self._rebuild()

    @Slot(str, str)
    def set_selected_clip(self, clip_id: str, kind: str) -> None:
        """Focus a timeline clip ("" to clear). Kind names the lane tapped."""
        clip_id, kind = str(clip_id), str(kind)
        if (clip_id, kind) == (self._selected_clip, self._selected_kind):
            return
        self._selected_clip = clip_id
        self._selected_kind = kind
        self._rebuild()

    @Slot(bool)
    def set_glass_supported(self, supported: bool) -> None:
        """Result of the runtime capability check, from the composition root."""
        if supported == self._glass_supported:
            return
        self._glass_supported = supported
        log.info("Glass surfaces %s by the graphics backend",
                 "supported" if supported else "not supported")
        self._rebuild()

    # ── internals ─────────────────────────────────────────────────────

    def _on_setting_changed(self, key: str, _value: Any) -> None:
        if key in _SHELL_KEYS:
            self._rebuild()

    def _rebuild(self) -> None:
        values = {name: self._settings.get(key) for key, name in _SHELL_KEYS.items()}

        mode = values["glassMode"]
        active = (
            not values["reduceTransparency"]
            and mode != "never"
            and (mode == "always" or self._glass_supported)
        )
        values["glassSupported"] = self._glass_supported
        values["windowHidden"] = self._window_hidden
        values["selectedClipId"] = self._selected_clip
        values["selectedKind"] = self._selected_kind
        # A hidden window renders nothing worth blurring, and sampling it is
        # exactly what stalls.
        values["glassActive"] = active and not self._window_hidden
        # Below this the scrim no longer guarantees 4.5:1 on a
        # bright frame; the settings panel says so.
        values["glassBelowSafe"] = values["glassOpacity"] < 0.55

        self._values = values
        self._theme.set_glass_enabled(active)
        self.changed.emit()


class ActionBridge(QObject):
    """Lets QML invoke registered actions - and nothing else."""

    failed = Signal(str, str)  # action id, message

    def __init__(self, registry, context, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._context = context

    @Slot(str)
    @Slot(str, "QVariantMap")
    def invoke(self, action_id: str, args: dict[str, Any] | None = None) -> None:
        """Run an action by id. Errors are logged and reported, never raised into QML."""
        try:
            self._registry.invoke(action_id, self._context, **(args or {}))
        except Exception as exc:
            log.exception("Action %s failed when invoked from QML", action_id)
            self.failed.emit(action_id, str(exc))

    @Slot(str, result=str)
    def shortcut(self, action_id: str) -> str:
        """Keyboard shortcut declared for an action, for tooltips."""
        try:
            return self._registry.get(action_id).shortcut
        except Exception:
            return ""

    @Property("QVariantList", constant=True)
    def catalogue(self) -> list[dict[str, str]]:
        """Every action, for the command palette."""
        return [
            {
                "id": a.id,
                "titleKey": a.title_key,
                "category": a.category,
                "shortcut": a.shortcut,
            }
            for a in self._registry.all()
        ]


def register_singletons(*, theme, translations, shell, actions,
                        playback=None,
                        project=None, export=None, proxies=None,
                        colorfx=None, thumbs=None, history=None,
                        waves=None, stickers=None, transitions=None,
                        packs=None, motion=None, audiofx=None,
                        music=None) -> None:
    """Expose the four singletons to QML under the ``IVE`` import namespace.

    .. warning::
       **Call this before constructing the QML engine.**

       On PySide6 6.11, ``qmlRegisterSingletonInstance()`` invoked *after* a
       ``QQmlApplicationEngine`` exists corrupts type resolution for every
       component loaded afterwards. The symptom is misleading - loading any
       QML file with child elements fails with::

           Cannot assign object of type "QQuickRectangle"
           to list property "data"; expected "QObject"

       which points at the child element and looks like a bug in the QML file.
       It is not: the file is fine, the registration order is wrong. Registering
       first, then creating the engine, works.

       Diagnosing this is made harder by the QML type cache: once a component
       has loaded successfully it stays cached, so a second load in the same
       process succeeds even after the registry has been corrupted. Test this
       kind of failure with one fresh process per case.
    """
    from PySide6.QtQml import qmlRegisterSingletonInstance

    qmlRegisterSingletonInstance(type(theme), "IVE", 1, 0, "Theme", theme)
    qmlRegisterSingletonInstance(type(translations), "IVE", 1, 0, "Tr", translations)
    qmlRegisterSingletonInstance(type(shell), "IVE", 1, 0, "Shell", shell)
    qmlRegisterSingletonInstance(type(actions), "IVE", 1, 0, "Actions", actions)
    if playback is not None:
        qmlRegisterSingletonInstance(type(playback), "IVE", 1, 0, "Playback", playback)
    if project is not None:
        qmlRegisterSingletonInstance(type(project), "IVE", 1, 0, "Project", project)
    if export is not None:
        qmlRegisterSingletonInstance(type(export), "IVE", 1, 0, "Export", export)
    if proxies is not None:
        qmlRegisterSingletonInstance(type(proxies), "IVE", 1, 0, "Proxies", proxies)
    if colorfx is not None:
        qmlRegisterSingletonInstance(type(colorfx), "IVE", 1, 0, "ColorFx", colorfx)
    if thumbs is not None:
        qmlRegisterSingletonInstance(type(thumbs), "IVE", 1, 0, "Thumbs", thumbs)
    if history is not None:
        # Read-only from QML: buttons bind canUndo/canRedo; mutation goes
        # through the edit.undo / edit.redo actions like everything else.
        qmlRegisterSingletonInstance(type(history), "IVE", 1, 0, "History", history)
    if waves is not None:
        qmlRegisterSingletonInstance(type(waves), "IVE", 1, 0, "Waves", waves)
    if stickers is not None:
        qmlRegisterSingletonInstance(type(stickers), "IVE", 1, 0, "Stickers", stickers)
    if transitions is not None:
        qmlRegisterSingletonInstance(type(transitions), "IVE", 1, 0,
                                     "Transitions", transitions)
    if packs is not None:
        qmlRegisterSingletonInstance(type(packs), "IVE", 1, 0,
                                     "Packs", packs)
    if motion is not None:
        qmlRegisterSingletonInstance(type(motion), "IVE", 1, 0,
                                     "Motion", motion)
    if audiofx is not None:
        qmlRegisterSingletonInstance(type(audiofx), "IVE", 1, 0,
                                     "AudioFx", audiofx)
    if music is not None:
        qmlRegisterSingletonInstance(type(music), "IVE", 1, 0,
                                     "Music", music)
    log.debug("QML singletons registered under the IVE namespace")
