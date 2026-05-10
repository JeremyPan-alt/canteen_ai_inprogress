"""Thread-safe latest-frame buffer.

Realtime camera processing should consume the current image instead of walking
through an old backlog. This buffer keeps only one frame and discards stale
content whenever a new frame arrives.
"""

from __future__ import annotations

import queue
from typing import Generic, Optional, TypeVar


T = TypeVar("T")


class LatestFrameBuffer(Generic[T]):
    """A maxsize=1 queue that always stores the newest item."""

    def __init__(self) -> None:
        self._queue: queue.Queue[T] = queue.Queue(maxsize=1)

    def put(self, item: T) -> None:
        """Store item, dropping any stale frame already in the buffer."""
        try:
            self._queue.put_nowait(item)
            return
        except queue.Full:
            pass

        try:
            self._queue.get_nowait()
        except queue.Empty:
            pass

        self._queue.put_nowait(item)

    def get_latest(self) -> Optional[T]:
        """Return the latest item without removing it from the buffer."""
        with self._queue.mutex:
            if not self._queue.queue:
                return None
            return self._queue.queue[-1]

    def clear(self) -> None:
        """Remove any stored item."""
        with self._queue.mutex:
            self._queue.queue.clear()
            self._queue.unfinished_tasks = 0
            self._queue.not_full.notify_all()

    def has_frame(self) -> bool:
        return self.get_latest() is not None
