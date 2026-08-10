"""Centralised path resolution for the "three sisters" layout.

The install root contains three sibling folders with different lifecycles::

    <install_root>/
        ive/         program  - replaced on every update
        models/      AI weights - replaced rarely
        user_data/   user data  - never touched by updates

Nothing in the codebase may compute ``Path(__file__).parents[N]`` on its own.
Every path goes through the helpers in this module.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

__all__ = [
    "install_root",
    "get_asset_path",
    "get_qml_path",
    "get_defaults_path",
    "get_model_path",
    "get_data_path",
    "bootstrap_user_data",
    "is_frozen",
    "local_path_from_url",
]


def local_path_from_url(value: str) -> str:
    """A filesystem path from what QML hands over, which may be a file: URL.

    The one place this conversion happens. The naive
    ``replace("file:///", "")`` that used to be scattered around had three
    real failures: no percent-decoding, so any path with a space or an
    accent (``clip%201.mp4``, ``Citt%C3%A0``) pointed at a file that does
    not exist; the leading slash of POSIX paths was lost, turning
    ``/home/u/v.mp4`` into a relative path; and UNC shares
    (``file://server/share``) lost their ``//``.
    """
    from urllib.parse import unquote, urlsplit

    text = str(value)
    if not text.startswith("file:"):
        return text
    parts = urlsplit(text)
    path = unquote(parts.path)
    if parts.netloc:                                   # file://server/share
        return f"//{parts.netloc}{path}"
    if len(path) > 2 and path[0] == "/" and path[2] == ":":
        return path[1:]                                # /C:/x -> C:/x
    return path

# Sub-folders created in user_data/ on first run.
_USER_DATA_DIRS = (
    "settings",
    "log",
    "cache",
    "cache/thumbnails",
    "cache/waveforms",
    "cache/proxies",
    "projects",
    "autosave",
    "packs",
    "themes",
    "plugins",
)


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def install_root() -> Path:
    """Root folder holding ``ive/``, ``models/`` and ``user_data/``."""
    if is_frozen():
        # <root>/ive/ive.exe  ->  <root>
        return Path(sys.executable).resolve().parent.parent
    # <root>/ive/src/ive/utils/paths.py  ->  <root>
    return Path(__file__).resolve().parents[4]


def _bundle_root() -> Path:
    """Folder holding read-only resources shipped with the program."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return install_root() / "ive"


def get_asset_path(relative: str = "") -> Path:
    """Read-only assets: icons, fonts, splash."""
    base = _bundle_root() / "assets"
    return base / relative if relative else base


def get_qml_path(relative: str = "") -> Path:
    """QML sources shipped with the program."""
    base = _bundle_root() / "qml"
    return base / relative if relative else base


def get_defaults_path(relative: str = "") -> Path:
    """Factory configuration templates copied to user_data on first run."""
    base = _bundle_root() / "config" / "defaults"
    return base / relative if relative else base


def get_model_path(relative: str = "") -> Path:
    """AI model weights. Read-only, but outside the bundle."""
    base = install_root() / "models"
    return base / relative if relative else base


def get_data_path(relative: str = "") -> Path:
    """Writable user data. Preserved across updates."""
    base = install_root() / "user_data"
    base.mkdir(parents=True, exist_ok=True)
    return base / relative if relative else base


def bootstrap_user_data() -> None:
    """Create the expected user_data sub-folders and copy missing defaults.

    Idempotent: existing user files are never overwritten, so an update only
    adds templates introduced since the previous release.

    Must run before anything writes to disk, the logger included.
    """
    for sub in _USER_DATA_DIRS:
        (get_data_path() / sub).mkdir(parents=True, exist_ok=True)

    defaults = get_defaults_path()
    if not defaults.is_dir():
        return

    settings_dir = get_data_path("settings")
    for src in defaults.rglob("*"):
        if not src.is_file():
            continue
        dst = settings_dir / src.relative_to(defaults)
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dst)
        except OSError as exc:  # pragma: no cover - depends on the filesystem
            # Not fatal: the app falls back to in-code defaults.
            print(f"[bootstrap] could not copy {src.name}: {exc}", file=sys.stderr)


def describe() -> str:
    """One-line summary of the resolved layout, for the startup log."""
    return (
        f"frozen={is_frozen()} root={install_root()} "
        f"bundle={_bundle_root()} data={get_data_path()}"
    )


# Qt on some Linux setups needs an explicit runtime dir; harmless elsewhere.
if sys.platform.startswith("linux"):
    os.environ.setdefault("XDG_RUNTIME_DIR", str(get_data_path("cache")))
