"""Entry point: ``python -m ive``.

Order matters here. Nothing may write to disk - the logger included - before
``bootstrap_user_data()`` has created the folders, and logging must be
configured before any heavy import so failures during import are captured.

This module is also the PyInstaller entry script. ``startup_ive.py`` at the
repository root is only a developer convenience.
"""

from __future__ import annotations

import os
import sys


def _platform_workarounds() -> None:
    """Environment tweaks that are no-ops on the wrong platform."""
    # Windows: avoids STATUS_ACCESS_VIOLATION when several native math
    # libraries (OpenMP) are loaded in one process.
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    # Jetson / aarch64 Linux: prevents TLS allocation errors with ONNX Runtime.
    gomp = "/lib/aarch64-linux-gnu/libgomp.so.1"
    if os.path.exists(gomp):
        os.environ["LD_PRELOAD"] = gomp + ":" + os.environ.get("LD_PRELOAD", "")


def main() -> int:
    _platform_workarounds()

    # In development the package lives in ive/src/; make it importable without
    # requiring an editable install.
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if here not in sys.path:
        sys.path.insert(0, here)

    from ive.utils.paths import bootstrap_user_data, describe

    bootstrap_user_data()

    from ive.utils.logging_setup import setup_logging

    setup_logging()

    import logging

    log = logging.getLogger("ive")
    log.info("=" * 70)
    log.info("IVE starting - python %s", sys.version.split()[0])
    log.info("Layout: %s", describe())

    from ive.app import run

    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
