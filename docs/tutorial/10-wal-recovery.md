# 10. WAL, Checkpoints, and REDO-Only Recovery

Durability is an ordering problem. A database cannot let a dirty data page
reach stable storage before the log evidence needed to recover it, and it
cannot report commit success before the commit record is durable. MiniPostgres
makes both rules visible with a checksummed WAL of full-page post-images, page
LSNs, a flush gate, sharp checkpoints, tail repair, and REDO-only startup
recovery.

## Learning objectives

After this chapter, you will be able to:

- decode the purpose of MiniPostgres WAL record framing and LSNs;
- trace a heap change through page-image logging and the buffer pool's
  WAL-before-data gate;
- state the exact order of a durable commit and a sharp checkpoint;
- distinguish repairable torn WAL tails from fatal earlier corruption;
- explain the REDO LSN test and why incomplete transactions need no physical
  UNDO for visibility correctness.

## WAL records are a checksummed byte stream

`src/minipostgres/wal/records.py` defines five record kinds:
`BeginRecord`, `HeapPageImagesRecord`, `CommitRecord`, `AbortRecord`, and
`CheckpointRecord`. `encode_record()` writes a fixed header containing magic,
format version, kind, total length, LSN, XID, payload length, and checksum.
Page-image payloads contain one or more `(PageKey, 8192-byte image)` pairs.
`decode_record()` verifies every framing field and CRC before returning a
typed `DecodedWalRecord`.

An LSN here is the byte offset where a record begins. Therefore
`DecodedWalRecord.end_lsn` is the first byte after it, and a record's position
can be checked against the offset found while scanning. The format is local to
MiniPostgres; neither record IDs nor bytes are readable by PostgreSQL.

`src/minipostgres/wal/manager.py`, `WalManager.append()`, encodes and writes a
record with `os.pwrite`, updates the in-memory entry list, and advances
`end_lsn`. Append does not imply durable media. `WalManager.flush()` calls
`os.fsync` when the flushed boundary trails the stream end and then advances
`flushed_lsn`.

The difference between appended and flushed is the space in which a process or
machine crash matters. Tests place failpoints on both sides of that boundary.

## Full-page post-images and the page LSN

Every logged heap-page mutation in MiniPostgres creates a complete *post-change*
image. `src/minipostgres/storage/heap.py`, `HeapTable._publish_page()`, encodes
the modified page, appends a `HeapPageImagesRecord`, installs that record's LSN
in the page header, and marks the buffer frame dirty. A single logical
operation may record more than one page image when needed.

The page LSN answers: “Which WAL change is already reflected in these page
bytes?” During recovery, a newer image must replace an older page; an equal or
newer page must not be rolled backward.

The full-image choice makes torn-page repair and idempotent REDO direct. It is
also expensive: an 8192-byte image plus framing is logged for every heap
mutation, even when a compact logical or physiological description would be
small. The difference is explicitly documented in
[Differences from PostgreSQL](../differences.md).

## The WAL-before-data gate

A dirty frame must not be written before its WAL evidence is durable.
`src/minipostgres/storage/buffer.py`, `BufferPool._flush_frame()`, invokes its
configured `wal_flush_gate` with the frame's page LSN before calling
`DiskManager.write_page()`. `Database.__init__()` supplies
`WalManager.flush` as that gate.

This creates the required order:

```text
append page-image WAL
→ assign its LSN to the changed page
→ mark buffer dirty
→ before data write, fsync WAL through the required point
→ write data page
```

If the process crashes before the page write, recovery has a durable image to
redo. If it crashes after the page write, replay sees an equal page LSN and is
idempotent. The rule does not require every modification to synchronously write
its data page.

## Successful commit means durable commit evidence

`src/minipostgres/transaction/manager.py`,
`TransactionManager.commit()`, handles transactions with writes as:

1. append `CommitRecord`;
2. pass the `after_commit_append_before_flush` failpoint;
3. flush WAL through its current end;
4. pass `after_commit_flush_before_response`;
5. mark the transaction object committed;
6. publish `COMMITTED` in the status table, remove it from the active set, and
   release locks.

The external success path occurs only after step 3. A crash before the flush
may lose the commit and recovery treats the XID as aborted. A crash after the
flush but before the client response may recover the commit even though the
client did not receive success—the classic uncertain outcome boundary.

MiniPostgres uses synchronous fsync for each writing commit. It has no group
commit, asynchronous commit option, WAL writer, replication acknowledgment, or
configurable durability level.

## Sharp checkpoints

`src/minipostgres/wal/checkpoint.py`, `sharp_checkpoint()`, deliberately uses a
simple, strong order:

```text
flush WAL
→ flush all dirty buffer frames
→ fsync every published relation
→ append and flush CHECKPOINT
→ atomically replace the control file
```

The checkpoint record carries a redo start boundary. The control file stores
the checkpoint LSN, clean-shutdown flag, next XID, and transaction-status
snapshot. `src/minipostgres/wal/control_file.py`, `ControlFile.store()`,
encodes checksummed JSON behind a versioned header, writes and fsyncs a
temporary file, atomically replaces the target, and fsyncs the parent
directory.

`Database.close()` aborts active transactions and calls
`Database.checkpoint(clean_shutdown=True)`. On ordinary open, the engine first
runs recovery and then publishes `clean_shutdown=False`, so an unclean process
exit is detectable.

A sharp checkpoint forces all dirty state out before publication. PostgreSQL's
checkpoint and restartpoint machinery is much more concurrent and spreads
writeback; MiniPostgres chooses an easily inspectable stop-the-world-style
ordering.

## Tail repair and fail-closed corruption

`WalManager.open()` calls `_scan_descriptor()`. A record is accepted only if
its full header, declared length, checksum, and stored LSN are valid. An
incomplete final header, an incomplete final payload, or a checksum failure in
the final framed record ends the valid prefix. `open()` truncates the file to
that prefix and fsyncs it.

Earlier corruption is different. If invalid framing or checksum appears while
more bytes follow, scanning raises `CorruptWal`. Silently discarding an
arbitrary suffix after interior corruption could erase already durable
transactions and invent a recovery boundary. The behavior contract is
therefore “repair a torn tail, fail closed on earlier corruption,” not “ignore
all bad WAL.”

## REDO-only startup

`src/minipostgres/wal/recovery.py`, `recover()`, scans typed WAL records,
reconstructs transaction statuses, and replays page images at or beyond the
checkpoint's redo start. For each image it decodes and verifies the page. If
the on-disk page is missing, corrupt, or has a lower page LSN than the image,
`DiskManager.repair_page()` installs the WAL image. Otherwise no write is
needed.

After scanning, every begun or stored `IN_PROGRESS` XID becomes `ABORTED`.
There is no physical UNDO pass. Versions from incomplete transactions can
remain in heap pages because `is_visible()` rejects aborted creators and treats
aborted deleters as ineffective. Chapter 11's VACUUM later reclaims dead
bytes.

B+Trees are treated as derived state. In
`src/minipostgres/engine.py`, `Database.__init__()`, an unclean open removes
published index relation files, recovers heap truth, rebuilds indexes from
globally live versions, flushes them, and fsyncs their relations. This trades
recovery speed for a smaller logged truth set.

## Compared with PostgreSQL 18

PostgreSQL WAL insertion and flush code lives under
`src/backend/access/transam/xlog.c`; resource managers describe operations,
and page LSN checks guide physical REDO. Checkpoint orchestration spans
`xlog.c`, `checkpointer.c`, buffer management, and control-file code.
PostgreSQL normally logs one full-page image for the first page modification
after a checkpoint when `full_page_writes` is enabled, then uses compact
resource-manager records for later changes.

MiniPostgres preserves WAL-before-data, durable commit evidence, page-LSN
idempotence, checkpoint ordering, and torn-tail recovery as teaching
contracts. It does not implement PostgreSQL WAL formats, segments, timelines,
archive recovery, PITR, replication, group commit, background writer behavior,
or ARIES-style physiological record breadth. See the `wal_before_data`,
`durable_commit`, and `redo` rows in the
[behavior matrix](../behavior-matrix.md) and the durability flow in the
[architecture reference](../architecture-reference.md).

## Hands-on experiment: repair only a torn tail

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from minipostgres.wal.manager import WalManager
from minipostgres.wal.records import BeginRecord, CommitRecord

with TemporaryDirectory() as root:
    path = Path(root) / "wal.log"
    wal = WalManager.open(path)
    wal.append(2, BeginRecord())
    wal.append(2, CommitRecord())
    wal.flush()
    valid = wal.end_lsn
    wal.close()
    with path.open("ab") as stream:
        stream.write(b"torn-tail")
    print("before repair:", path.stat().st_size > valid)
    reopened = WalManager.open(path)
    print("after repair:", path.stat().st_size == valid)
    print("records:", [type(item.record).__name__ for item in reopened.scan()])
    reopened.close()
PY
```

Measured output:

```text
before repair: True
after repair: True
records: ['BeginRecord', 'CommitRecord']
```

Then verify the ordering gate and torn-page REDO:

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline pytest -q \
  tests/reliability/test_wal_before_data.py::test_heap_change_is_logged_before_dirty_page_can_flush \
  tests/reliability/test_engine_recovery.py::test_recovery_repairs_torn_post_checkpoint_heap_page
```

```text
..                                                                       [100%]
2 passed in 0.78s
```

## Exercises

1. **Understanding.** A disk page has page LSN 900 and recovery sees valid
   images at LSN 850 and 940. Which image can change the page?

    Acceptance: explain both comparisons and idempotence.

    ??? note "Reference answer"
        The 850 image is skipped because the page is already newer. The 940
        image is installed because its page LSN is newer. Replaying again sees
        equality and skips it, making REDO idempotent.

2. **Understanding.** Why is a checksum error in an earlier WAL record fatal
   while an incomplete last record is truncated?

    Acceptance: discuss what can safely be inferred about a valid prefix.

    ??? note "Reference answer"
        A partial final write has a clear valid prefix ending at the preceding
        record. Interior corruption followed by more bytes does not establish
        that the suffix is safely discardable; truncating there could erase
        durable history, so recovery fails closed.

3. **Hands-on.** In a disposable worktree, add a test that corrupts an interior
   WAL record while leaving a later valid record. Do not edit the tutorial
   author's `src/` tree.

    Acceptance: reopening must raise `CorruptWal` and must not truncate the
    file. Run the new test plus `tests/unit/wal/test_wal_manager.py`.

    ??? note "Reference answer"
        Append and flush three records, close the manager, flip one payload or
        checksum byte in the second record, record the file size, and call
        `WalManager.open()`. Assert `CorruptWal` and unchanged size. The later
        third record makes the damaged second record interior rather than a
        repairable torn tail.

## Summary

MiniPostgres turns durability into inspectable order: page-image WAL precedes
dirty data, commit WAL precedes success, and a sharp checkpoint flushes WAL,
pages, relations, and metadata in sequence. Startup repairs only a verifiable
torn tail, REDOs missing/corrupt/older pages, marks incomplete transactions
aborted, and rebuilds derived indexes. REDO preserves bytes; the next chapter
explains how VACUUM safely removes obsolete versions and how HOT avoids some
index churn before cleanup is needed.
