#!/usr/bin/env bash
# IVE - Individual Video Editor : Linux / macOS launcher.
# The Windows counterpart is startup_ive.bat; keep the two in step.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

# Interpreter search order: explicit override, per-project venv,
# shared venv four levels up, then whatever is on PATH.
PY=""
for candidate in \
    "${IVE_PYTHON:-}" \
    "$HERE/.venv/bin/python" \
    "$HERE/../../../../.venv/bin/python" \
    "$(command -v python3 || true)"
do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "[IVE] No Python interpreter found." >&2
    echo "      Set one explicitly:  export IVE_PYTHON=/path/to/python" >&2
    exit 127
fi

echo "[IVE] Interpreter: $PY"
exec "$PY" "$HERE/startup_ive.py" "$@"
