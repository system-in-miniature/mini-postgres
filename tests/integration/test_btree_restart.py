from __future__ import annotations

from pathlib import Path

from minipostgres.index.btree import BTree
from minipostgres.index.key import KeyCodec
from minipostgres.row import TID
from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.disk import DiskManager
from minipostgres.types import DataType

_INT = KeyCodec((DataType.INT64,))


def test_point_search_delete_and_range_survive_clean_restart(
    tmp_path: Path,
) -> None:
    disk = DiskManager.open(tmp_path)
    pool = BufferPool(disk, frame_count=3)
    tree = BTree.open(pool, index_id=8)
    for key in range(500):
        tree.insert(_INT.encode((key,)), TID(key // 100, key % 100))
    for key in range(0, 500, 7):
        assert tree.delete(
            _INT.encode((key,)),
            TID(key // 100, key % 100),
        )
    expected_height = tree.height
    pool.flush_all()
    disk.sync_relation(tree.relation)
    disk.close()

    reopened_disk = DiskManager.open(tmp_path)
    reopened = BTree.open(
        BufferPool(reopened_disk, frame_count=2),
        index_id=8,
    )

    assert reopened.height == expected_height
    assert reopened.search(_INT.encode((7,))) == ()
    assert reopened.search(_INT.encode((8,))) == (TID(0, 8),)
    assert [
        tid
        for _, tid in reopened.range(_INT.encode((123,)), _INT.encode((321,)))
    ] == [
        TID(key // 100, key % 100)
        for key in range(123, 322)
        if key % 7
    ]
