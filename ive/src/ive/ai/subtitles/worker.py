"""The transcription worker: a separate PROCESS, on purpose.

Two reasons, both hard requirements:

* **Crash isolation** (docs/AI_FEATURES.md): CTranslate2 is native code;
  if it dies, it must take this process with it, not the editor.
* **The duplicate OpenMP abort**: ctranslate2 ships its own
  ``libiomp5md.dll``, and in the shared venv other packages (torch, the
  Intel runtime in Library/bin) already load theirs - importing
  ctranslate2 in the app process aborts with ``OMP Error #15`` before
  Python even sees an exception. Here the standard workaround is set
  BEFORE anything native loads, and its blast radius is this process
  alone. The app process never imports faster_whisper or ctranslate2.

Protocol, line-JSON over the pipes:

* stdin: one job object -
  ``{"model_id", "language", "clips": [{"path", "start", "sourceIn",
  "duration"}, ...]}``
* stdout: ``{"progress": 0..1}`` lines while working, then exactly one
  ``{"lines": [{"start", "end", "text"}, ...]}`` or ``{"error": "..."}``.
* stderr: logging, forwarded to the app's log by the service.

Cancellation is the parent killing the process: nothing here holds
state anyone would miss.

Run as ``python -m ive.ai.subtitles.worker`` with ``ive/src`` on the
path (the service passes it via PYTHONPATH).
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
    log = logging.getLogger("ive.ai.subtitles.worker")

    try:
        job = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"error": f"bad job: {exc}"}), flush=True)
        return 2

    from ive.ai.subtitles.task import SubtitleTask, TranscribeError

    task = SubtitleTask(str(job.get("model_id") or "whisper-small"))
    state = task.availability()
    if state != "ready":
        print(json.dumps({"error": state}), flush=True)
        return 3

    def progress(fraction: float) -> None:
        print(json.dumps({"progress": round(float(fraction), 4)}),
              flush=True)

    try:
        lines = task.run_on_clips(
            list(job.get("clips") or []),
            language=str(job.get("language") or ""),
            progress=progress)
    except TranscribeError as exc:
        log.error("Transcription failed: %s", exc)
        print(json.dumps({"error": str(exc)}), flush=True)
        return 4
    except Exception as exc:                      # noqa: BLE001
        log.exception("Worker died unexpectedly")
        print(json.dumps({"error": f"unexpected: {exc}"}), flush=True)
        return 5

    print(json.dumps({"lines": [
        {"start": round(line.start, 3), "end": round(line.end, 3),
         "text": line.text,
         "words": [{"start": round(float(w["start"]), 3),
                    "end": round(float(w["end"]), 3),
                    "text": str(w["text"])} for w in line.words]}
        for line in lines]}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
