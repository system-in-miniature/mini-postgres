"""Pinned fixed-frame page cache with WAL-before-data flush ordering."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from types import TracebackType
from typing import Protocol, runtime_checkable

from minipostgres.errors import BufferPoolFull, DatabaseClosed
from minipostgres.storage.constants import PageKind
from minipostgres.storage.identifiers import PageKey, RelationId
from minipostgres.storage.page import decode_page, encode_page
from minipostgres.storage.replacer import ClockReplacer


class PageDisk(Protocol):
    """The page I/O surface required by the buffer pool."""

    def read_page(self, key: PageKey) -> bytes: ...

    def write_page(self, key: PageKey, encoded: bytes) -> None: ...


@runtime_checkable
class AllocatingPageDisk(PageDisk, Protocol):
    """Page disk extension used by ``new_page``."""

    def allocate_page(
        self,
        relation: RelationId,
        kind: PageKind | None = None,
    ) -> PageKey: ...


@runtime_checkable
class CountingPageDisk(PageDisk, Protocol):
    """Page disk extension used to inspect relation length."""

    def page_count(self, relation: RelationId) -> int: ...


@runtime_checkable
class RootedPageDisk(PageDisk, Protocol):
    """Page disk extension exposing the database storage root."""

    root: Path


@dataclass(slots=True)
class _Frame:
    frame_id: int
    key: PageKey | None = None
    page_bytes: bytes = b""
    page_lsn: int = 0
    pin_count: int = 0
    dirty: bool = False


@dataclass(frozen=True, slots=True)
class FrameSnapshot:
    """Read-only diagnostic view of one resident frame."""

    frame_id: int
    key: PageKey
    page_lsn: int
    pin_count: int
    dirty: bool


def _no_wal_yet(page_lsn: int) -> None:
    if page_lsn != 0:
        raise RuntimeError(
            "nonzero page LSN cannot flush before WAL is implemented"
        )


class BufferPool:
    """Mediate all normal relation-page reads, writes, pins, and eviction."""

    def __init__(
        self,
        disk: PageDisk,
        frame_count: int,
        *,
        wal_flush_gate: Callable[[int], None] | None = None,
    ) -> None:
        if type(frame_count) is not int or frame_count <= 0:
            raise ValueError("frame_count must be a positive integer")
        self._disk = disk
        self._frames = [_Frame(frame_id) for frame_id in range(frame_count)]
        self._page_table: dict[PageKey, int] = {}
        self._free_frames = list(range(frame_count))
        self._clock = ClockReplacer(frame_count)
        self._wal_flush_gate = wal_flush_gate or _no_wal_yet
        self._lock = RLock()

    @property
    def resident_page_count(self) -> int:
        with self._lock:
            return len(self._page_table)

    @property
    def storage_root(self) -> Path:
        """Return the database root required by persistent sidecars."""

        if not isinstance(self._disk, RootedPageDisk):
            raise TypeError("configured page disk does not expose a storage root")
        return self._disk.root

    def page_count(self, relation: RelationId) -> int:
        """Return the number of allocated pages in a physical relation."""

        if not isinstance(self._disk, CountingPageDisk):
            raise TypeError("configured page disk cannot count relation pages")
        return self._disk.page_count(relation)

    def fetch_page(self, key: PageKey) -> PageGuard:
        """Pin a resident page or load it into a free/evictable frame."""

        with self._lock:
            resident = self._page_table.get(key)
            if resident is not None:
                frame = self._frames[resident]
                frame.pin_count += 1
                self._clock.mark_evictable(resident, False)
                self._clock.record_access(resident)
                return PageGuard(self, resident, key)

            frame_id, from_free_list = self._select_frame()
            frame = self._frames[frame_id]
            try:
                if frame.key is not None:
                    self._flush_frame(frame)
                page_bytes = self._disk.read_page(key)
                decoded = decode_page(key, page_bytes)
            except BaseException:
                if from_free_list:
                    self._free_frames.insert(0, frame_id)
                else:
                    self._clock.mark_evictable(frame_id, True)
                raise

            if frame.key is not None:
                del self._page_table[frame.key]
            frame.key = key
            frame.page_bytes = page_bytes
            frame.page_lsn = decoded.page_lsn
            frame.pin_count = 1
            frame.dirty = False
            self._page_table[key] = frame_id
            self._clock.record_access(frame_id)
            self._clock.mark_evictable(frame_id, False)
            return PageGuard(self, frame_id, key)

    def new_page(
        self,
        relation: RelationId,
        kind: PageKind | None = None,
    ) -> PageGuard:
        """Allocate and immediately pin a new physical page."""

        if not isinstance(self._disk, AllocatingPageDisk):
            raise TypeError("configured page disk does not support allocation")
        key = self._disk.allocate_page(relation, kind)
        return self.fetch_page(key)

    def pin_count(self, key: PageKey) -> int:
        with self._lock:
            return self._resident_frame(key).pin_count

    def frame(self, key: PageKey) -> FrameSnapshot:
        """Return an immutable diagnostic snapshot for tests and metrics."""

        with self._lock:
            frame = self._resident_frame(key)
            assert frame.key is not None
            return FrameSnapshot(
                frame.frame_id,
                frame.key,
                frame.page_lsn,
                frame.pin_count,
                frame.dirty,
            )

    def flush_page(self, key: PageKey) -> None:
        """Flush one dirty resident page after satisfying the WAL gate."""

        with self._lock:
            self._flush_frame(self._resident_frame(key))

    def flush_all(self) -> None:
        """Flush all dirty frames in deterministic frame order."""

        with self._lock:
            for frame in self._frames:
                if frame.key is not None:
                    self._flush_frame(frame)

    def _select_frame(self) -> tuple[int, bool]:
        if self._free_frames:
            return self._free_frames.pop(0), True
        victim = self._clock.evict()
        if victim is None:
            raise BufferPoolFull("all buffer frames are pinned")
        return victim, False

    def _resident_frame(self, key: PageKey) -> _Frame:
        frame_id = self._page_table.get(key)
        if frame_id is None:
            raise KeyError(f"page is not resident: {key}")
        return self._frames[frame_id]

    def _flush_frame(self, frame: _Frame) -> None:
        if not frame.dirty:
            return
        assert frame.key is not None
        self._wal_flush_gate(frame.page_lsn)
        self._disk.write_page(frame.key, frame.page_bytes)
        frame.dirty = False

    def guard_page_bytes(self, frame_id: int, key: PageKey) -> bytes:
        """Return bytes while a matching guard owns a live pin."""

        with self._lock:
            frame = self._guarded_frame(frame_id, key)
            return frame.page_bytes

    def guard_replace_bytes(
        self,
        frame_id: int,
        key: PageKey,
        page_bytes: bytes,
    ) -> None:
        """Replace bytes while a matching guard owns a live pin."""

        with self._lock:
            frame = self._guarded_frame(frame_id, key)
            decoded = decode_page(key, page_bytes)
            if decoded.page_lsn < frame.page_lsn:
                raise ValueError("page replacement cannot decrease its LSN")
            frame.page_bytes = page_bytes
            frame.page_lsn = decoded.page_lsn

    def guard_mark_dirty(
        self,
        frame_id: int,
        key: PageKey,
        page_lsn: int,
    ) -> None:
        """Mark a guarded frame dirty at a nondecreasing LSN."""

        with self._lock:
            frame = self._guarded_frame(frame_id, key)
            if page_lsn < frame.page_lsn:
                raise ValueError("dirty page LSN cannot decrease")
            decoded = decode_page(key, frame.page_bytes)
            frame.page_bytes = encode_page(
                key,
                decoded.kind,
                page_lsn,
                decoded.body,
            )
            frame.page_lsn = page_lsn
            frame.dirty = True

    def release_guard(self, frame_id: int, key: PageKey) -> None:
        """Release one pin owned by a matching page guard."""

        with self._lock:
            frame = self._guarded_frame(frame_id, key)
            if frame.pin_count <= 0:
                raise RuntimeError("buffer frame pin count underflow")
            frame.pin_count -= 1
            if frame.pin_count == 0:
                self._clock.mark_evictable(frame_id, True)

    def _guarded_frame(self, frame_id: int, key: PageKey) -> _Frame:
        frame = self._frames[frame_id]
        if frame.key != key or frame.pin_count <= 0:
            raise DatabaseClosed("page guard no longer owns a pinned frame")
        return frame


class PageGuard:
    """RAII-style ownership of exactly one buffer-frame pin."""

    def __init__(self, pool: BufferPool, frame_id: int, key: PageKey) -> None:
        self._pool = pool
        self._frame_id = frame_id
        self.key = key
        self._released = False

    def __enter__(self) -> PageGuard:
        self._ensure_active()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    @property
    def page_bytes(self) -> bytes:
        self._ensure_active()
        return self._pool.guard_page_bytes(self._frame_id, self.key)

    def replace_bytes(self, page_bytes: bytes) -> None:
        """Replace the complete checksummed page held by this guard."""

        self._ensure_active()
        self._pool.guard_replace_bytes(self._frame_id, self.key, page_bytes)

    def mark_dirty(self, page_lsn: int) -> None:
        """Mark changed bytes dirty at a nondecreasing page LSN."""

        self._ensure_active()
        self._pool.guard_mark_dirty(self._frame_id, self.key, page_lsn)

    def release(self) -> None:
        """Release this guard's pin exactly once."""

        if self._released:
            return
        self._pool.release_guard(self._frame_id, self.key)
        self._released = True

    def _ensure_active(self) -> None:
        if self._released:
            raise DatabaseClosed("page guard has been released")
