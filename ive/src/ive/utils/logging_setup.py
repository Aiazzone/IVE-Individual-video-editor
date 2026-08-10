"""Logging and crash diagnostics.

Produces three files in ``user_data/log/``:

===================  =========================================================
``ive.log``          application log, rotating (5 x 2 MB)
``faulthandler.log`` native crashes (FFmpeg, GPU drivers, ONNX Runtime)
``events.log``       business events, rotating daily, kept 30 days
===================  =========================================================

``setup_logging()`` must be called from ``__main__`` *before* any heavy import,
so failures during import are captured too.
"""

from __future__ import annotations

import atexit
import faulthandler
import logging
import logging.handlers
import sys
import threading
import traceback
from types import TracebackType

from ive.utils.paths import get_data_path

__all__ = ["setup_logging", "events_logger", "install_qt_message_handler"]

_LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(threadName)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_fault_file = None  # keep the handle alive for the whole process lifetime
_configured = False


def setup_logging(level: int = logging.INFO, console: bool = True) -> None:
    """Configure the root logger, crash handlers and exception hooks."""
    global _fault_file, _configured
    if _configured:
        return

    log_dir = get_data_path("log")
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "ive.log", maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # In a frozen build with console=False stdout is gone; guard the handler.
    if console and sys.stderr is not None:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        root.addHandler(stream)

    # Native crash dumps. NOTE: dump_traceback_later()/heartbeat must stay off -
    # it caused heap corruption with native video libraries on Windows.
    _fault_file = open(log_dir / "faulthandler.log", "a", encoding="utf-8")
    faulthandler.enable(file=_fault_file, all_threads=True)

    _install_excepthooks()
    atexit.register(_dump_threads_on_exit)

    _configured = True
    logging.getLogger(__name__).info("Logging initialised: %s", log_dir)


def events_logger() -> logging.Logger:
    """Separate logger for business events, isolated from the root logger."""
    logger = logging.getLogger("ive.events")
    if logger.handlers:
        return logger

    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = logging.handlers.TimedRotatingFileHandler(
        get_data_path("log") / "events.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", _DATE_FORMAT))
    logger.addHandler(handler)
    return logger


def _install_excepthooks() -> None:
    logger = logging.getLogger("ive.crash")

    def hook(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logger.critical("Unhandled exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = hook

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        if issubclass(args.exc_type, SystemExit):
            return
        logger.critical(
            "Unhandled exception in thread %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = thread_hook


def _dump_threads_on_exit() -> None:
    """Dump every thread stack at shutdown - invaluable when the app hangs."""
    logger = logging.getLogger("ive.shutdown")
    try:
        frames = sys._current_frames()
    except Exception:  # pragma: no cover - interpreter teardown
        return
    for thread in threading.enumerate():
        frame = frames.get(thread.ident)
        if frame is None:
            continue
        stack = "".join(traceback.format_stack(frame))
        # INFO, not DEBUG: the root logger runs at INFO by default, so a
        # DEBUG dump never reached the log - dead diagnostics precisely in
        # the "invaluable when the app hangs" case it exists for.
        logger.info("Thread %s (daemon=%s):\n%s", thread.name, thread.daemon, stack)


def install_qt_message_handler() -> None:
    """Route Qt and QML diagnostics into the application log.

    Call after the QGuiApplication exists. QML warnings are real defects
    (see docs/UI_STYLE_GUIDE.md), so they are logged at WARNING and above.
    """
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    logger = logging.getLogger("qt")
    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handler(mode, context, message: str) -> None:
        where = ""
        if context is not None and context.file:
            where = f" ({context.file}:{context.line})"
        logger.log(levels.get(mode, logging.INFO), "%s%s", message, where)

    qInstallMessageHandler(handler)
