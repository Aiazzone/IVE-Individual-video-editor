"""Automatic subtitles: speech in the footage becomes editable text clips.

Pipeline (docs/AI_FEATURES.md §4): audio extraction -> speech-to-text
with word timestamps (faster-whisper) -> segmentation into readable
lines -> text clips on the timeline, one undo step, every line
correctable by hand like any other title.
"""

from ive.ai.subtitles.segment import SubtitleLine, segment_words
from ive.ai.subtitles.task import SubtitleTask, TranscribeError

__all__ = ["SubtitleTask", "TranscribeError", "SubtitleLine", "segment_words"]
