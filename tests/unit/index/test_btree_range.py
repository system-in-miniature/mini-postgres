from __future__ import annotations

from pathlib import Path

from minipostgres.index.btree import BTree
from minipostgres.index.key import KeyCodec
from minipostgres.row import TID
from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.disk import DiskManager
from minipostgres.storage.identifiers import btree_page_key
from minipostgres.types import DataType

_INT = KeyCodec((DataType.INT64,))


def test_range_iterator_crosses_leaf_siblings_and_is_inclusive(
    tmp_path: Path,
) -> None:
    disk = DiskManager.open(tmp_path)
    tree = BTree.open(BufferPool(disk, frame_count=4), index_id=1)
    for key in range(500):
        tree.insert(_INT.encode((key,)), TID(0, key))

    entries = list(tree.range(_INT.encode((123,)), _INT.encode((321,))))

    assert [tid.slot_id for _, tid in entries] == list(range(123, 322))


def test_range_iterator_releases_its_current_leaf_pin_on_close(
    tmp_path: Path,
) -> None:
    disk = DiskManager.open(tmp_path)
    pool = BufferPool(disk, frame_count=4)
    tree = BTree.open(pool, index_id=1)
    for key in range(500):
        tree.insert(_INT.encode((key,)), TID(0, key))
    iterator = tree.range(_INT.encode((100,)), _INT.encode((400,)))

    next(iterator)
    current_page_id = iterator.current_page_id
    assert current_page_id is not None
    key = btree_page_key(1, current_page_id)
    assert pool.pin_count(key) == 1

    iterator.close()

    assert pool.pin_count(key) == 0

