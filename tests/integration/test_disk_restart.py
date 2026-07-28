from __future__ import annotations

from pathlib import Path

from minipostgres.storage.constants import PageKind
from minipostgres.storage.disk import DiskManager
from minipostgres.storage.identifiers import heap_relation
from minipostgres.storage.page import decode_page, encode_page


def test_multiple_pages_survive_manager_restart_in_physical_order(
    tmp_path: Path,
) -> None:
    relation = heap_relation(9)
    manager = DiskManager.open(tmp_path)
    keys = [manager.allocate_page(relation) for _ in range(3)]
    for key in keys:
        manager.write_page(
            key,
            encode_page(
                key,
                PageKind.HEAP,
                page_lsn=0,
                body=f"page-{key.page_id}".encode(),
            ),
        )
    manager.sync_relation(relation)
    manager.close()

    reopened = DiskManager.open(tmp_path)

    assert [key.page_id for key in keys] == [0, 1, 2]
    assert [
        decode_page(key, reopened.read_page(key)).body for key in keys
    ] == [b"page-0", b"page-1", b"page-2"]
