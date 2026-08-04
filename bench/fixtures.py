"""Fast, deterministic physical fixtures for benchmark setup only.

The measured operations still use MiniPostgres. These builders avoid turning
the intentionally expensive per-row full-page-image write path into tens of
minutes of unmeasured setup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from minipostgres import Database
from minipostgres.catalog.catalog import Catalog
from minipostgres.catalog.model import Schema
from minipostgres.errors import PageFull
from minipostgres.index.key import KeyCodec
from minipostgres.index.pages import (
    InternalPage,
    LeafEntry,
    LeafPage,
    MetaPage,
    encode_internal,
    encode_leaf,
    encode_meta,
)
from minipostgres.row import TID
from minipostgres.storage.constants import PAGE_BODY_SIZE, PageKind
from minipostgres.storage.disk import DiskManager
from minipostgres.storage.identifiers import (
    PageKey,
    btree_page_key,
    btree_relation,
    heap_page_key,
    heap_relation,
)
from minipostgres.storage.page import encode_page
from minipostgres.storage.slotted import SLOT_ENTRY_SIZE, SlottedPage
from minipostgres.storage.tuple import SYSTEM_XID, TupleCodec, TupleVersion
from minipostgres.transaction.status import TransactionStatus
from minipostgres.wal.control_file import ControlFile, ControlState
from minipostgres.wal.manager import WalManager
from minipostgres.wal.records import (
    BeginRecord,
    CheckpointRecord,
    CommitRecord,
    HeapPageImagesRecord,
)


@dataclass(frozen=True, slots=True)
class HeapFixture:
    root: Path
    table_name: str
    table_id: int
    row_count: int
    updated_row_count: int
    page_count: int
    live_tids: tuple[TID, ...]


def _create_table(root: Path, table_name: str, *, recovery: bool = False) -> None:
    columns = "id INT" if recovery else "id INT, payload INT"
    with Database.open(root) as database:
        database.execute(f"CREATE TABLE {table_name} ({columns})")


def _write_heap_page(
    disk: DiskManager,
    table_id: int,
    page: SlottedPage,
) -> None:
    relation = heap_relation(table_id)
    key = disk.allocate_page(relation, PageKind.HEAP)
    if key.page_id != page.page_id:
        raise RuntimeError("heap fixture page IDs are not contiguous")
    disk.write_page(
        key,
        encode_page(key, PageKind.HEAP, page_lsn=0, body=page.to_body()),
    )


def build_heap_fixture(
    root: Path,
    *,
    row_count: int,
    updated_row_count: int = 0,
    table_name: str = "bench_rows",
) -> HeapFixture:
    """Build a valid heap with optional committed UPDATE-style chains."""

    if row_count <= 0:
        raise ValueError("row_count must be positive")
    if not 0 <= updated_row_count <= row_count:
        raise ValueError("updated_row_count must be within the live row count")
    root = Path(root)
    _create_table(root, table_name)
    catalog = Catalog.open(root)
    table = catalog.table(table_name)
    codec = TupleCodec(table.schema)
    disk = DiskManager.open(root)
    relation = heap_relation(table.table_id)
    page_id = 0
    page = SlottedPage.empty(page_id)
    live_tids: list[TID] = []

    def flush_page() -> None:
        nonlocal page_id, page
        _write_heap_page(disk, table.table_id, page)
        page_id += 1
        page = SlottedPage.empty(page_id)

    for row_id in range(row_count):
        if row_id < updated_row_count:
            live = codec.encode(TupleVersion(2, 0, None, (row_id, row_id % 1_000 + 1)))
            # The live member is inserted first so its stable TID is known
            # before encoding the retired root's forward link.
            pair_bytes = len(live) * 2 + 2 * SLOT_ENTRY_SIZE
            if pair_bytes > page.contiguous_free_bytes:
                flush_page()
            live_slot = page.insert(live)
            live_tid = TID(page_id, live_slot)
            retired = codec.encode(
                TupleVersion(
                    SYSTEM_XID,
                    2,
                    live_tid,
                    (row_id, row_id % 1_000),
                )
            )
            page.insert(retired)
            live_tids.append(live_tid)
            continue

        encoded = codec.encode(
            TupleVersion(SYSTEM_XID, 0, None, (row_id, row_id % 1_000))
        )
        if len(encoded) + SLOT_ENTRY_SIZE > page.contiguous_free_bytes:
            flush_page()
        slot_id = page.insert(encoded)
        live_tids.append(TID(page_id, slot_id))

    _write_heap_page(disk, table.table_id, page)
    disk.sync_relation(relation)
    disk.close()
    pages = page_id + 1

    if updated_row_count:
        control = ControlFile(root / "control")
        previous = control.load()
        control.store(
            ControlState(
                checkpoint_lsn=previous.checkpoint_lsn,
                clean_shutdown=True,
                next_xid=3,
                statuses=((2, TransactionStatus.COMMITTED),),
            )
        )

    with Database.open(root, buffer_frames=128) as database:
        database.execute(f"ANALYZE {table_name}")

    return HeapFixture(
        root=root,
        table_name=table_name,
        table_id=table.table_id,
        row_count=row_count,
        updated_row_count=updated_row_count,
        page_count=pages,
        live_tids=tuple(live_tids),
    )


def _leaf_capacity(codec: KeyCodec) -> int:
    entries: list[LeafEntry] = []
    while True:
        index = len(entries)
        entries.append(LeafEntry(codec.encode((index,)), TID(index, 0)))
        try:
            encode_leaf(LeafPage(tuple(entries), None, None))
        except PageFull:
            return len(entries) - 1


def _write_btree_page(
    disk: DiskManager,
    index_id: int,
    kind: PageKind,
    body: bytes,
) -> int:
    relation = btree_relation(index_id)
    key = disk.allocate_page(relation, kind)
    disk.write_page(key, encode_page(key, kind, page_lsn=0, body=body))
    return key.page_id


def install_bulk_index(
    root: Path,
    fixture: HeapFixture,
    *,
    index_name: str,
) -> dict[str, int]:
    """Install a sorted two-level B+Tree without timing its setup build."""

    catalog = Catalog.open(root)
    table = catalog.table(fixture.table_id)
    metadata = catalog.prepare_index(
        index_name,
        table.table_id,
        (0,),
        unique=False,
    )
    codec = KeyCodec((table.schema.column(0).data_type,))
    capacity = _leaf_capacity(codec)
    all_entries = tuple(
        LeafEntry(codec.encode((row_id,)), fixture.live_tids[row_id])
        for row_id in range(fixture.row_count)
    )
    chunks = tuple(
        all_entries[offset : offset + capacity]
        for offset in range(0, len(all_entries), capacity)
    )
    disk = DiskManager.open(root)
    meta_page_id = _write_btree_page(
        disk,
        metadata.index_id,
        PageKind.BTREE_META,
        encode_meta(MetaPage(1, 1)),
    )
    if meta_page_id != 0:
        raise RuntimeError("B+Tree metapage is not page zero")
    leaf_ids: list[int] = []
    for chunk_index, chunk in enumerate(chunks):
        leaf_id = chunk_index + 1
        actual = _write_btree_page(
            disk,
            metadata.index_id,
            PageKind.BTREE_LEAF,
            encode_leaf(
                LeafPage(
                    chunk,
                    None if chunk_index == 0 else leaf_id - 1,
                    None if chunk_index + 1 == len(chunks) else leaf_id + 1,
                )
            ),
        )
        if actual != leaf_id:
            raise RuntimeError("B+Tree fixture leaf IDs are not contiguous")
        leaf_ids.append(leaf_id)

    if len(leaf_ids) == 1:
        root_page_id = leaf_ids[0]
        height = 1
    else:
        root_node = InternalPage(
            tuple(chunk[0].key for chunk in chunks[1:]),
            tuple(leaf_ids),
        )
        root_page_id = _write_btree_page(
            disk,
            metadata.index_id,
            PageKind.BTREE_INTERNAL,
            encode_internal(root_node),
        )
        height = 2

    # Rewrite metapage zero with the final root identity.
    relation = btree_relation(metadata.index_id)
    key = btree_page_key(metadata.index_id, 0)
    disk.write_page(
        key,
        encode_page(
            key,
            PageKind.BTREE_META,
            page_lsn=0,
            body=encode_meta(MetaPage(root_page_id, height)),
        ),
    )
    disk.sync_relation(relation)
    disk.close()
    catalog.publish_index(metadata)
    return {
        "index_id": metadata.index_id,
        "height": height,
        "leaf_pages": len(leaf_ids),
        "entries": fixture.row_count,
    }


def _recovery_pages(schema: Schema, row_count: int):
    codec = TupleCodec(schema)
    page_id = 0
    page = SlottedPage.empty(page_id)
    rows_on_page = 0
    for row_id in range(row_count):
        encoded = codec.encode(TupleVersion(SYSTEM_XID, 0, None, (row_id,)))
        if len(encoded) + SLOT_ENTRY_SIZE > page.contiguous_free_bytes:
            yield page, rows_on_page
            page_id += 1
            page = SlottedPage.empty(page_id)
            rows_on_page = 0
        page.insert(encoded)
        rows_on_page += 1
    yield page, rows_on_page


def build_recovery_wal(
    root: Path,
    *,
    row_count: int,
    checkpoint: bool,
) -> dict[str, int | bool]:
    """Create committed heap page-image WAL, optionally materialize checkpoint."""

    root = Path(root)
    _create_table(root, "recovery_rows", recovery=True)
    catalog = Catalog.open(root)
    table = catalog.table("recovery_rows")
    wal = WalManager.open(root / "wal.log")
    wal.append(2, BeginRecord())
    images: list[tuple[PageKey, bytes]] = []
    free_space_categories = bytearray()
    for page, _ in _recovery_pages(table.schema, row_count):
        key = heap_page_key(table.table_id, page.page_id)
        lsn = wal.end_lsn
        image = encode_page(
            key,
            PageKind.HEAP,
            page_lsn=lsn,
            body=page.to_body(),
        )
        wal.append(2, HeapPageImagesRecord(((key, image),)))
        images.append((key, image))
        free_bytes = page.available_free_bytes
        category = (
            0
            if free_bytes == 0
            else min(
                255,
                (free_bytes * 255 + PAGE_BODY_SIZE - 1) // PAGE_BODY_SIZE,
            )
        )
        free_space_categories.append(category)
    wal.append(2, CommitRecord())
    wal.flush(wal.end_lsn)
    checkpoint_lsn = ControlFile(root / "control").load().checkpoint_lsn
    if checkpoint:
        disk = DiskManager.open(root)
        for key, image in images:
            disk.repair_page(key, image)
        disk.sync_relation(heap_relation(table.table_id))
        disk.close()
        checkpoint_lsn = wal.append(0, CheckpointRecord(wal.end_lsn))
        wal.flush(wal.end_lsn)
    wal_bytes = wal.end_lsn
    wal.close()
    # Ordinary heap writes maintain this sidecar. Publish it once during
    # untimed synthetic setup so startup measures WAL/REDO rather than a
    # missing-fixture FSM rebuild with one fsync per heap page.
    fsm_path = root / "relations" / f"table-{table.table_id}.fsm"
    with fsm_path.open("wb") as stream:
        stream.write(free_space_categories)
        stream.flush()
        os.fsync(stream.fileno())
    ControlFile(root / "control").store(
        ControlState(
            checkpoint_lsn=checkpoint_lsn,
            clean_shutdown=False,
            next_xid=3,
            statuses=((2, TransactionStatus.COMMITTED),),
        )
    )
    return {
        "row_count": row_count,
        "checkpoint": checkpoint,
        "page_images": len(images),
        "wal_bytes": wal_bytes,
        "checkpoint_lsn": checkpoint_lsn,
    }
