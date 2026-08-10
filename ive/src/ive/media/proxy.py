"""Proxies: a small stand-in copy so 4K can be edited at all.

Measured on this machine (``tests/test_performance.py``), a 3840x2160 clip
costs **35 ms** to decode one frame sequentially and **1237 ms** to seek. The
budget at 30 fps is 33 ms. No amount of tuning closes that gap: 8.3 million
pixels per frame decoded in Python is simply not a real-time operation.

So the editor works on a smaller copy and renders from the original. This is
what every editor does, and it is the difference between 4K being usable and
4K being a slideshow.

**The rule that is never broken: the export reads the originals.** A render
made from proxies is wasted work, and the user would only find out afterwards.
The flag lives in the graph builder, defaults to proxies for the preview, and
is forced off for export.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QMutex,
    QMutexLocker,
    QObject,
    Qt,
    QThread,
    Signal,
    Slot,
)

from ive.media.probe import MediaInfo, probe
from ive.utils.paths import get_data_path

log = logging.getLogger(__name__)

__all__ = ["ProxyManager", "ProxyPolicy", "proxy_key"]


@dataclass(frozen=True)
class ProxyPolicy:
    """When to build a proxy, and how small."""

    enabled: bool = True
    #: Above this height the original is too heavy to scrub. 1080p decodes in
    #: about 6 ms here, 2160p in 35 - the line sits between them.
    threshold_height: int = 1440
    #: Target height. 540p keeps a decode near 2 ms and still shows framing,
    #: focus and motion well enough to cut on.
    height: int = 540
    #: CRF: the proxy is a working copy, not a deliverable.
    quality: int = 30

    def needs_proxy(self, info: MediaInfo) -> bool:
        video = info.primary_video
        if not self.enabled or video is None:
            return False
        _, height = video.display_size
        return height > self.threshold_height


def proxy_key(path: Path) -> str:
    """Identity of a source file: path, size and mtime.

    Including size and mtime means re-exporting a clip under the same name
    invalidates its proxy, instead of silently editing against the old picture.
    """
    try:
        stat = path.stat()
        raw = f"{path.resolve()}|{stat.st_size}|{int(stat.st_mtime)}"
    except OSError:
        raw = str(path)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


class _Worker(QObject):
    """Builds proxies on its own thread, one after another."""

    progress = Signal(str, int, int)     # source path, done, total
    finished = Signal(str, str)          # source path, proxy path
    failed = Signal(str, str)            # source path, reason

    def __init__(self) -> None:
        super().__init__()
        self._cancel = False
        self._mutex = QMutex()

    @Slot()
    def cancel(self) -> None:
        with QMutexLocker(self._mutex):
            self._cancel = True

    def _cancelled(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._cancel

    @Slot(str, str, int, int)
    def build(self, source: str, destination: str, height: int, quality: int) -> None:
        import av

        from ive.export.service import encoder_for

        with QMutexLocker(self._mutex):
            self._cancel = False

        src = Path(source)
        out = Path(destination)
        tmp = out.with_suffix(out.suffix + ".part")
        container_in = container_out = None
        try:
            info = probe(src)
            video = info.primary_video
            if video is None:
                self.failed.emit(source, "no video stream")
                return

            width, src_height = video.display_size
            scale = height / max(1, src_height)
            target_w = max(2, int(round(width * scale)) & ~1)
            target_h = max(2, height & ~1)
            fps = float(video.fps) or 25.0

            encoder = encoder_for("h264", target_w, target_h, "yuv420p", fps)
            if encoder is None:
                self.failed.emit(source, "no usable H.264 encoder")
                return

            out.parent.mkdir(parents=True, exist_ok=True)
            container_in = av.open(str(src))
            stream_in = container_in.streams.video[0]
            stream_in.thread_type = "AUTO"

            container_out = av.open(str(tmp), "w", format="mp4")
            stream_out = container_out.add_stream(encoder, rate=round(fps))
            stream_out.width = target_w
            stream_out.height = target_h
            stream_out.pix_fmt = "yuv420p"
            if encoder.startswith("libx264"):
                stream_out.options = {"crf": str(quality), "preset": "veryfast"}

            total = stream_in.frames or int(round(info.duration * fps)) or 1
            log.info("Proxy: %s -> %dx%d via %s (%d frames)",
                     src.name, target_w, target_h, encoder, total)

            done = 0
            # No audio in the proxy: the original's audio is cheap to decode
            # and always exact, so copying it here would only add size.
            for frame in container_in.decode(stream_in):
                if self._cancelled():
                    log.info("Proxy cancelled: %s", src.name)
                    self._cleanup(container_out, tmp)
                    self.failed.emit(source, "cancelled")
                    return
                reformatted = frame.reformat(width=target_w, height=target_h,
                                             format="yuv420p")
                for packet in stream_out.encode(reformatted):
                    container_out.mux(packet)
                done += 1
                if done % 25 == 0:
                    self.progress.emit(source, done, total)

            for packet in stream_out.encode():
                container_out.mux(packet)
            container_out.close()
            container_out = None
            tmp.replace(out)        # only now does it count as a proxy

            self.progress.emit(source, total, total)
            log.info("Proxy ready: %s (%.1f KB)", out.name, out.stat().st_size / 1024)
            self.finished.emit(source, str(out))
        except Exception as exc:
            log.exception("Proxy failed for %s", src.name)
            self._cleanup(container_out, tmp)
            self.failed.emit(source, str(exc))
        finally:
            if container_in is not None:
                try:
                    container_in.close()
                except Exception:
                    pass

    @staticmethod
    def _cleanup(container, tmp: Path) -> None:
        if container is not None:
            try:
                container.close()
            except Exception:
                pass
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            log.warning("Could not remove the partial proxy %s", tmp)


class ProxyManager(QObject):
    """Knows which proxies exist, and builds the missing ones."""

    changed = Signal()                   # a proxy appeared or went away
    progressChanged = Signal()
    error = Signal(str)

    _buildRequested = Signal(str, str, int, int)
    _cancelRequested = Signal()

    def __init__(self, settings=None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._folder = Path(get_data_path("cache/proxies"))
        self._folder.mkdir(parents=True, exist_ok=True)
        self._queue: list[str] = []
        self._current = ""
        self._done = 0
        self._total = 0

        self._thread = QThread()
        self._thread.setObjectName("proxy")
        self._worker = _Worker()
        self._worker.moveToThread(self._thread)
        self._buildRequested.connect(self._worker.build)
        # Direct on purpose, and by name: the worker thread is busy inside
        # build(), so a queued cancel would only be delivered when the build
        # is already over. (`type=0` was AutoConnection, which across threads
        # IS queued - cancelling a proxy did nothing.)
        self._cancelRequested.connect(self._worker.cancel,
                                      type=Qt.ConnectionType.DirectConnection)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    # ── policy ────────────────────────────────────────────────────────

    @property
    def policy(self) -> ProxyPolicy:
        if self._settings is None:
            return ProxyPolicy()
        return ProxyPolicy(
            enabled=bool(self._settings.get("media.proxy_enabled")),
            threshold_height=int(self._settings.get("media.proxy_threshold")),
            height=int(self._settings.get("media.proxy_height")),
        )

    # ── lookup ────────────────────────────────────────────────────────

    def path_for(self, source: str | Path) -> Path:
        """Where the proxy for this file would live."""
        source = Path(source)
        return self._folder / f"{proxy_key(source)}.mp4"

    @Slot(str, result=bool)
    def has_proxy(self, source: str) -> bool:
        return self.path_for(source).is_file()

    @Slot(str, result=str)
    def resolve(self, source: str) -> str:
        """The file the PREVIEW should read: the proxy when there is one.

        Export must never call this. It uses the source path directly, which
        is why the choice lives in the graph builder rather than being hidden
        inside the producer.
        """
        if not self.policy.enabled:
            return str(source)
        proxy = self.path_for(source)
        return str(proxy) if proxy.is_file() else str(source)

    # ── building ──────────────────────────────────────────────────────

    @Slot(str, result=bool)
    def request(self, source: str) -> bool:
        """Queue a proxy for this file if the policy calls for one."""
        source = str(source)
        if not Path(source).is_file():
            return False
        if self.has_proxy(source) or source in self._queue or source == self._current:
            return False
        try:
            info = probe(source)
        except Exception as exc:
            log.warning("Cannot probe %s for a proxy: %s", Path(source).name, exc)
            return False
        if not self.policy.needs_proxy(info):
            return False

        self._queue.append(source)
        log.info("Proxy queued: %s (%d waiting)", Path(source).name, len(self._queue))
        self._start_next()
        return True

    @Slot("QVariantList", result=int)
    def request_many(self, sources: list) -> int:
        return sum(1 for s in sources or [] if self.request(str(s)))

    @Slot()
    def cancel(self) -> None:
        self._queue.clear()
        if self._current:
            self._cancelRequested.emit()

    def _start_next(self) -> None:
        if self._current or not self._queue:
            return
        source = self._queue.pop(0)
        self._current = source
        self._done = 0
        self._total = 0
        policy = self.policy
        self.progressChanged.emit()
        self._buildRequested.emit(source, str(self.path_for(source)),
                                  policy.height, policy.quality)

    # ── state for QML ─────────────────────────────────────────────────

    @Property(bool, notify=progressChanged)
    def busy(self) -> bool:
        return bool(self._current)

    @Property(int, notify=progressChanged)
    def pending(self) -> int:
        return len(self._queue) + (1 if self._current else 0)

    @Property(float, notify=progressChanged)
    def progress(self) -> float:
        return (self._done / self._total) if self._total else 0.0

    @Property(str, notify=progressChanged)
    def currentName(self) -> str:
        return Path(self._current).name if self._current else ""

    # ── reactions ─────────────────────────────────────────────────────

    def _on_progress(self, _source: str, done: int, total: int) -> None:
        self._done, self._total = done, total
        self.progressChanged.emit()

    def _on_finished(self, source: str, _proxy: str) -> None:
        self._current = ""
        self.progressChanged.emit()
        self.changed.emit()          # the graph should be rebuilt to pick it up
        self._start_next()

    def _on_failed(self, source: str, reason: str) -> None:
        log.warning("Proxy failed for %s: %s", Path(source).name, reason)
        self._current = ""
        self.progressChanged.emit()
        if reason != "cancelled":
            self.error.emit(reason)
        self._start_next()

    # ── housekeeping ──────────────────────────────────────────────────

    @Slot(result=int)
    def clear_cache(self) -> int:
        """Delete every proxy. They are all rebuildable, so this is safe."""
        removed = 0
        for path in self._folder.glob("*.mp4"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                log.warning("Could not delete %s", path.name)
        log.info("Removed %d proxies", removed)
        self.changed.emit()
        return removed

    @Property(float, notify=changed)
    def cacheSizeMb(self) -> float:
        try:
            return sum(p.stat().st_size for p in self._folder.glob("*.mp4")) / 1048576
        except OSError:
            return 0.0

    def shutdown(self) -> None:
        self.cancel()
        self._thread.quit()
        if not self._thread.wait(4000):
            log.warning("Proxy thread did not stop in time")
            self._thread.terminate()
            self._thread.wait(1000)
