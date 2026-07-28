from __future__ import annotations

from dataclasses import dataclass

from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.constants import PageKind
from minipostgres.storage.identifiers import PageKey, heap_page_key
from minipostgres.storage.page import encode_page


@dataclass(frozen=True)
class RecordedWrite:
    key: PageKey
    page: bytes


class RecordingDisk:
    def __init__(self, pages: dict[PageKey, bytes]) -> None:
        self.pages = pages
        self.writes: list[RecordedWrite] = []

    def read_page(self, key: PageKey) -> bytes:
        return self.pages[key]

    def write_page(self, key: PageKey, page: bytes) -> None:
        self.writes.append(RecordedWrite(key, page))
        self.pages[key] = page


def test_dirty_eviction_flushes_wal_before_page() -> None:
    first_key = heap_page_key(1, 0)
    second_key = heap_page_key(1, 1)
    disk = RecordingDisk(
        {
            first_key: encode_page(first_key, PageKind.HEAP, 0, b"first"),
            second_key: encode_page(second_key, PageKind.HEAP, 0, b"second"),
        }
    )
    operations: list[tuple[str, int]] = []

    def wal_gate(page_lsn: int) -> None:
        operations.append(("wal", page_lsn))

    pool = BufferPool(disk, frame_count=1, wal_flush_gate=wal_gate)
    with pool.fetch_page(first_key) as guard:
        guard.replace_bytes(encode_page(first_key, PageKind.HEAP, 0, b"dirty"))
        guard.mark_dirty(page_lsn=44)

    with pool.fetch_page(second_key):
        pass

    assert operations == [("wal", 44)]
    assert [write.key for write in disk.writes] == [first_key]
