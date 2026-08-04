"""Subprocess boundaries for SIGKILL setup and isolated recovery timing."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from bench.fixtures import build_recovery_wal
from minipostgres.catalog.catalog import Catalog
from minipostgres.storage.constants import PageKind
from minipostgres.storage.disk import DiskManager
from minipostgres.storage.identifiers import heap_page_key, heap_relation
from minipostgres.storage.page import decode_page
from minipostgres.storage.slotted import SlottedPage
from minipostgres.wal.control_file import ControlFile
from minipostgres.wal.manager import WalManager
from minipostgres.wal.recovery import recover as redo


def prepare(root: Path, row_count: int, checkpoint: bool, ready: Path) -> None:
    metadata = build_recovery_wal(
        root,
        row_count=row_count,
        checkpoint=checkpoint,
    )
    ready.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
    while True:
        time.sleep(1)


def recover(root: Path) -> None:
    started = time.perf_counter_ns()
    control = ControlFile(root / "control").load()
    wal = WalManager.open(root / "wal.log")
    disk = DiskManager.open(root)
    result = redo(
        wal,
        disk,
        start_lsn=control.checkpoint_lsn,
        initial_statuses=control.statuses,
        next_xid=control.next_xid,
    )
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    table = Catalog.open(root).table("recovery_rows")
    relation = heap_relation(table.table_id)
    rows = 0
    for page_id in range(disk.page_count(relation)):
        key = heap_page_key(table.table_id, page_id)
        decoded = decode_page(key, disk.read_page(key))
        if decoded.kind is not PageKind.HEAP:
            raise RuntimeError("recovered relation contains a non-heap page")
        rows += len(SlottedPage.from_body(page_id, decoded.body).live_slots())
    payload = {
        "elapsed_ms": elapsed_ms,
        "recovered_rows": rows,
        "redone_pages": result.redone_pages,
    }
    wal.close()
    disk.close()
    print(json.dumps(payload, sort_keys=True), flush=True)
    os._exit(0)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("root", type=Path)
    prepare_parser.add_argument("row_count", type=int)
    prepare_parser.add_argument("checkpoint", choices=("yes", "no"))
    prepare_parser.add_argument("ready", type=Path)
    recover_parser = subparsers.add_parser("recover")
    recover_parser.add_argument("root", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "prepare":
        prepare(
            arguments.root,
            arguments.row_count,
            arguments.checkpoint == "yes",
            arguments.ready,
        )
    else:
        recover(arguments.root)


if __name__ == "__main__":
    main()
