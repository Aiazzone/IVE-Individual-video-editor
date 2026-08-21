"""Composition root: builds every service, wires them and loads the QML shell.

This is the only place that knows about all the modules at once. Everything
else receives what it needs through its constructor.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QCoreApplication, QUrl, Qt
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

from ive.core.actions.context import ActionContext
from ive.core.actions.registry import ActionRegistry
from ive.core.commands.history import UndoStack
from ive.core.services.project_service import ProjectService
from ive.export.service import ExportService
from ive.media.proxy import ProxyManager
from ive.core.events.bus import EventBus
from ive.i18n.translation_manager import TranslationManager, set_manager
from ive.playback.transport import PlaybackService
from ive.settings.service import SettingsService
from ive.utils.paths import get_data_path
from ive.utils.watchdog import MainThreadWatchdog
from ive.ui.bridge import ActionBridge, ShellState, register_singletons
from ive.ui.preview_item import PreviewItem
from ive.ui.theme_service import ThemeService
from ive.utils import paths
from ive.utils.logging_setup import install_qt_message_handler

log = logging.getLogger(__name__)

__all__ = ["Application", "run"]

ORG_NAME = "IVE"
APP_NAME = "IVE"


class Application:
    """Owns the Qt application, the services and the QML engine."""

    def __init__(self, argv: list[str] | None = None) -> None:
        self._argv = argv if argv is not None else sys.argv

        QCoreApplication.setOrganizationName(ORG_NAME)
        QCoreApplication.setApplicationName(APP_NAME)
        self.qt = QGuiApplication(self._argv)
        install_qt_message_handler()

        self._load_fonts()

        # ── services ──────────────────────────────────────────────────
        self.events = EventBus()
        self.settings = SettingsService()
        self.translations = TranslationManager()
        self.translations.set_language(self.settings.get("app.language"))
        set_manager(self.translations)

        self.theme = ThemeService(self.settings)
        self.history = UndoStack()
        self.proxies = ProxyManager(self.settings)
        self.project = ProjectService(self.settings, history=self.history)
        self.playback = PlaybackService(proxies=self.proxies, settings=self.settings)
        self.export = ExportService(playback=self.playback)
        # The project timeline IS what plays. Rebuilding the sequence on every
        # edit keeps the preview and the timeline from ever disagreeing.
        self.project.timelineChanged.connect(self._sync_sequence)
        self.project.mediaChanged.connect(self._queue_proxies)
        # A finished proxy only takes effect once the graph is rebuilt.
        self.proxies.changed.connect(self._sync_sequence)
        self.project.projectChanged.connect(self._sync_sequence)

        self.registry = ActionRegistry()
        self._register_actions()

        self.shell = ShellState(self.settings, self.theme)
        self.context = ActionContext(
            settings=self.settings,
            theme=self.theme,
            translations=self.translations,
            history=self.history,
            events=self.events,
        )
        self.context.extras["playback"] = self.playback
        self.context.project = self.project
        self.context.extras["export"] = self.export
        self.context.extras["proxies"] = self.proxies
        self.actions = ActionBridge(self.registry, self.context)

        # ── QML ───────────────────────────────────────────────────────
        # Order matters: the singletons must be registered BEFORE the engine
        # exists, or PySide6 corrupts type resolution for every component
        # loaded afterwards. See register_singletons() for the full symptom.
        from ive.ui.color_service import ColorLibraryService
        from ive.ui.audio_service import AudioLibraryService
        from ive.ui.motion_service import MotionService
        from ive.ui.music_service import MusicService
        from ive.ui.pack_service import PackService
        from ive.ui.sticker_service import StickerLibraryService
        from ive.ui.thumbnails import ThumbnailService
        from ive.ui.transition_service import TransitionLibraryService
        from ive.ui.waveforms import WaveformService

        self.colorfx = ColorLibraryService(self.translations, self.settings)
        self.stickers = StickerLibraryService(self.translations, self.settings)
        self.transitions = TransitionLibraryService(self.translations,
                                                    self.settings)
        self.motion = MotionService(self.translations)
        self.audiofx = AudioLibraryService(self.translations, self.settings)
        self.music = MusicService(self.translations, self.settings,
                                  self.playback)
        self.packs = PackService(self.translations, self.colorfx,
                                 self.stickers, self.transitions,
                                 motion=self.motion, export=self.export,
                                 audiofx=self.audiofx, music=self.music)
        self.context.extras["packs"] = self.packs
        self.thumbs = ThumbnailService()
        self.waves = WaveformService()
        register_singletons(
            theme=self.theme,
            translations=self.translations,
            shell=self.shell,
            actions=self.actions,
            playback=self.playback,
            project=self.project,
            export=self.export,
            proxies=self.proxies,
            colorfx=self.colorfx,
            thumbs=self.thumbs,
            history=self.history,
            waves=self.waves,
            stickers=self.stickers,
            transitions=self.transitions,
            packs=self.packs,
            motion=self.motion,
            audiofx=self.audiofx,
            music=self.music,
        )
        # Same rule as the singletons: register before the engine exists.
        qmlRegisterType(PreviewItem, "IVE", 1, 0, "PreviewItem")
        self.engine = QQmlApplicationEngine()
        self.engine.addImportPath(str(paths.get_qml_path()))
        self.engine.objectCreationFailed.connect(self._on_creation_failed)
        # Thumbnails are FILES generated by ThumbnailService's worker; QML
        # loads them with Qt's native image loader. There is deliberately
        # no Python image provider: one deadlocked the GUI against Qt's
        # pixmap-store mutex (see ive/ui/thumbnails.py).

        self.settings.changed.connect(self._on_setting_changed)

    # ── lifecycle ─────────────────────────────────────────────────────

    def run(self) -> int:
        """Load the shell and enter the event loop."""
        main_qml = paths.get_qml_path("Main.qml")
        if not main_qml.is_file():
            log.critical("Main.qml not found at %s", main_qml)
            return 2

        log.info("Loading QML shell: %s", main_qml)
        self.engine.load(QUrl.fromLocalFile(str(main_qml)))
        roots = self.engine.rootObjects()
        if not roots:
            log.critical("QML failed to load; see the warnings above")
            return 3

        window = roots[0]
        self.context.window = window
        # Minimising must stop the decorative decode and the glass effects.
        # Without this the loop keeps decoding into a surface nobody can see,
        # and Qt's ShaderEffectSource against a zero-size window is what makes
        # the app appear to hang.
        window.visibilityChanged.connect(self._on_visibility_changed)
        self._detect_glass_support(window)
        self._apply_window_state(window)

        # Armed last, so it never reports the startup work as a stall. It is
        # what turns "it froze" into a stack: see utils/watchdog.py.
        self.watchdog = MainThreadWatchdog(self.qt, threshold=2.0,
                                           log_dir=get_data_path("log"))
        # Also watch that frames actually reach the screen, but only while
        # playing - Qt presents nothing when nothing changes.
        self.watchdog.watch_window(window, lambda: bool(self.playback.playing))
        # A user gesture that paints nothing IS the freeze, so every action
        # arms the render watch for a few seconds. Gating on playback alone
        # left it inert during the very hang it was built to catch.
        # ActionRegistry is a plain class with no signals, so the invoke
        # method is wrapped rather than connected to.
        _invoke = self.actions.invoke

        def _invoke_watched(*args, **kwargs):
            self.watchdog.expect_frames(4.0)
            return _invoke(*args, **kwargs)

        self.actions.invoke = _invoke_watched
        self.watchdog.start()

        log.info("Application started")
        code = self.qt.exec()

        self.watchdog.stop()
        self.proxies.shutdown()
        self.export.shutdown()
        self.project.close()
        self.playback.shutdown()
        self.settings.flush()
        log.info("Application exited with code %s", code)
        return code

    # ── setup helpers ─────────────────────────────────────────────────

    def _register_actions(self) -> None:
        """Import the action modules so their decorators run, then collect."""
        from ive.core.actions.builtin import edit_actions  # noqa: F401
        from ive.core.actions.builtin import media_actions  # noqa: F401
        from ive.core.actions.builtin import export_actions  # noqa: F401
        from ive.core.actions.builtin import project_actions  # noqa: F401
        from ive.core.actions.builtin import proxy_actions  # noqa: F401
        from ive.core.actions.builtin import timeline_actions  # noqa: F401
        from ive.core.actions.builtin import shell_actions  # noqa: F401
        from ive.core.actions.builtin import color_actions  # noqa: F401
        from ive.core.actions.builtin import audio_actions  # noqa: F401
        from ive.core.actions.builtin import sticker_actions  # noqa: F401
        from ive.core.actions.builtin import text_actions  # noqa: F401
        from ive.core.actions.builtin import transition_actions  # noqa: F401
        from ive.core.actions.builtin import pack_actions  # noqa: F401

        self.registry.add_pending()
        log.info("Registered %d actions", len(tuple(self.registry.all())))

    def _load_fonts(self) -> None:
        """Load bundled fonts; fall back to the system font when absent."""
        font_dir = paths.get_asset_path("fonts")
        families: list[str] = []
        if font_dir.is_dir():
            for path in sorted(font_dir.glob("*.tt[fc]")) + sorted(font_dir.glob("*.otf")):
                font_id = QFontDatabase.addApplicationFont(str(path))
                if font_id < 0:
                    log.warning("Could not load font %s", path.name)
                    continue
                families += QFontDatabase.applicationFontFamilies(font_id)
        if families:
            log.info("Bundled fonts: %s", ", ".join(sorted(set(families))))
            self.qt.setFont(QFont(families[0], 10))
        else:
            log.info("No bundled fonts found; using the system font")

        icon = paths.get_asset_path("icons/app.png")
        if icon.is_file():
            self.qt.setWindowIcon(QIcon(str(icon)))

    def _detect_glass_support(self, window) -> None:
        """Glass needs a hardware scene graph; the software backend is too slow."""
        supported = True
        try:
            api = QQuickWindow.graphicsApi()
            supported = api != QSGRendererInterface.GraphicsApi.Software
            log.info("Scene graph backend: %s (glass supported: %s)", api, supported)
        except Exception:
            log.exception("Could not query the graphics backend; assuming glass works")
        self.shell.set_glass_supported(supported)

    def _apply_window_state(self, window) -> None:
        """Restore fullscreen, screen and geometry from the previous session."""
        wanted_screen = self.settings.get("window.screen")
        if wanted_screen:
            for screen in self.qt.screens():
                if screen.name() == wanted_screen:
                    window.setScreen(screen)
                    break
            else:
                log.info("Screen %r is gone; using the primary screen", wanted_screen)

        geometry = self.settings.get("window.geometry")
        if isinstance(geometry, list) and len(geometry) == 4:
            try:
                x, y, w, h = (int(v) for v in geometry)
                window.setX(x)
                window.setY(y)
                window.setWidth(max(960, w))
                window.setHeight(max(600, h))
            except (TypeError, ValueError):
                log.warning("Stored geometry is unusable: %r", geometry)

        fullscreen = bool(self.settings.get("window.fullscreen"))
        window.setProperty("isFullscreen", fullscreen)
        window.setVisibility(
            QQuickWindow.Visibility.FullScreen if fullscreen
            else QQuickWindow.Visibility.Windowed
        )
        log.info("Window shown (fullscreen=%s)", fullscreen)

    def _on_visibility_changed(self, visibility) -> None:
        """Minimised or hidden: stop everything that costs per frame."""
        # PySide hands over the Visibility enum itself, which int() refuses.
        # Compare against the enum members instead of numeric values.
        hidden = visibility in (
            QQuickWindow.Visibility.Hidden,
            QQuickWindow.Visibility.Minimized,
        )
        log.info("Window visibility=%s (hidden=%s)", visibility, hidden)
        self.shell.set_window_hidden(hidden)

    # The looping backdrop is drawn in QML now (shell/IdleBackdrop.qml), so
    # there is no decoder to start and stop. Removing the service took a
    # continuous 720p decode off the machine.

    def _queue_proxies(self) -> None:
        """Anything heavy enough gets a stand-in, without being asked."""
        paths = [m["path"] for m in self.project.media if not m.get("missing")]
        self.proxies.request_many(paths)

    def _sync_sequence(self) -> None:
        """Hand the current timeline to the transport."""
        clips = self.project.timelineClips
        if clips:
            self.playback.open_sequence(clips)
        elif self.playback.isSequence:
            # The timeline emptied out; stop pretending there is something.
            self.playback.close()

    def _on_setting_changed(self, key: str, value) -> None:
        if key == "app.language":
            self.translations.set_language(value)
        elif key == "app.theme":
            self.theme.set_theme(value, persist=False)
        elif key in ("appearance.glass_opacity", "appearance.glass_blur"):
            self.theme.set_glass_overrides(
                float(self.settings.get("appearance.glass_opacity")),
                int(self.settings.get("appearance.glass_blur")),
            )
        elif key == "log.level":
            logging.getLogger().setLevel(getattr(logging, str(value), logging.INFO))

    def _on_creation_failed(self, url: QUrl) -> None:
        log.critical("QML object creation failed for %s", url.toString())


def run(argv: list[str] | None = None) -> int:
    """Entry point used by ``__main__``."""
    # Qt 6 picks a sensible default, but be explicit about DPI rounding so the
    # shell looks the same on fractional-scaling Windows setups.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    return Application(argv).run()
