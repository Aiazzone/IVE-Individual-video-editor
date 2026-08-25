"""Fetching model weights: streamed, hash-verified, resumable, removable.

Same gate as the official packs (ive/packs/official.py): stream to a
``.part`` name, verify the SHA-256, and only then move the file into
place. A mismatch deletes the file and reports; a cancelled or failed
download leaves no ``.part`` behind. A file already present at its full
recorded size is skipped, which is what makes a retry after a dropped
connection resume instead of starting over - per file, not per byte.

``file://`` URLs work, which is how the tests exercise the whole path
without a network. Nothing downloaded is ever executed: the weights are
data for CTranslate2, and the hash pins exactly which data.
"""

from __future__ import annotations

import hashlib
import logging
import urllib.error
import urllib.request
from typing import Any, Callable

from ive.ai.model_registry import is_installed, model_dir, model_entry

log = logging.getLogger(__name__)

__all__ = ["fetch_model", "ModelDownloadError"]

_CHUNK = 256 * 1024


class ModelDownloadError(RuntimeError):
    """A fetch that did not end with an installed model; ``.reason`` is a
    short machine code: unknown_model, not_found, network, hash_mismatch,
    cancelled."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason


def fetch_model(model_id: str, *,
                progress: Callable[[int, int], None] | None = None,
                cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Download and verify every file of one model.

    ``progress(done_bytes, total_bytes)`` counts across ALL files, so a
    single bar can ride it. ``cancelled()`` is polled per chunk. Returns
    the registry entry on success. Raises :class:`ModelDownloadError`.
    """
    entry = model_entry(model_id)
    if entry is None:
        raise ModelDownloadError("unknown_model", f"No model {model_id!r}")

    folder = model_dir(model_id)
    folder.mkdir(parents=True, exist_ok=True)
    total = int(entry["total_size"])
    done = 0

    for spec in entry["files"]:
        target = folder / spec["name"]
        size = int(spec["size"])
        try:
            if target.stat().st_size == size:
                done += size          # verified when it was downloaded
                if progress is not None:
                    progress(done, total)
                continue
        except OSError:
            pass

        partial = target.with_suffix(target.suffix + ".part")
        request = urllib.request.Request(spec["url"],
                                         headers={"User-Agent": "IVE/1.0"})
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(request, timeout=60) as response, \
                    open(partial, "wb") as sink:
                while True:
                    if cancelled is not None and cancelled():
                        raise ModelDownloadError("cancelled")
                    chunk = response.read(_CHUNK)
                    if not chunk:
                        break
                    sink.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if progress is not None:
                        progress(done, total)
        except ModelDownloadError:
            partial.unlink(missing_ok=True)
            raise
        except urllib.error.HTTPError as exc:
            partial.unlink(missing_ok=True)
            raise ModelDownloadError(
                "not_found" if exc.code == 404 else "network",
                f"HTTP {exc.code} for {spec['name']}") from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            partial.unlink(missing_ok=True)
            raise ModelDownloadError("network",
                                     f"{spec['name']}: {exc}") from exc

        if digest.hexdigest() != spec["sha256"]:
            partial.unlink(missing_ok=True)
            log.error("Model %s: hash mismatch on %s, file discarded",
                      model_id, spec["name"])
            raise ModelDownloadError("hash_mismatch", spec["name"])
        partial.replace(target)
        log.info("Model %s: %s downloaded (%d bytes), hash verified",
                 model_id, spec["name"], size)

    if not is_installed(model_id):     # belt and braces
        raise ModelDownloadError("network", "files missing after download")
    log.info("Model %s installed in %s", model_id, folder)
    return entry
