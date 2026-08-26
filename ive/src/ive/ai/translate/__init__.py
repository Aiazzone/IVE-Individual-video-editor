"""Subtitle translation: local, per language pair, undoable.

Argos Open Tech's OPUS-MT packages loaded DIRECTLY with ctranslate2 +
sentencepiece: the argostranslate library (and the stanza/spacy tail it
drags in) never enters the process. Subtitle lines are short, so no
sentence splitter is needed - each line is one translation unit, which
also keeps the line-to-line timing mapping trivial.

Missing direct pairs pivot through English (how OPUS pairs are
published). Inference lives in a separate worker process, same contract
and same reasons as the subtitles (ive/ai/subtitles/worker.py).
"""

from ive.ai.translate.task import TranslateError, TranslateTask

__all__ = ["TranslateTask", "TranslateError"]
