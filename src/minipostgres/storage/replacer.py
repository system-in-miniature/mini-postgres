"""Deterministic Clock replacement for buffer-pool frames."""

from __future__ import annotations


class ClockReplacer:
    """Select unpinned frames using reference-bit second chances."""

    def __init__(self, frame_count: int) -> None:
        if type(frame_count) is not int or frame_count <= 0:
            raise ValueError("frame_count must be a positive integer")
        self._referenced = [False] * frame_count
        self._evictable = [False] * frame_count
        self._hand = 0

    def record_access(self, frame_id: int) -> None:
        """Give a frame one second chance on a future Clock sweep."""

        self._validate_frame_id(frame_id)
        self._referenced[frame_id] = True

    def mark_evictable(self, frame_id: int, evictable: bool) -> None:
        """Change whether the frame is currently eligible for eviction."""

        self._validate_frame_id(frame_id)
        self._evictable[frame_id] = evictable

    def evict(self) -> int | None:
        """Return one victim after at most two complete sweeps."""

        # Corresponds to PostgreSQL's shared-buffer clock sweep: referenced
        # frames get a second chance; pinned/non-evictable frames are skipped.
        for _ in range(len(self._evictable) * 2):
            frame_id = self._hand
            self._hand = (self._hand + 1) % len(self._evictable)
            if not self._evictable[frame_id]:
                continue
            if self._referenced[frame_id]:
                self._referenced[frame_id] = False
                continue
            self._evictable[frame_id] = False
            return frame_id
        return None

    def _validate_frame_id(self, frame_id: int) -> None:
        if (
            type(frame_id) is not int
            or frame_id < 0
            or frame_id >= len(self._evictable)
        ):
            raise IndexError(f"frame ID out of range: {frame_id}")
