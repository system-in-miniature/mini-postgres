"""Fixed-page relation-file I/O for heap and B+Tree forks."""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType

from minipostgres.errors import CorruptPage, DatabaseClosed
from minipostgres.storage.constants import PAGE_SIZE, PageKind
from minipostgres.storage.identifiers import ForkKind, PageKey, RelationId
from minipostgres.storage.page import decode_page, encode_page


def relation_path(root: Path, relation: RelationId) -> Path:
    """Return the stable on-disk path for one physical relation."""

    if relation.fork is ForkKind.HEAP:
        return root / "relations" / f"table-{relation.object_id}.heap"
    return root / "indexes" / f"index-{relation.object_id}.btree"


class DiskManager:
    """Own relation descriptors and exact fixed-size page I/O."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._descriptors: dict[RelationId, int] = {}
        self._closed = False

    @classmethod
    def open(cls, root: Path) -> DiskManager:
        """Open a database storage root, creating fork directories as needed."""

        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        (root / "relations").mkdir(exist_ok=True)
        (root / "indexes").mkdir(exist_ok=True)
        return cls(root)

    def __enter__(self) -> DiskManager:
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def page_count(self, relation: RelationId) -> int:
        """Return the number of complete physical pages in a relation."""

        descriptor = self._descriptor(relation)
        size = os.fstat(descriptor).st_size
        if size % PAGE_SIZE:
            raise CorruptPage(
                f"relation size {size} is not a multiple of page size {PAGE_SIZE}"
            )
        return size // PAGE_SIZE

    def allocate_page(
        self,
        relation: RelationId,
        kind: PageKind | None = None,
    ) -> PageKey:
        """Append one valid empty page and return its stable identity."""

        page_id = self.page_count(relation)
        key = PageKey(relation, page_id)
        if kind is None:
            kind = (
                PageKind.HEAP
                if relation.fork is ForkKind.HEAP
                else PageKind.BTREE_LEAF
            )
        encoded = encode_page(key, kind, page_lsn=0, body=b"")
        self._pwrite_exact(self._descriptor(relation), encoded, page_id * PAGE_SIZE)
        return key

    def read_page(self, key: PageKey) -> bytes:
        """Read one exact page and validate its checksum and identity."""

        descriptor = self._descriptor(key.relation)
        encoded = self._pread_exact(descriptor, PAGE_SIZE, key.page_id * PAGE_SIZE)
        decode_page(key, encoded)
        return encoded

    def write_page(self, key: PageKey, encoded: bytes) -> None:
        """Validate and overwrite one already allocated physical page."""

        decode_page(key, encoded)
        if key.page_id >= self.page_count(key.relation):
            raise CorruptPage(f"page {key.page_id} is not allocated")
        self._pwrite_exact(
            self._descriptor(key.relation),
            encoded,
            key.page_id * PAGE_SIZE,
        )

    def sync_relation(self, relation: RelationId) -> None:
        """Make prior writes to one relation durable."""

        os.fsync(self._descriptor(relation))

    def close(self) -> None:
        """Close every cached descriptor; repeated close is harmless."""

        if self._closed:
            return
        self._closed = True
        descriptors = tuple(self._descriptors.values())
        self._descriptors.clear()
        for descriptor in descriptors:
            os.close(descriptor)

    def _ensure_open(self) -> None:
        if self._closed:
            raise DatabaseClosed("disk manager is closed")

    def _descriptor(self, relation: RelationId) -> int:
        self._ensure_open()
        descriptor = self._descriptors.get(relation)
        if descriptor is not None:
            return descriptor
        path = relation_path(self.root, relation)
        created = not path.exists()
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        self._descriptors[relation] = descriptor
        if created:
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        return descriptor

    @staticmethod
    def _pread_exact(descriptor: int, size: int, offset: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = os.pread(descriptor, remaining, offset + size - remaining)
            if not chunk:
                actual = size - remaining
                raise CorruptPage(
                    f"short page read: expected {size} bytes, got {actual}"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    @staticmethod
    def _pwrite_exact(descriptor: int, data: bytes, offset: int) -> None:
        written = 0
        while written < len(data):
            count = os.pwrite(descriptor, data[written:], offset + written)
            if count <= 0:
                raise OSError(
                    f"short page write: expected {len(data)} bytes, got {written}"
                )
            written += count
