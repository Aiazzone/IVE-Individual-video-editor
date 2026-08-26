"""Text through an OPUS-MT pair: extract once, load lazily, translate.

The ``.argosmodel`` a pair downloads as is a zip holding a CTranslate2
model and a SentencePiece tokenizer (plus a stanza tokenizer this app
deliberately never loads). It is extracted NEXT TO itself on first use
- idempotent, verified by the presence of the sentencepiece file - and
the pair stays loaded for the next batch until ``unload()``.

Qt-free on purpose; runs on whatever worker process calls it. Like the
subtitles task, this must NOT be imported into the app process with the
model actually loaded: ctranslate2's OpenMP runtime aborts there
(ive/ai/subtitles/worker.py tells the whole story).
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Callable

from ive.ai.model_registry import is_installed, model_dir, translate_route

log = logging.getLogger(__name__)

__all__ = ["TranslateTask", "TranslateError"]

#: Lines per translate_batch call: small enough for steady progress,
#: large enough that the model amortises.
_BATCH = 16


class TranslateError(RuntimeError):
    """Translation failed in a way the caller must surface."""


def _unpacked_root(pair_id: str) -> Path:
    """The extracted package folder, extracting on first use."""
    folder = model_dir(pair_id)
    marker = "sentencepiece.model"
    for candidate in folder.glob(f"**/{marker}"):
        return candidate.parent
    archive = folder / "pack.argosmodel"
    if not archive.is_file():
        raise TranslateError(f"{pair_id}: package file missing")
    log.info("Extracting %s", archive)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(folder / "unpacked")
    for candidate in folder.glob(f"**/{marker}"):
        return candidate.parent
    raise TranslateError(f"{pair_id}: no tokenizer inside the package")


class TranslateTask:
    """Translation over one or two catalogued pairs (pivot via English)."""

    def __init__(self) -> None:
        self._loaded: dict[str, tuple] = {}

    # -- availability ---------------------------------------------------

    @staticmethod
    def route(source: str, target: str) -> list[str] | None:
        return translate_route(source, target)

    @staticmethod
    def availability(source: str, target: str) -> str:
        """"ready" | "model_missing" | "backend_missing" | "no_route"."""
        from importlib.util import find_spec

        try:
            if (find_spec("ctranslate2") is None
                    or find_spec("sentencepiece") is None):
                return "backend_missing"
        except (ImportError, ValueError):
            return "backend_missing"
        route = translate_route(source, target)
        if route is None:
            return "no_route"
        if any(not is_installed(pair) for pair in route):
            return "model_missing"
        return "ready"

    def unload(self) -> None:
        self._loaded.clear()

    def _ensure(self, pair_id: str):
        loaded = self._loaded.get(pair_id)
        if loaded is None:
            import ctranslate2
            import sentencepiece

            root = _unpacked_root(pair_id)
            tokenizer = sentencepiece.SentencePieceProcessor()
            tokenizer.load(str(root / "sentencepiece.model"))
            translator = ctranslate2.Translator(str(root / "model"),
                                                device="cpu",
                                                compute_type="int8")
            loaded = (tokenizer, translator)
            self._loaded[pair_id] = loaded
            log.info("Translation pair %s loaded from %s", pair_id, root)
        return loaded

    # -- translation ----------------------------------------------------

    def _hop(self, pair_id: str, texts: list[str],
             progress: Callable[[float], None] | None,
             cancelled: Callable[[], bool] | None,
             base: float, span: float) -> list[str]:
        tokenizer, translator = self._ensure(pair_id)
        out: list[str] = []
        for start in range(0, len(texts), _BATCH):
            if cancelled is not None and cancelled():
                raise TranslateError("cancelled")
            batch = texts[start:start + _BATCH]
            tokens = [tokenizer.encode(t, out_type=str) for t in batch]
            try:
                results = translator.translate_batch(tokens)
            except Exception as exc:
                raise TranslateError(str(exc)) from exc
            out.extend(tokenizer.decode(r.hypotheses[0]) for r in results)
            if progress is not None:
                progress(base + span * min(1.0, len(out) / len(texts)))
        return out

    def translate(self, texts: list[str], source: str, target: str, *,
                  progress: Callable[[float], None] | None = None,
                  cancelled: Callable[[], bool] | None = None
                  ) -> list[str]:
        """Each input line becomes one output line, order preserved.

        Multi-line texts (a two-row subtitle) are translated row by row
        so the line break survives. A pivot route pays two hops; the
        progress fraction covers both.
        """
        route = translate_route(source, target)
        if route is None:
            raise TranslateError(f"no route {source}->{target}")
        if not route or not texts:
            return list(texts)

        # Flatten rows, remembering the shape, so "\n" survives.
        rows: list[str] = []
        shape: list[int] = []
        for text in texts:
            parts = [p for p in str(text).split("\n")]
            shape.append(len(parts))
            rows.extend(parts)

        span = 1.0 / len(route)
        for index, pair_id in enumerate(route):
            rows = self._hop(pair_id, rows, progress, cancelled,
                             index * span, span)

        out: list[str] = []
        cursor = 0
        for count in shape:
            out.append("\n".join(r.strip() for r in
                                 rows[cursor:cursor + count]).strip())
            cursor += count
        return out
