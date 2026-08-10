# Stage 24 · Sharp checkpoint durability

### Goal

Build sharp checkpoint durability and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/minipostgres/wal/checkpoint.py`
    - `src/minipostgres/wal/recovery.py`
    - `tests/unit/wal/test_checkpoint.py`
    - `tests/unit/wal/test_recovery.py`

### The problem at this point

WAL-before-data, commit records, page LSNs, and checkpoint publication must form one crash-order proof.

### Test contract

#### See the failure first

The focused tests force sharp checkpoint durability through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/unit/wal/test_checkpoint.py"
    ```diff
    diff --git a/tests/unit/wal/test_checkpoint.py b/tests/unit/wal/test_checkpoint.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3d6b711930eaccbbae154e77f8643560f4abfc2a
    --- /dev/null
    +++ b/tests/unit/wal/test_checkpoint.py
    @@ -0,0 +1,43 @@
    +from __future__ import annotations
    +
    +from minipostgres.storage.buffer import BufferPool
    +from minipostgres.storage.constants import PageKind
    +from minipostgres.storage.disk import DiskManager
    +from minipostgres.storage.identifiers import heap_relation
    +from minipostgres.storage.page import decode_page, encode_page
    +from minipostgres.wal.checkpoint import sharp_checkpoint
    +from minipostgres.wal.control_file import ControlFile
    +from minipostgres.wal.manager import WalManager
    +from minipostgres.wal.records import CheckpointRecord
    +
    +
    +def test_sharp_checkpoint_flushes_wal_pages_and_control_metadata(tmp_path) -> None:
    +    disk = DiskManager.open(tmp_path)
    +    wal = WalManager.open(tmp_path / "wal.log")
    +    pool = BufferPool(disk, 2, wal_flush_gate=wal.flush)
    +    relation = heap_relation(4)
    +    with pool.new_page(relation, PageKind.HEAP) as guard:
    +        lsn = wal.end_lsn
    +        wal.append(3, CheckpointRecord(0))
    +        guard.replace_bytes(
    +            encode_page(guard.key, PageKind.HEAP, lsn, b"checkpointed")
    +        )
    +        guard.mark_dirty(lsn)
    +        key = guard.key
    +    control = ControlFile(tmp_path / "control")
    +
    +    checkpoint_lsn = sharp_checkpoint(
    +        wal,
    +        pool,
    +        disk,
    +        (relation,),
    +        control,
    +        clean_shutdown=True,
    +    )
    +
    +    assert control.load().checkpoint_lsn == checkpoint_lsn
    +    assert control.load().clean_shutdown
    +    assert decode_page(key, disk.read_page(key)).body == b"checkpointed"
    +    assert wal.flushed_lsn == wal.end_lsn
    +    wal.close()
    +    disk.close()
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force sharp checkpoint durability through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert control.load().checkpoint_lsn == checkpoint_lsn
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/wal/test_recovery.py"
    ```diff
    diff --git a/tests/unit/wal/test_recovery.py b/tests/unit/wal/test_recovery.py
    index 3a3c28eb35516959da587e3719bb929aae819088..b81cf47a7b9ff82420b55a7d4e1b532e8c4ba5af 100644
    --- a/tests/unit/wal/test_recovery.py
    +++ b/tests/unit/wal/test_recovery.py
    @@ -55,3 +55,22 @@ def test_recovery_allocates_a_missing_page_from_a_full_image(tmp_path) -> None:
         assert decode_page(key, disk.read_page(key)).body == b"restored"
         wal.close()
         disk.close()
    +
    +
    +def test_recovery_reconstructs_old_statuses_when_redo_starts_later(
    +    tmp_path,
    +) -> None:
    +    disk = DiskManager.open(tmp_path)
    +    wal = WalManager.open(tmp_path / "wal.log")
    +    wal.append(11, BeginRecord())
    +    wal.append(11, CommitRecord())
    +    redo_start = wal.end_lsn
    +    wal.append(12, BeginRecord())
    +    wal.flush()
    +
    +    result = recover(wal, disk, start_lsn=redo_start)
    +
    +    assert result.statuses.get(11) is TransactionStatus.COMMITTED
    +    assert result.statuses.get(12) is TransactionStatus.ABORTED
    +    wal.close()
    +    disk.close()
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force sharp checkpoint durability through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert control.load().checkpoint_lsn == checkpoint_lsn
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is sharp checkpoint durability. WAL-before-data, commit records, page LSNs, and checkpoint publication must form one crash-order proof.

### Why this mechanism is necessary

WAL-before-data, commit records, page LSNs, and checkpoint publication must form one crash-order proof. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

No data page outruns durable WAL, and recovery starts only from a completely published checkpoint.

### Mechanism blocks

#### Sharp checkpoint durability mechanism

No data page outruns durable WAL, and recovery starts only from a completely published checkpoint.

??? note "File diff: src/minipostgres/wal/checkpoint.py"
    ```diff
    diff --git a/src/minipostgres/wal/checkpoint.py b/src/minipostgres/wal/checkpoint.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..6ed00cf9490e999ce5b4efff8272ad07036530c7
    --- /dev/null
    +++ b/src/minipostgres/wal/checkpoint.py
    @@ -0,0 +1,36 @@
    +"""Sharp checkpoints: force WAL and dirty pages before advancing control."""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Iterable
    +
    +from minipostgres.storage.buffer import BufferPool
    +from minipostgres.storage.disk import DiskManager
    +from minipostgres.storage.identifiers import RelationId
    +from minipostgres.wal.control_file import ControlFile, ControlState
    +from minipostgres.wal.manager import WalManager
    +from minipostgres.wal.records import CheckpointRecord
    +
    +
    +def sharp_checkpoint(
    +    wal: WalManager,
    +    buffer_pool: BufferPool,
    +    disk: DiskManager,
    +    relations: Iterable[RelationId],
    +    control: ControlFile,
    +    *,
    +    clean_shutdown: bool = False,
    +) -> int:
    +    """Create a no-dirty-page checkpoint and publish it atomically."""
    +
    +    wal.flush()
    +    buffer_pool.flush_all()
    +    for relation in sorted(
    +        set(relations),
    +        key=lambda item: (int(item.fork), item.object_id),
    +    ):
    +        disk.sync_relation(relation)
    +    checkpoint_lsn = wal.append(0, CheckpointRecord(wal.end_lsn))
    +    wal.flush()
    +    control.store(ControlState(checkpoint_lsn, clean_shutdown))
    +    return checkpoint_lsn
    ```

??? note "File diff: src/minipostgres/wal/recovery.py"
    ```diff
    diff --git a/src/minipostgres/wal/recovery.py b/src/minipostgres/wal/recovery.py
    index 3908c06abfbd3ef83100c89588787092bc4332c3..acc71bcf81f7f7cc455daf036eb5c3d23c780ad1 100644
    --- a/src/minipostgres/wal/recovery.py
    +++ b/src/minipostgres/wal/recovery.py
    @@ -37,7 +37,7 @@ def recover(
         begun: set[int] = set()
         maximum_xid = 1
         redone = 0
    -    for entry in wal.scan(start_lsn):
    +    for entry in wal.scan():
             maximum_xid = max(maximum_xid, entry.xid)
             record = entry.record
             if isinstance(record, BeginRecord):
    @@ -46,7 +46,7 @@ def recover(
                 statuses.set(entry.xid, TransactionStatus.COMMITTED)
             elif isinstance(record, AbortRecord):
                 statuses.set(entry.xid, TransactionStatus.ABORTED)
    -        elif isinstance(record, HeapPageImagesRecord):
    +        elif isinstance(record, HeapPageImagesRecord) and entry.lsn >= start_lsn:
                 for key, image in record.images:
                     decoded_image = decode_page(key, image)
                     while disk.page_count(key.relation) <= key.page_id:
    ```

**What it is and why it appears**

The central mechanism is sharp checkpoint durability. WAL-before-data, commit records, page LSNs, and checkpoint publication must form one crash-order proof.

**Runtime role**

No data page outruns durable WAL, and recovery starts only from a completely published checkpoint.

**Statement understanding**

The durable boundary is this: no data page outruns durable WAL, and recovery starts only from a completely published checkpoint.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/24-checkpoint-durability/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: no data page outruns durable WAL, and recovery starts only from a completely published checkpoint.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 10](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/10-wal-recovery.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/24-checkpoint-durability/stage.patch)
