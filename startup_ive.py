"""Developer launcher.

Exists only to give the project a recognisable name in the editor's run list.
It delegates straight to the package entry point; PyInstaller targets
``ive/src/ive/__main__.py``, not this file.

    python startup_ive.py
"""

from __future__ import annotations

import os
import runpy
import sys

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ive", "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

if __name__ == "__main__":
    runpy.run_module("ive", run_name="__main__", alter_sys=True)
