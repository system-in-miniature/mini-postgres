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
    return BTree.open(BufferPool(disk, frame_count=5), index_id=1)


def test_delete_redistributes_merges_and_collapses_root(tmp_path: Path) -> None:
    tree = _tree(tmp_path)
    for key in range(300):
        tree.insert(_INT.encode((key,)), TID(0, key))

    for key in range(299):
        assert tree.delete(_INT.encode((key,)), TID(0, key))

    assert tree.height == 1
    assert tree.search(_INT.encode((299,))) == (TID(0, 299),)


def test_delete_removes_only_exact_key_tid_pair(tmp_path: Path) -> None:
    tree = _tree(tmp_path)
    key = _INT.encode((7,))
    tids = (TID(0, 1), TID(0, 2), TID(0, 3))
    for tid in tids:
        tree.insert(key, tid)

    assert tree.delete(key, TID(0, 2))
    assert not tree.delete(key, TID(0, 2))
    assert tree.search(key) == (TID(0, 1), TID(0, 3))


def test_delete_rebalances_internal_levels_created_by_wide_keys(
    tmp_path: Path,
) -> None:
    tree = _tree(tmp_path)
    entries = [
        (key.to_bytes(4, "big") + b"x" * 900, TID(0, key))
        for key in range(120)
    ]
    for key, tid in entries:
        tree.insert(key, tid)
    assert tree.height >= 3

    for key, tid in entries[:-1]:
        assert tree.delete(key, tid)

    assert tree.height == 1
    assert tree.search(entries[-1][0]) == (entries[-1][1],)
