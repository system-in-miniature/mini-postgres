from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given
from hypothesis import strategies as st

from minipostgres.catalog.model import Column, Schema, TableMetadata
from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.disk import DiskManager
from minipostgres.storage.heap import HeapTable
from minipostgres.types import DataType


@given(
    st.lists(
        st.tuples(
            st.integers(-(2**63), 2**63 - 1),
            st.text(
                alphabet=st.characters(blacklist_categories=("Cs",)),
                max_size=40,
            ),
        ),
        max_size=30,
    )
)
def test_heap_scan_matches_inserted_rows(
    rows: list[tuple[int, str]],
) -> None:
    metadata = TableMetadata(
        1,
        "items",
        Schema.create(
            (
                Column("id", DataType.INT64),
                Column("name", DataType.TEXT),
            )
        ),
    )
    with TemporaryDirectory() as temporary:
        disk = DiskManager.open(Path(temporary))
        pool = BufferPool(disk, frame_count=3)
        heap = HeapTable.open(pool, metadata)

        tids = [heap.insert(row) for row in rows]

        assert list(heap.scan()) == list(zip(tids, rows, strict=True))
