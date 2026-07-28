from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from minipostgres.catalog.model import Column, Schema
from minipostgres.executor.memory import MemoryTable
from minipostgres.types import DataType


@given(
    st.lists(
        st.tuples(
            st.integers(min_value=-(2**63), max_value=2**63 - 1),
            st.text(),
        )
    )
)
def test_scan_matches_insert_and_delete_model(
    rows: list[tuple[int, str]],
) -> None:
    schema = Schema.create(
        (
            Column("id", DataType.INT64),
            Column("name", DataType.TEXT),
        )
    )
    table = MemoryTable(table_id=1, schema=schema)
    tids = [table.insert(row) for row in rows]

    for index, tid in enumerate(tids):
        if index % 3 == 0:
            table.delete(tid)

    expected = [
        (tid, row)
        for index, (tid, row) in enumerate(zip(tids, rows, strict=True))
        if index % 3 != 0
    ]
    assert list(table.scan()) == expected
