"""The official pack catalogue, and fetching a pack from it.

The catalogue is DATA in the repository (``config/defaults/packs/
catalog.json``): for every official pack its name, what it holds, the
download URL (a GitHub Release asset), its size and its **SHA-256**. The
heavy files never live in the repository; a build of IVE knows where
they are and what they must hash to.

Fetching = stream the file to a temporary name, verify the hash, and
only then hand it to ``install_pack`` - the same gate a dropped file goes
through. Nothing downloaded is ever executed, a hash mismatch deletes
the file and reports, and a cancelled or failed download leaves no
residue. ``file://`` URLs work too, which is how the tests exercise the
whole path without a network.
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ive.utils.paths import get_data_path, get_defaults_path

log = logging.getLogger(__name__)

__all__ = ["load_catalog", "catalog_entry", "fetch_pack", "DownloadError"]

_CHUNK = 256 * 1024


class DownloadError(RuntimeError):
    """A fetch that did not end with an installed pack; ``.reason`` is a
    short machine code: not_found, network, hash_mismatch, cancelled,
    install_failed."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason


def _localized(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    return {"en": str(value)} if value else {}


def load_catalog(path: Path | None = None) -> list[dict[str, Any]]:
    """The catalogue entries, coerced; an unreadable file is an empty
    catalogue with a warning, never a crash at startup."""
    path = path or get_defaults_path("packs") / "catalog.json"
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Official pack catalogue unreadable (%s): %s", path, exc)
        return []
    entries = raw.get("packs") if isinstance(raw, dict) else raw
    out = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        pack_id = str(entry.get("id") or "").strip()
        url = str(entry.get("url") or "").strip()
        digest = str(entry.get("sha256") or "").strip().lower()
        if not pack_id or not url or len(digest) != 64:
            log.warning("Catalogue entry without id/url/sha256 skipped: %r",
                        entry.get("id"))
            continue
        try:
            size = int(entry.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        out.append({
            "id": pack_id,
            "names": _localized(entry.get("name")) or {"en": pack_id},
            "descriptions": _localized(entry.get("description")),
            "kind": str(entry.get("kind") or "pack"),
            "version": str(entry.get("version") or ""),
            "size": size,
            "sha256": digest,
            "url": url,
            "license": str(entry.get("license") or ""),
            "author": str(entry.get("author") or ""),
        })
    return out


def catalog_entry(pack_id: str) -> dict[str, Any] | None:
    return next((e for e in load_catalog() if e["id"] == pack_id), None)


def fetch_pack(entry: dict[str, Any], *,
               progress: Callable[[int, int], None] | None = None,
               cancelled: Callable[[], bool] | None = None,
               downloads_dir: Path | None = None) -> dict[str, Any]:
    """Download, verify and install one catalogue entry.

    ``progress(done_bytes, total_bytes)`` is called per chunk (total may
    be 0 when the server does not say); ``cancelled()`` is polled per
    chunk. Returns ``install_pack``'s report. Raises DownloadError.
    """
    from ive.packs.pack import install_pack

    folder = downloads_dir or get_data_path("cache/downloads")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{entry['id']}.ivepack"
    partial = target.with_suffix(".part")
    request = urllib.request.Request(entry["url"],
                                     headers={"User-Agent": "IVE/1.0"})
    digest = hashlib.sha256()
    done = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response, \
                open(partial, "wb") as sink:
            total = int(response.headers.get("Content-Length") or
                        entry.get("size") or 0)
            while True:
                if cancelled is not None and cancelled():
                    raise DownloadError("cancelled")
                chunk = response.read(_CHUNK)
                if not chunk:
                    break
                sink.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
    except DownloadError:
        partial.unlink(missing_ok=True)
        raise
    except urllib.error.HTTPError as exc:
        partial.unlink(missing_ok=True)
        raise DownloadError("not_found" if exc.code == 404 else "network",
                            f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        partial.unlink(missing_ok=True)
        raise DownloadError("network", str(exc)) from exc

    if digest.hexdigest() != entry["sha256"]:
        partial.unlink(missing_ok=True)
        log.error("Pack %s: hash mismatch, file discarded", entry["id"])
        raise DownloadError("hash_mismatch")
    partial.replace(target)
    log.info("Pack %s downloaded (%d bytes), hash verified", entry["id"], done)

    report = install_pack(target)
    target.unlink(missing_ok=True)     # the install copied it out
    if not report.get("ok"):
        raise DownloadError("install_failed",
                            str(report.get("error") or "install_failed"))
    return report
