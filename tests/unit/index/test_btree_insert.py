from __future__ import annotations

from pathlib import Path

from minipostgres.index.btree import BTree
from minipostgres.index.key import KeyCodec
from minipostgres.row import TID
from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.disk import DiskManager
from minipostgres.types import DataType

_INT = KeyCodec((DataType.INT64,))


def _tree(tmp_path: Path) -> BTree:
    disk = DiskManager.open(tmp_path)
    pool = BufferPool(disk, frame_count=4)
    return BTree.open(pool, index_id=1)


def test_btree_root_and_leaf_split_preserve_search(tmp_path: Path) -> None:
    tree = _tree(tmp_path)
    inserted = [
        (_INT.encode((key,)), TID(key // 3, key % 3)) for key in range(500)
    ]

    for key, tid in inserted:
        tree.insert(key, tid)

    assert tree.height > 1
    for key, tid in inserted:
        assert tid in tree.search(key)


def test_duplicate_key_tid_insertion_is_idempotent_and_sorted(
    tmp_path: Path,
) -> None:
    tree = _tree(tmp_path)
    key = _INT.encode((7,))
    tids = (TID(2, 3), TID(0, 9), TID(2, 3), TID(1, 1))

    for tid in tids:
        tree.insert(key, tid)

    assert tree.search(key) == (TID(0, 9), TID(1, 1), TID(2, 3))

