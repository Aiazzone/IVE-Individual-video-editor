"""Consumers: the only things that ask for frames.

Deliberately free of Qt, so the whole engine can be exercised headless in a
test. The Qt preview consumer is a thin wrapper in ``playback/``.

The point of this file is the promise in docs/ENGINE.md §6.2: **preview and
export pull the SAME graph**. They differ only in the rate they pull at and in
what they do with the frame. If they ever diverge, the exported file stops
matching what the user watched - which is the defect most editors have and
nobody can debug.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable, Iterator

from ive.engine.frame import Frame
from ive.engine.producer import Producer

log = logging.getLogger(__name__)

__all__ = ["Consumer", "PullConsumer", "SequenceWalker"]


class Consumer(ABC):
    """Something that pulls frames out of a graph."""

    def __init__(self, producer: Producer) -> None:
        self.producer = producer

    @abstractmethod
    def pull(self, position: int) -> Frame | None:
        """Fetch one frame."""


class PullConsumer(Consumer):
    """Pulls a single frame on demand: scrubbing, thumbnails, one export step.

    ``want_image`` and ``want_audio`` decide what actually gets evaluated. The
    stacks are lazy, so asking for audio only really does skip the video
    decode - that is how waveform extraction stays cheap.
    """

    def __init__(self, producer: Producer, *, want_image: bool = True,
                 want_audio: bool = False) -> None:
        super().__init__(producer)
        self.want_image = want_image
        self.want_audio = want_audio

    def pull(self, position: int) -> Frame | None:
        frame = self.producer.frame_at(int(position))
        if frame is None:
            return None
        # Force evaluation here, on the caller's thread, so the cost is paid
        # where the caller expects it rather than later on the GUI thread.
        if self.want_image:
            frame.image()
        if self.want_audio:
            frame.audio()
        return frame


class SequenceWalker(Consumer):
    """Walks a range of frames in order: rendering, analysis, export.

    Sequential access is what keeps the decoders on their fast path, so a
    walker is always cheaper than a loop of random pulls.
    """

    def __init__(self, producer: Producer, *, want_image: bool = True,
                 want_audio: bool = True, start: int = 0,
                 end: int | None = None) -> None:
        super().__init__(producer)
        self.want_image = want_image
        self.want_audio = want_audio
        self.start = int(start)
        self.end = int(end) if end is not None else producer.length
        self._cancelled = False

    def pull(self, position: int) -> Frame | None:
        frame = self.producer.frame_at(int(position))
        if frame is None:
            return None
        if self.want_image:
            frame.image()
        if self.want_audio:
            frame.audio()
        return frame

    def cancel(self) -> None:
        self._cancelled = True

    def __iter__(self) -> Iterator[Frame]:
        for position in range(self.start, self.end):
            if self._cancelled:
                log.info("Sequence walk cancelled at %d", position)
                return
            frame = self.pull(position)
            if frame is None:
                return
            yield frame

    def run(self, on_frame: Callable[[Frame], None],
            on_progress: Callable[[int, int], None] | None = None) -> int:
        """Walk the range, handing each frame to ``on_frame``."""
        total = max(0, self.end - self.start)
        done = 0
        for frame in self:
            on_frame(frame)
            done += 1
            if on_progress is not None and done % 10 == 0:
                on_progress(done, total)
        if on_progress is not None:
            on_progress(done, total)
        return done
