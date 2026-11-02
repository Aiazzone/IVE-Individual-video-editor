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

from ive.ai import (MODELS, ModelDownloadError, fetch_model,
                    installed_bytes, is_installed, model_entry,
                    remove_model, translate_route)
from ive.ai.subtitles import SubtitleTask

#: Characters per second past which a subtitle line reads too fast.
#: The classic subtitling ceiling is ~17-21; the warning is advisory.
_MAX_CPS = 21.0

log = logging.getLogger(__name__)

__all__ = ["SubtitleService"]


class SubtitleService(QObject):
    """State machine behind the "Automatic subtitles" card."""

    stateChanged = Signal()
    downloadChanged = Signal()
    runChanged = Signal()
    translateChanged = Signal()
    #: Lines landed on the timeline (count). For the UI's closing note.
    finished = Signal(int)

    def __init__(self, settings, project, parent: QObject | None = None
                 ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._project = project
        self._downloading = False
        self._downloading_id = ""
        self._download_progress = 0.0
        self._download_cancel = threading.Event()
        self._download_thread: threading.Thread | None = None
        self._running = False
        self._progress = 0.0
        self._error = ""
        self._last_count = 0
        self._process: QProcess | None = None
        self._stdout = b""
        self._detected_language = ""
        self._translating = False
        self._translate_progress = 0.0
        self._translate_error = ""
        self._last_translated = 0
        self._long_lines = 0
        self._tprocess: QProcess | None = None
        self._tstdout = b""
        #: (clip_id, duration) of the lines sent to the worker, in the
        #: same order its texts come back.
        self._tclips: list[tuple[str, float]] = []

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

    @Property(str, notify=stateChanged)
    def modelId(self) -> str:
        return self._model_id()

    @Property(str, notify=stateChanged)
    def language(self) -> str:
        return str(self._settings.get("ai.subtitles_language") or "")

    @Property("QVariantList", notify=stateChanged)
    def models(self) -> list:
        """Every catalogued model, for the "AI models" settings card:
        id, name, catalogue size, licence, installed, and the real
        footprint on disk."""
        out = []
        for model_id in MODELS:
            entry = model_entry(model_id)
            out.append({
                "id": model_id,
                "name": str(entry["name"]),
                "sizeMb": int(round(entry["total_size"] / 1e6)),
                "license": str(entry["weights_license"]),
                "installed": is_installed(model_id),
                "diskMb": int(round(installed_bytes(model_id) / 1e6)),
            })
        return out

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

    @Property(str, notify=downloadChanged)
    def downloadingId(self) -> str:
        return self._downloading_id if self._downloading else ""

    @Slot(result=bool)
    def download_model(self) -> bool:
        """Fetch the CONFIGURED model's weights - the card's button."""
        return self.download(self._model_id())

    @Slot(str, result=bool)
    def download(self, model_id: str) -> bool:
        """Fetch one model's weights. Explicit, cancellable."""
        return self._download_ids([str(model_id)])

    @Slot("QVariantList", result=bool)
    def download_many(self, model_ids) -> bool:
        """Fetch several models in one cancellable run (online content)."""
        ids = model_ids.toVariant() if hasattr(model_ids, "toVariant")             else model_ids
        return self._download_ids([str(m) for m in ids or []])

    def _download_ids(self, model_ids: list) -> bool:
        """Fetch several models in order, one progress bar over all."""
        model_ids = [m for m in model_ids if model_entry(m) is not None]
        if self._downloading or not model_ids:
            return False
        self._downloading_id = model_ids[0]
        self._downloading = True
        self._download_progress = 0.0
        self._download_cancel.clear()
        self.downloadChanged.emit()
        totals = [int(model_entry(m)["total_size"]) for m in model_ids]
        grand = sum(totals) or 1

        def run() -> None:
            done_before = 0
            try:
                for index, model_id in enumerate(model_ids):
                    self._downloading_id = model_id
                    self.downloadChanged.emit()

                    def tick(done, _total, _base=done_before):
                        self._on_download_progress(_base + done, grand)

                    fetch_model(model_id, progress=tick,
                                cancelled=self._download_cancel.is_set)
                    done_before += totals[index]
                    log.info("Model %s installed", model_id)
            except ModelDownloadError as exc:
                if exc.reason != "cancelled":
                    log.warning("Model download failed: %s", exc)
                    self._error = f"download_{exc.reason}"
            finally:
                self._downloading = False
                self.downloadChanged.emit()
                self.stateChanged.emit()
                self.runChanged.emit()

        self._error = ""
        self._download_thread = threading.Thread(
            target=run, name="ai-model-download", daemon=True)
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

    @Slot(str, result=bool)
    def remove(self, model_id: str) -> bool:
        """Free one model's disk space. Refused while it is in use."""
        if self._downloading or self._running:
            return False
        if not remove_model(str(model_id)):
            return False
        self.stateChanged.emit()
        return True

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

        job = {"model_id": self._model_id(),
               "language": str(self._settings.get("ai.subtitles_language")
                               or ""),
               "clips": clips}
        process = QProcess(self)
        process.setProcessEnvironment(self._worker_env())
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
        elif "language" in message:
            self._detected_language = str(message["language"])
            self.stateChanged.emit()
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

    def _worker_env(self):
        import ive
        from PySide6.QtCore import QProcessEnvironment

        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONPATH", os.pathsep.join(filter(None, [
            str(Path(ive.__file__).parents[1]),
            env.value("PYTHONPATH", "")])))
        return env

    # ── translation ───────────────────────────────────────────────────
    # Same architecture as the generation: the pairs load ctranslate2,
    # which must never enter this process, so the work happens in
    # ive/ai/translate/worker.py and the answer comes back as data.

    def _translate_source(self) -> str:
        pinned = str(self._settings.get("ai.subtitles_language") or "")
        return pinned or self._detected_language

    @Property(str, notify=stateChanged)
    def detectedLanguage(self) -> str:
        return self._detected_language

    @Property(str, notify=stateChanged)
    def translateTarget(self) -> str:
        return str(self._settings.get("ai.translate_target") or "en")

    @Property(str, notify=stateChanged)
    def translateState(self) -> str:
        """"ready" | "model_missing" | "backend_missing" | "no_route"
        | "no_source" - what stands between here and a translation."""
        if getattr(sys, "frozen", False):
            return "backend_missing"
        source = self._translate_source()
        if not source:
            return "no_source"
        from ive.ai.translate import TranslateTask

        return TranslateTask.availability(source, self.translateTarget)

    @Property(int, notify=stateChanged)
    def translateMissingMb(self) -> int:
        """Download size of the pairs still missing for the route."""
        route = translate_route(self._translate_source(),
                                self.translateTarget) or []
        total = 0
        for pair in route:
            if not is_installed(pair):
                entry = model_entry(pair)
                total += int(entry["total_size"]) if entry else 0
        return int(round(total / 1e6))

    @Slot(result=bool)
    def download_translate_models(self) -> bool:
        """Fetch the missing pair(s) of the current route, in order."""
        route = translate_route(self._translate_source(),
                                self.translateTarget) or []
        missing = [pair for pair in route if not is_installed(pair)]
        return self._download_ids(missing) if missing else False

    @Property(bool, notify=translateChanged)
    def translating(self) -> bool:
        return self._translating

    @Property(float, notify=translateChanged)
    def translateProgress(self) -> float:
        return self._translate_progress

    @Property(str, notify=translateChanged)
    def translateError(self) -> str:
        return self._translate_error

    @Property(int, notify=translateChanged)
    def lastTranslated(self) -> int:
        return self._last_translated

    @Property(int, notify=translateChanged)
    def longLines(self) -> int:
        """Lines whose translation may read too fast for their time."""
        return self._long_lines

    @Slot(result=bool)
    def translate(self) -> bool:
        """Translate every Text-lane clip; timings stay, one undo."""
        if self._translating or self.translateState != "ready":
            return False
        clips = [c for c in self._project.timelineClips
                 if c.get("track") == 3 and c.get("text")]
        if not clips:
            self._translate_error = "no_lines"
            self.translateChanged.emit()
            return False
        self._tclips = [(c["id"], float(c["duration"])) for c in clips]
        job = {"source": self._translate_source(),
               "target": self.translateTarget,
               "texts": [c["text"] for c in clips]}
        process = QProcess(self)
        process.setProcessEnvironment(self._worker_env())
        process.readyReadStandardOutput.connect(self._on_translate_output)
        process.readyReadStandardError.connect(self._on_translate_log)
        process.finished.connect(self._on_translate_finished)
        self._tprocess = process
        self._tstdout = b""
        self._translate_error = ""
        self._last_translated = 0
        self._long_lines = 0
        self._translating = True
        self._translate_progress = 0.0
        self.translateChanged.emit()
        log.info("Subtitle translation started: %d lines, %s -> %s",
                 len(clips), job["source"], job["target"])
        process.start(sys.executable, ["-m", "ive.ai.translate.worker"])
        process.write(json.dumps(job).encode("utf-8"))
        process.closeWriteChannel()
        return True

    @Slot()
    def cancel_translate(self) -> None:
        process = self._tprocess
        if process is not None and self._translating:
            log.info("Subtitle translation cancelled")
            self._translate_error = "cancelled"
            process.kill()

    def _on_translate_output(self) -> None:
        process = self._tprocess
        if process is None:
            return
        self._tstdout += bytes(process.readAllStandardOutput().data())
        while b"\n" in self._tstdout:
            line, self._tstdout = self._tstdout.split(b"\n", 1)
            self._handle_translate_line(line.strip())

    def _handle_translate_line(self, line: bytes) -> None:
        if not line:
            return
        try:
            message = json.loads(line.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            log.warning("Unreadable translate line: %r", line[:120])
            return
        if "progress" in message:
            self._translate_progress = float(message["progress"])
            self.translateChanged.emit()
        elif "error" in message:
            self._translate_error = str(message["error"])
        elif "texts" in message:
            if self._translate_error == "cancelled":
                return
            texts = [str(t) for t in message["texts"]]
            changes = [{"clip_id": cid, "text": text}
                       for (cid, _dur), text in zip(self._tclips, texts)]
            self._last_translated = self._project.apply_translations(changes)
            self._long_lines = sum(
                1 for (_cid, duration), text in zip(self._tclips, texts)
                if duration > 0 and len(text) / duration > _MAX_CPS)

    def _on_translate_log(self) -> None:
        process = self._tprocess
        if process is None:
            return
        text = bytes(process.readAllStandardError().data()) \
            .decode("utf-8", "replace").strip()
        for line in text.splitlines():
            if line.strip():
                log.info("[translate] %s", line.strip())

    def _on_translate_finished(self, code: int, _status) -> None:
        self._on_translate_output()
        if code != 0 and not self._translate_error:
            self._translate_error = f"worker_exit_{code}"
        self._translating = False
        process = self._tprocess
        self._tprocess = None
        if process is not None:
            process.deleteLater()
        self.translateChanged.emit()
        log.info("Subtitle translation finished: %d clip(s), error=%r",
                 self._last_translated, self._translate_error)

    # ── lifecycle ─────────────────────────────────────────────────────

    def shutdown(self) -> None:
        self._download_cancel.set()
        for attr in ("_process", "_tprocess"):
            process = getattr(self, attr)
            if process is not None:
                setattr(self, attr, None)
                process.kill()
                process.waitForFinished(2000)
        thread = self._download_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
