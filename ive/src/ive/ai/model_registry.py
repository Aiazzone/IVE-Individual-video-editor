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
    "u2netp": {
        "task": "segmentation",
        "name": "U²-Net Small",
        "description_key": "ai.model.u2netp",
        "code_license": "Apache-2.0 (U-2-Net)",
        "weights_license": "Apache-2.0 (U-2-Net); ONNX by rembg (MIT)",
        "commercial_use_allowed": True,
        "files": [{
            "name": "u2netp.onnx",
            "url": "https://github.com/danielgatis/rembg/releases/"
                   "download/v0.0.0/u2netp.onnx",
            "size": 4574861,
            "sha256": "309c8469258dda742793dce0ebea8e6dd393174f"
                      "89934733ecc8b14c76f4ddd8",
        }],
    },
    "vittrack": {
        "task": "tracking",
        "name": "VitTrack",
        "description_key": "ai.model.vittrack",
        "code_license": "Apache-2.0 (OpenCV TrackerVit)",
        "weights_license": "Apache-2.0 (opencv_zoo)",
        "commercial_use_allowed": True,
        "files": [{
            "name": "object_tracking_vittrack_2023sep.onnx",
            # Pinned to the commit that last touched the file, so the
            # checksum below stays true whatever happens on main.
            "url": "https://github.com/opencv/opencv_zoo/raw/"
                   "fef72f8fa7c52eaf116d3df358d24e6e959ada0e/models/"
                   "object_tracking_vittrack/"
                   "object_tracking_vittrack_2023sep.onnx",
            "size": 714726,
            "sha256": "2990f0b7cd44d92afa48cd97db6de7be113fc1d9"
                      "594fddb74e2725c10478e91d",
        }],
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


def _argos_pair(source: str, target: str, version: str, size: int,
                sha256: str, name: str) -> dict[str, Any]:
    slug = f"{source}_{target}"
    return {
        "task": "translate",
        "name": name,
        "description_key": "",
        "code_license": "MIT (CTranslate2, SentencePiece)",
        "weights_license": "MIT/CC0 (Argos Open Tech; dati OPUS)",
        "commercial_use_allowed": True,
        "from": source,
        "to": target,
        "files": [{
            "name": "pack.argosmodel",
            "url": f"https://argos-net.com/v1/translate-{slug}-"
                   f"{version}.argosmodel",
            "size": size,
            "sha256": sha256,
        }],
    }


MODELS.update({
    # Subtitle translation pairs (docs/AI_FEATURES.md §5). Loaded with
    # ctranslate2 + sentencepiece directly - the argostranslate library
    # (and its stanza/spacy tail) never enters the app; subtitle lines
    # are short enough to need no sentence splitter.
    "translate-it-en": _argos_pair(
        "it", "en", "1_0", 87190224,
        "d2dd23b8b702f612b8127f07c7a0391f5f2a8b93344e6ddc9dd93c81824e85cb",
        "Italiano → English"),
    "translate-en-it": _argos_pair(
        "en", "it", "1_0", 87660780,
        "dde2180001a47904ecbbd688a41e35db8a040e4fd5b52e4f29b4bb499516ab32",
        "English → Italiano"),
    "translate-pt-en": _argos_pair(
        "pt", "en", "1_9", 69447231,
        "ae76df6f650895c16f2b582065014fab496755ca846ecb19fae81d51f332a38e",
        "Português → English"),
    "translate-en-pt": _argos_pair(
        "en", "pt", "1_9", 66179184,
        "0c5350a2fa5b923de1346edc0d42e08e38bab2e33cede3a0b9a48eb4281ad8a9",
        "English → Português"),
    "translate-es-en": _argos_pair(
        "es", "en", "1_9", 285208831,
        "c54df2b62fceaf54a3ce5d97db6bf56efd7940063329f6778f4212d2acb370d4",
        "Español → English"),
    "translate-en-es": _argos_pair(
        "en", "es", "1_0", 87503191,
        "d698d0ef87ad70d5d184b7fa6965905bf4368f09a2bb9ffb165a79bac96af0c4",
        "English → Español"),
})


def translate_route(source: str, target: str) -> list[str] | None:
    """Model ids that turn ``source`` text into ``target`` text.

    A direct pair when one exists, otherwise a pivot THROUGH ENGLISH
    (how the OPUS pairs are published). ``None`` means the catalogue
    cannot get there at all; ``[]`` means nothing to do (same language).
    """
    source, target = str(source).lower(), str(target).lower()
    if not source or source == target:
        return []
    direct = next((mid for mid, e in MODELS.items()
                   if e.get("task") == "translate"
                   and e.get("from") == source and e.get("to") == target),
                  None)
    if direct is not None:
        return [direct]
    first = next((mid for mid, e in MODELS.items()
                  if e.get("task") == "translate"
                  and e.get("from") == source and e.get("to") == "en"),
                 None)
    second = next((mid for mid, e in MODELS.items()
                   if e.get("task") == "translate"
                   and e.get("from") == "en" and e.get("to") == target),
                  None)
    if first is not None and second is not None:
        return [first, second]
    return None


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
