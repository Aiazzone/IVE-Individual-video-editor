"""The catalogue of AI models: what exists, where it lives, what it hashes to.

This file is the source of truth (docs/AI_FEATURES.md §10): for every
model its files with URL, size and SHA-256, plus the licences - of the
CODE and of the WEIGHTS separately, because they differ more often than
not. URLs are pinned to an immutable revision, so a repository moving
on cannot silently change what the checksums were computed against.

Weights are installed under ``models/<task>/<model_id>/``. "Installed"
means every file is present at its recorded size; the cryptographic
check happens once, at download time (ive/ai/downloader.py) - files are
not re-hashed at every startup.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from ive.utils.paths import get_model_path

log = logging.getLogger(__name__)

__all__ = ["MODELS", "model_entry", "model_dir", "is_installed",
           "installed_bytes", "remove_model"]


def _whisper_files(repo: str, revision: str, model_sha: str,
                   model_size: int, config_sha: str, config_size: int
                   ) -> list[dict[str, Any]]:
    base = f"https://huggingface.co/{repo}/resolve/{revision}"
    return [
        {"name": "config.json", "url": f"{base}/config.json",
         "size": config_size, "sha256": config_sha},
        {"name": "model.bin", "url": f"{base}/model.bin",
         "size": model_size, "sha256": model_sha},
        {"name": "tokenizer.json", "url": f"{base}/tokenizer.json",
         "size": 2203239,
         "sha256": "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"},
        {"name": "vocabulary.txt", "url": f"{base}/vocabulary.txt",
         "size": 459861,
         "sha256": "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913"},
    ]


#: Every known model. Keyed by our id, not the upstream name.
MODELS: dict[str, dict[str, Any]] = {
    "whisper-tiny": {
        "task": "subtitles",
        "name": "Whisper Tiny",
        "description_key": "ai.model.whisper_tiny",
        "code_license": "MIT (faster-whisper, CTranslate2)",
        "weights_license": "MIT (OpenAI Whisper)",
        "commercial_use_allowed": True,
        "files": _whisper_files(
            "Systran/faster-whisper-tiny",
            "d90ca5fe260221311c53c58e660288d3deb8d356",
            "dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1",
            75538270,
            "a73a28cdfe1c43ccc7202fa333d1f89c202477271407ae9a7f19afa52039cac8",
            2249),
    },
    "whisper-small": {
        "task": "subtitles",
        "name": "Whisper Small",
        "description_key": "ai.model.whisper_small",
        "code_license": "MIT (faster-whisper, CTranslate2)",
        "weights_license": "MIT (OpenAI Whisper)",
        "commercial_use_allowed": True,
        "files": _whisper_files(
            "Systran/faster-whisper-small",
            "536b0662742c02347bc0e980a01041f333bce120",
            "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671",
            483546902,
            "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828",
            2370),
    },
}


def model_entry(model_id: str) -> dict[str, Any] | None:
    """The catalogue entry, with ``id`` and ``total_size`` filled in."""
    entry = MODELS.get(str(model_id))
    if entry is None:
        return None
    out = dict(entry)
    out["id"] = str(model_id)
    out["total_size"] = sum(int(f["size"]) for f in entry["files"])
    return out


def model_dir(model_id: str) -> Path:
    """Where this model's files live (whether or not they exist yet)."""
    entry = MODELS.get(str(model_id)) or {}
    task = str(entry.get("task") or "misc")
    return get_model_path(task) / str(model_id)


def is_installed(model_id: str) -> bool:
    """Every recorded file present at its recorded size."""
    entry = MODELS.get(str(model_id))
    if entry is None:
        return False
    folder = model_dir(model_id)
    for spec in entry["files"]:
        path = folder / spec["name"]
        try:
            if path.stat().st_size != int(spec["size"]):
                return False
        except OSError:
            return False
    return True


def installed_bytes(model_id: str) -> int:
    """Disk footprint of what is actually there (0 when nothing is)."""
    folder = model_dir(model_id)
    total = 0
    try:
        for path in folder.iterdir():
            if path.is_file():
                total += path.stat().st_size
    except OSError:
        pass
    return total


def remove_model(model_id: str) -> bool:
    """Delete a model's folder. Missing is fine; a locked file is not."""
    folder = model_dir(model_id)
    if not folder.exists():
        return True
    try:
        shutil.rmtree(folder)
        log.info("Model %s removed (%s)", model_id, folder)
        return True
    except OSError:
        log.exception("Could not remove model %s", model_id)
        return False
