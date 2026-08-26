"""The translation worker: a separate PROCESS, same story as subtitles.

ctranslate2 cannot load in the app process (duplicate-OpenMP abort,
documented in ive/ai/subtitles/worker.py); here the workaround is
confined and a native crash takes only this process.

Protocol, line-JSON over the pipes:

* stdin: ``{"source", "target", "texts": [...]}``
* stdout: ``{"progress": 0..1}`` lines, then exactly one
  ``{"texts": [...]}`` (same length and order) or ``{"error": "..."}``.
* stderr: logging, forwarded to the app's log.

Cancellation is the parent killing the process.
Run as ``python -m ive.ai.translate.worker`` with ``ive/src`` on the
path.
"""

from __future__ import annotations

import json
import logging
import os
import sys

# Must precede any import that could pull native OpenMP code in.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


def main() -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("ive.ai.translate.worker")

    try:
        job = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"error": f"bad job: {exc}"}), flush=True)
        return 2

    from ive.ai.translate.task import TranslateError, TranslateTask

    source = str(job.get("source") or "")
    target = str(job.get("target") or "")
    texts = [str(t) for t in (job.get("texts") or [])]
    state = TranslateTask.availability(source, target)
    if state != "ready":
        print(json.dumps({"error": state}), flush=True)
        return 3

    def progress(fraction: float) -> None:
        print(json.dumps({"progress": round(float(fraction), 4)}),
              flush=True)

    try:
        out = TranslateTask().translate(texts, source, target,
                                        progress=progress)
    except TranslateError as exc:
        log.error("Translation failed: %s", exc)
        print(json.dumps({"error": str(exc)}), flush=True)
        return 4
    except Exception as exc:                      # noqa: BLE001
        log.exception("Worker died unexpectedly")
        print(json.dumps({"error": f"unexpected: {exc}"}), flush=True)
        return 5

    print(json.dumps({"texts": out}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
