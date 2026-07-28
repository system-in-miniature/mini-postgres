from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, settings
from hypothesis import strategies as st

from minipostgres.index.btree import BTree
from minipostgres.index.key import KeyCodec
from minipostgres.row import TID
from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.disk import DiskManager
from minipostgres.types import DataType

_INT = KeyCodec((DataType.INT64,))
_TIDS = st.builds(
    TID,
    page_id=st.integers(0, 100),
    slot_id=st.integers(0, 100),
)


@settings(deadline=None, max_examples=30)
@given(
    st.lists(
        st.tuples(st.integers(-(2**31), 2**31 - 1), _TIDS),
        max_size=250,
    )
)
def test_btree_matches_sorted_multimap(
    entries: list[tuple[int, TID]],
) -> None:
    with TemporaryDirectory() as temporary:
        disk = DiskManager.open(Path(temporary))
        pool = BufferPool(disk, frame_count=5)
        tree = BTree.open(pool, index_id=1)
        model: dict[bytes, list[TID]] = defaultdict(list)

        for value, tid in entries:
            key = _INT.encode((value,))
            tree.insert(key, tid)
            if tid not in model[key]:
                model[key].append(tid)

        assert [(key, tree.search(key)) for key in sorted(model)] == [
            (key, tuple(sorted(tids, key=lambda tid: (tid.page_id, tid.slot_id))))
            for key, tids in sorted(model.items())
        ]
