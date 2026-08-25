"""Automatic subtitles for QML: model state, download, generation.

The QML side sees one singleton (``Subtitles``) with three concerns:

* **state** - whether the feature can run: the model may be missing
  (an invitation to download, with size and licence on show), the
  backend absent, or everything ready. A missing model is a state,
  never an error (docs/AI_FEATURES.md).
* **download** - explicit, hash-verified (ive/ai/downloader.py), with
  progress and cancel; runs on a plain thread, the GUI never blocks.
* **generation** - the transcription runs in a SEPARATE PROCESS
  (ive/ai/subtitles/worker.py - crash isolation plus the duplicate-
  OpenMP abort that forbids loading ctranslate2 in the app process).
  Progress lines stream back over stdout; the finished lines land on
  the project through ``place_subtitles`` in one undo step.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, QProcess, Signal, Slot

from ive.ai import fetch_model, model_entry, ModelDownloadError
from ive.ai.subtitles import SubtitleTask

log = logging.getLogger(__name__)

__all__ = ["SubtitleService"]


class SubtitleService(QObject):
    """State machine behind the "Automatic subtitles" card."""

    stateChanged = Signal()
    downloadChanged = Signal()
    runChanged = Signal()
    #: Lines landed on the timeline (count). For the UI's closing note.
    finished = Signal(int)

    def __init__(self, settings, project, parent: QObject | None = None
                 ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._project = project
        self._downloading = False
        self._download_progress = 0.0
        self._download_cancel = threading.Event()
        self._download_thread: threading.Thread | None = None
        self._running = False
        self._progress = 0.0
        self._error = ""
        self._last_count = 0
        self._process: QProcess | None = None
        self._stdout = b""

    # ── model state ───────────────────────────────────────────────────

    def _model_id(self) -> str:
        return str(self._settings.get("ai.subtitles_model")
                   or "whisper-small")

    @Property(str, notify=stateChanged)
    def state(self) -> str:
        """"ready" | "model_missing" | "backend_missing"."""
        if getattr(sys, "frozen", False):
            # The worker is launched as `python -m`; a frozen build has
            # no interpreter to hand it to. Fase 10 packaging will ship
            # one; until then the feature declares itself absent.
            return "backend_missing"
        return SubtitleTask(self._model_id()).availability()

    @Property(str, notify=stateChanged)
    def modelName(self) -> str:
        entry = model_entry(self._model_id())
        return str(entry["name"]) if entry else self._model_id()

    @Property(int, notify=stateChanged)
    def modelSizeMb(self) -> int:
        entry = model_entry(self._model_id())
        return int(round(entry["total_size"] / 1e6)) if entry else 0

    @Property(str, notify=stateChanged)
    def modelLicense(self) -> str:
        entry = model_entry(self._model_id())
        return str(entry["weights_license"]) if entry else ""

    @Slot()
    def refresh(self) -> None:
        self.stateChanged.emit()

    # ── download ──────────────────────────────────────────────────────

    @Property(bool, notify=downloadChanged)
    def downloading(self) -> bool:
        return self._downloading

    @Property(float, notify=downloadChanged)
    def downloadProgress(self) -> float:
        return self._download_progress

    @Property(str, notify=runChanged)
    def error(self) -> str:
        return self._error

    @Property(int, notify=runChanged)
    def lastCount(self) -> int:
        return self._last_count

    @Slot(result=bool)
    def download_model(self) -> bool:
        """Fetch the configured model's weights. Explicit, cancellable."""
        if self._downloading:
            return False
        model_id = self._model_id()
        self._downloading = True
        self._download_progress = 0.0
        self._download_cancel.clear()
        self.downloadChanged.emit()

        def run() -> None:
            try:
                fetch_model(model_id, progress=self._on_download_progress,
                            cancelled=self._download_cancel.is_set)
                log.info("Subtitle model %s installed", model_id)
            except ModelDownloadError as exc:
                if exc.reason != "cancelled":
                    log.warning("Subtitle model download failed: %s", exc)
                    self._error = f"download_{exc.reason}"
            finally:
                self._downloading = False
                self.downloadChanged.emit()
                self.stateChanged.emit()
                self.runChanged.emit()

        self._error = ""
        self._download_thread = threading.Thread(
            target=run, name="subtitle-model-download", daemon=True)
        self._download_thread.start()
        return True

    def _on_download_progress(self, done: int, total: int) -> None:
        fraction = done / total if total else 0.0
        if fraction - self._download_progress >= 0.01 or fraction >= 1.0:
            self._download_progress = fraction
            self.downloadChanged.emit()

    @Slot()
    def cancel_download(self) -> None:
        self._download_cancel.set()

    # ── generation ────────────────────────────────────────────────────

    @Property(bool, notify=runChanged)
    def running(self) -> bool:
        return self._running

    @Property(float, notify=runChanged)
    def progress(self) -> float:
        return self._progress

    def _speech_clips(self) -> list[dict]:
        """The A/V clips whose sound can carry speech, timeline order.

        Track 0 only: the Music lane is a bed by definition, and text,
        stickers and colour spans have no sound at all.
        """
        clips = []
        for clip in self._project.timelineClips:
            if (clip.get("track") == 0 and clip.get("hasAudio")
                    and not clip.get("missing") and clip.get("path")
                    and not clip.get("muted")):
                clips.append({"path": clip["path"],
                              "start": float(clip["start"]),
                              "sourceIn": float(clip["sourceIn"]),
                              "duration": float(clip["duration"])})
        clips.sort(key=lambda c: c["start"])
        return clips

    @Slot(result=bool)
    def generate(self) -> bool:
        """Transcribe the cut and lay the lines on the Text lane."""
        if self._running or self.state != "ready":
            return False
        clips = self._speech_clips()
        if not clips:
            self._error = "no_speech_clips"
            self.runChanged.emit()
            return False

        import ive

        job = {"model_id": self._model_id(),
               "language": str(self._settings.get("ai.subtitles_language")
                               or ""),
               "clips": clips}
        from PySide6.QtCore import QProcessEnvironment

        process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONPATH", os.pathsep.join(filter(None, [
            str(Path(ive.__file__).parents[1]),
            env.value("PYTHONPATH", "")])))
        process.setProcessEnvironment(env)
        process.readyReadStandardOutput.connect(self._on_worker_output)
        process.readyReadStandardError.connect(self._on_worker_log)
        process.finished.connect(self._on_worker_finished)
        self._process = process
        self._stdout = b""
        self._error = ""
        self._last_count = 0
        self._running = True
        self._progress = 0.0
        self.runChanged.emit()
        log.info("Subtitle generation started: %d clip(s), model %s",
                 len(clips), job["model_id"])
        process.start(sys.executable, ["-m", "ive.ai.subtitles.worker"])
        process.write(json.dumps(job).encode("utf-8"))
        process.closeWriteChannel()
        return True

    @Slot()
    def cancel(self) -> None:
        """Stop the run: the worker holds no state worth a goodbye."""
        process = self._process
        if process is not None and self._running:
            log.info("Subtitle generation cancelled")
            self._error = "cancelled"
            process.kill()

    def _on_worker_output(self) -> None:
        process = self._process
        if process is None:
            return
        self._stdout += bytes(process.readAllStandardOutput().data())
        while b"\n" in self._stdout:
            line, self._stdout = self._stdout.split(b"\n", 1)
            self._handle_worker_line(line.strip())

    def _handle_worker_line(self, line: bytes) -> None:
        if not line:
            return
        try:
            message = json.loads(line.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            log.warning("Unreadable worker line: %r", line[:120])
            return
        if "progress" in message:
            self._progress = float(message["progress"])
            self.runChanged.emit()
        elif "error" in message:
            self._error = str(message["error"])
        elif "lines" in message:
            if self._error == "cancelled":
                # kill() on a process still STARTING is a no-op on
                # Windows; the run can then finish anyway. The user
                # said stop: the result is thrown away, not applied.
                return
            count = self._project.place_subtitles(list(message["lines"]))
            self._last_count = count
            if count == 0 and not self._error:
                self._error = "no_speech_found"

    def _on_worker_log(self) -> None:
        process = self._process
        if process is None:
            return
        text = bytes(process.readAllStandardError().data()) \
            .decode("utf-8", "replace").strip()
        for line in text.splitlines():
            if line.strip():
                log.info("[worker] %s", line.strip())

    def _on_worker_finished(self, code: int, _status) -> None:
        self._on_worker_output()          # whatever arrived last
        if code != 0 and not self._error:
            self._error = f"worker_exit_{code}"
        self._running = False
        self._progress = 1.0 if not self._error else self._progress
        process = self._process
        self._process = None
        if process is not None:
            process.deleteLater()
        self.runChanged.emit()
        self.finished.emit(self._last_count)
        log.info("Subtitle generation finished: %d line(s), error=%r",
                 self._last_count, self._error)

    # ── lifecycle ─────────────────────────────────────────────────────

    def shutdown(self) -> None:
        self._download_cancel.set()
        process = self._process
        if process is not None:
            self._process = None
            process.kill()
            process.waitForFinished(2000)
        thread = self._download_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
