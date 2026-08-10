# Stage 12 · Persistent heap files

### Goal

Build persistent heap files and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/minipostgres/errors.py`
    - `src/minipostgres/storage/buffer.py`
    - `src/minipostgres/storage/constants.py`
    - `src/minipostgres/storage/disk.py`
    - `src/minipostgres/storage/free_space.py`
    - `src/minipostgres/storage/heap.py`
    - `src/minipostgres/storage/identifiers.py`
    - `src/minipostgres/storage/page.py`
    - `src/minipostgres/storage/replacer.py`
    - `src/minipostgres/storage/slotted.py`
    - `src/minipostgres/storage/tuple.py`
    - `tests/integration/test_buffer_eviction.py`
    - `tests/integration/test_disk_restart.py`
    - `tests/integration/test_heap_table.py`
    - `tests/property/test_heap_table_model.py`
    - `tests/property/test_slotted_page_model.py`
    - `tests/property/test_tuple_codec_property.py`
    - `tests/unit/storage/test_buffer_pool.py`
    - `tests/unit/storage/test_clock_replacer.py`
    - `tests/unit/storage/test_disk_manager.py`
    - `tests/unit/storage/test_free_space.py`
    - `tests/unit/storage/test_page_guard.py`
    - `tests/unit/storage/test_slotted_page.py`
    - `tests/unit/storage/test_tuple_codec.py`

### The problem at this point

Pages, slots, tuple bytes, disk IO, replacement, and buffer ownership must compose into stable row locations.

### Test contract

#### See the failure first

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/integration/test_buffer_eviction.py"
    ```diff
    diff --git a/tests/integration/test_buffer_eviction.py b/tests/integration/test_buffer_eviction.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..9be509359ed1e35f6fb94c0450506537e95c7e0a
    --- /dev/null
    +++ b/tests/integration/test_buffer_eviction.py
    @@ -0,0 +1,53 @@
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +
    +from minipostgres.storage.buffer import BufferPool
    +from minipostgres.storage.constants import PageKind
    +from minipostgres.storage.identifiers import PageKey, heap_page_key
    +from minipostgres.storage.page import encode_page
    +
    +
    +@dataclass(frozen=True)
    +class RecordedWrite:
    +    key: PageKey
    +    page: bytes
    +
    +
    +class RecordingDisk:
    +    def __init__(self, pages: dict[PageKey, bytes]) -> None:
    +        self.pages = pages
    +        self.writes: list[RecordedWrite] = []
    +
    +    def read_page(self, key: PageKey) -> bytes:
    +        return self.pages[key]
    +
    +    def write_page(self, key: PageKey, page: bytes) -> None:
    +        self.writes.append(RecordedWrite(key, page))
    +        self.pages[key] = page
    +
    +
    +def test_dirty_eviction_flushes_wal_before_page() -> None:
    +    first_key = heap_page_key(1, 0)
    +    second_key = heap_page_key(1, 1)
    +    disk = RecordingDisk(
    +        {
    +            first_key: encode_page(first_key, PageKind.HEAP, 0, b"first"),
    +            second_key: encode_page(second_key, PageKind.HEAP, 0, b"second"),
    +        }
    +    )
    +    operations: list[tuple[str, int]] = []
    +
    +    def wal_gate(page_lsn: int) -> None:
    +        operations.append(("wal", page_lsn))
    +
    +    pool = BufferPool(disk, frame_count=1, wal_flush_gate=wal_gate)
    +    with pool.fetch_page(first_key) as guard:
    +        guard.replace_bytes(encode_page(first_key, PageKind.HEAP, 0, b"dirty"))
    +        guard.mark_dirty(page_lsn=44)
    +
    +    with pool.fetch_page(second_key):
    +        pass
    +
    +    assert operations == [("wal", 44)]
    +    assert [write.key for write in disk.writes] == [first_key]
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert frame.key is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/integration/test_disk_restart.py"
    ```diff
    diff --git a/tests/integration/test_disk_restart.py b/tests/integration/test_disk_restart.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..0f665bac438c21b4b9dccc9df1745033803f2c1d
    --- /dev/null
    +++ b/tests/integration/test_disk_restart.py
    @@ -0,0 +1,35 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +from minipostgres.storage.constants import PageKind
    +from minipostgres.storage.disk import DiskManager
    +from minipostgres.storage.identifiers import heap_relation
    +from minipostgres.storage.page import decode_page, encode_page
    +
    +
    +def test_multiple_pages_survive_manager_restart_in_physical_order(
    +    tmp_path: Path,
    +) -> None:
    +    relation = heap_relation(9)
    +    manager = DiskManager.open(tmp_path)
    +    keys = [manager.allocate_page(relation) for _ in range(3)]
    +    for key in keys:
    +        manager.write_page(
    +            key,
    +            encode_page(
    +                key,
    +                PageKind.HEAP,
    +                page_lsn=0,
    +                body=f"page-{key.page_id}".encode(),
    +            ),
    +        )
    +    manager.sync_relation(relation)
    +    manager.close()
    +
    +    reopened = DiskManager.open(tmp_path)
    +
    +    assert [key.page_id for key in keys] == [0, 1, 2]
    +    assert [
    +        decode_page(key, reopened.read_page(key)).body for key in keys
    +    ] == [b"page-0", b"page-1", b"page-2"]
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert frame.key is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/integration/test_heap_table.py"
    ```diff
    diff --git a/tests/integration/test_heap_table.py b/tests/integration/test_heap_table.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3bc197e0e28fb3d904da7da458444a0429e250ca
    --- /dev/null
    +++ b/tests/integration/test_heap_table.py
    @@ -0,0 +1,79 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +from minipostgres.catalog.model import Column, Schema, TableMetadata
    +from minipostgres.storage.buffer import BufferPool
    +from minipostgres.storage.disk import DiskManager
    +from minipostgres.storage.heap import HeapTable
    +from minipostgres.types import DataType
    +
    +
    +def _users() -> TableMetadata:
    +    return TableMetadata(
    +        table_id=1,
    +        name="users",
    +        schema=Schema.create(
    +            (
    +                Column("id", DataType.INT64, nullable=False),
    +                Column("name", DataType.TEXT, nullable=False),
    +                Column("age", DataType.INT64),
    +            )
    +        ),
    +    )
    +
    +
    +def _open_heap(root: Path) -> tuple[DiskManager, BufferPool, HeapTable]:
    +    disk = DiskManager.open(root)
    +    pool = BufferPool(disk, frame_count=2)
    +    return disk, pool, HeapTable.open(pool, _users())
    +
    +
    +def test_heap_insert_fetch_scan_update_delete_and_restart(tmp_path: Path) -> None:
    +    disk, pool, heap = _open_heap(tmp_path)
    +    first = heap.insert((1, "A", 20))
    +    second = heap.insert((2, "B", 30))
    +    replacement = heap.replace(second, (2, "B", 31))
    +    assert replacement is not None
    +    assert heap.delete(first)
    +    pool.flush_all()
    +    disk.close()
    +
    +    reopened_disk, reopened_pool, reopened = _open_heap(tmp_path)
    +
    +    assert reopened.fetch(first) is None
    +    assert reopened.fetch(replacement) == (2, "B", 31)
    +    assert list(reopened.scan()) == [(replacement, (2, "B", 31))]
    +    reopened_pool.flush_all()
    +    reopened_disk.close()
    +
    +
    +def test_heap_repairs_stale_free_space_estimate(tmp_path: Path) -> None:
    +    _disk, _pool, heap = _open_heap(tmp_path)
    +    first = heap.insert((1, "x" * 7_500, 20))
    +    assert first.page_id == 0
    +    heap.free_space.record(page_id=0, free_bytes=8_000)
    +
    +    second = heap.insert((2, "y" * 1_000, 30))
    +
    +    assert second.page_id == 1
    +    assert heap.fetch(second) == (2, "y" * 1_000, 30)
    +
    +
    +def test_heap_tids_keep_stable_slots_after_delete_and_compaction(
    +    tmp_path: Path,
    +) -> None:
    +    _disk, _pool, heap = _open_heap(tmp_path)
    +    first = heap.insert((1, "A", 20))
    +    deleted = heap.insert((2, "B", 30))
    +    third = heap.insert((3, "C", 40))
    +
    +    assert heap.delete(deleted)
    +    inserted = heap.insert((4, "D" * 2_000, 50))
    +
    +    assert first.slot_id == 0
    +    assert third.slot_id == 2
    +    assert heap.fetch(first) == (1, "A", 20)
    +    assert heap.fetch(third) == (3, "C", 40)
    +    assert heap.fetch(inserted) == (4, "D" * 2_000, 50)
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert frame.key is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/property/test_heap_table_model.py"
    ```diff
    diff --git a/tests/property/test_heap_table_model.py b/tests/property/test_heap_table_model.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..79950a189416ad04be0b42c927df666336b5ea22
    --- /dev/null
    +++ b/tests/property/test_heap_table_model.py
    @@ -0,0 +1,48 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +from tempfile import TemporaryDirectory
    +
    +from hypothesis import given
    +from hypothesis import strategies as st
    +
    +from minipostgres.catalog.model import Column, Schema, TableMetadata
    +from minipostgres.storage.buffer import BufferPool
    +from minipostgres.storage.disk import DiskManager
    +from minipostgres.storage.heap import HeapTable
    +from minipostgres.types import DataType
    +
    +
    +@given(
    +    st.lists(
    +        st.tuples(
    +            st.integers(-(2**63), 2**63 - 1),
    +            st.text(
    +                alphabet=st.characters(blacklist_categories=("Cs",)),
    +                max_size=40,
    +            ),
    +        ),
    +        max_size=30,
    +    )
    +)
    +def test_heap_scan_matches_inserted_rows(
    +    rows: list[tuple[int, str]],
    +) -> None:
    +    metadata = TableMetadata(
    +        1,
    +        "items",
    +        Schema.create(
    +            (
    +                Column("id", DataType.INT64),
    +                Column("name", DataType.TEXT),
    +            )
    +        ),
    +    )
    +    with TemporaryDirectory() as temporary:
    +        disk = DiskManager.open(Path(temporary))
    +        pool = BufferPool(disk, frame_count=3)
    +        heap = HeapTable.open(pool, metadata)
    +
    +        tids = [heap.insert(row) for row in rows]
    +
    +        assert list(heap.scan()) == list(zip(tids, rows, strict=True))
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert frame.key is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/property/test_slotted_page_model.py"
    ```diff
    diff --git a/tests/property/test_slotted_page_model.py b/tests/property/test_slotted_page_model.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..8aa4650c45266d57b423a4c36ed47b1b7e78759a
    --- /dev/null
    +++ b/tests/property/test_slotted_page_model.py
    @@ -0,0 +1,24 @@
    +from __future__ import annotations
    +
    +from hypothesis import given
    +from hypothesis import strategies as st
    +
    +from minipostgres.errors import PageFull
    +from minipostgres.storage.slotted import SlottedPage
    +
    +
    +@given(st.lists(st.binary(min_size=0, max_size=128), max_size=40))
    +def test_slotted_page_matches_stable_slot_reference(values: list[bytes]) -> None:
    +    page = SlottedPage.empty(page_id=0)
    +    model: dict[int, bytes] = {}
    +
    +    for value in values:
    +        try:
    +            slot = page.insert(value)
    +        except PageFull:
    +            break
    +        model[slot] = value
    +
    +    assert {slot: page.read(slot) for slot in page.live_slots()} == model
    +    restored = SlottedPage.from_body(page_id=0, body=page.to_body())
    +    assert {slot: restored.read(slot) for slot in restored.live_slots()} == model
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert frame.key is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/property/test_tuple_codec_property.py"
    ```diff
    diff --git a/tests/property/test_tuple_codec_property.py b/tests/property/test_tuple_codec_property.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..f8152005e3dcee51017a7f94402c704597e46f13
    --- /dev/null
    +++ b/tests/property/test_tuple_codec_property.py
    @@ -0,0 +1,63 @@
    +from __future__ import annotations
    +
    +import math
    +
    +from hypothesis import given
    +from hypothesis import strategies as st
    +
    +from minipostgres.catalog.model import Column, Schema
    +from minipostgres.row import TID
    +from minipostgres.storage.tuple import TupleCodec, TupleVersion
    +from minipostgres.types import DataType
    +
    +_SCHEMA = Schema.create(
    +    (
    +        Column("number", DataType.INT64),
    +        Column("ratio", DataType.FLOAT64),
    +        Column("flag", DataType.BOOLEAN),
    +        Column("text", DataType.TEXT),
    +    )
    +)
    +_TEXT = st.text(
    +    alphabet=st.characters(blacklist_categories=("Cs",)),
    +    max_size=128,
    +)
    +
    +
    +@given(
    +    integer=st.one_of(st.none(), st.integers(-(2**63), 2**63 - 1)),
    +    floating=st.one_of(
    +        st.none(),
    +        st.floats(allow_nan=False, allow_infinity=False, width=64),
    +    ),
    +    boolean=st.one_of(st.none(), st.booleans()),
    +    text=st.one_of(st.none(), _TEXT),
    +    xmin=st.integers(0, 2**64 - 1),
    +    xmax=st.integers(0, 2**64 - 1),
    +    next_page=st.integers(0, 100),
    +    next_slot=st.integers(0, 100),
    +)
    +def test_tuple_codec_round_trips_supported_scalar_domains(
    +    integer: int | None,
    +    floating: float | None,
    +    boolean: bool | None,
    +    text: str | None,
    +    xmin: int,
    +    xmax: int,
    +    next_page: int,
    +    next_slot: int,
    +) -> None:
    +    version = TupleVersion(
    +        xmin=xmin,
    +        xmax=xmax,
    +        next_tid=TID(next_page, next_slot),
    +        values=(integer, floating, boolean, text),
    +    )
    +
    +    decoded = TupleCodec(_SCHEMA).decode(TupleCodec(_SCHEMA).encode(version))
    +
    +    assert decoded == version
    +    if floating is not None:
    +        assert math.copysign(1.0, decoded.values[1]) == math.copysign(
    +            1.0, floating
    +        )
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert frame.key is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/storage/test_buffer_pool.py"
    ```diff
    diff --git a/tests/unit/storage/test_buffer_pool.py b/tests/unit/storage/test_buffer_pool.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..e7f38cabd3913eed79b7646a0b51d850b9b095a5
    --- /dev/null
    +++ b/tests/unit/storage/test_buffer_pool.py
    @@ -0,0 +1,51 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +import pytest
    +
    +from minipostgres.errors import BufferPoolFull
    +from minipostgres.storage.buffer import BufferPool
    +from minipostgres.storage.disk import DiskManager
    +from minipostgres.storage.identifiers import heap_relation
    +
    +
    +def test_buffer_pool_reuses_a_resident_frame_and_counts_pins(
    +    tmp_path: Path,
    +) -> None:
    +    disk = DiskManager.open(tmp_path)
    +    key = disk.allocate_page(heap_relation(1))
    +    pool = BufferPool(disk, frame_count=1)
    +
    +    first = pool.fetch_page(key)
    +    second = pool.fetch_page(key)
    +
    +    assert pool.resident_page_count == 1
    +    assert pool.pin_count(key) == 2
    +    first.release()
    +    assert pool.pin_count(key) == 1
    +    second.release()
    +    assert pool.pin_count(key) == 0
    +
    +
    +def test_buffer_pool_cannot_evict_the_only_pinned_frame(tmp_path: Path) -> None:
    +    disk = DiskManager.open(tmp_path)
    +    relation = heap_relation(1)
    +    first_key = disk.allocate_page(relation)
    +    second_key = disk.allocate_page(relation)
    +    pool = BufferPool(disk, frame_count=1)
    +
    +    with pool.fetch_page(first_key), pytest.raises(BufferPoolFull):
    +        pool.fetch_page(second_key)
    +
    +
    +def test_default_wal_gate_rejects_nonzero_dirty_lsn(tmp_path: Path) -> None:
    +    disk = DiskManager.open(tmp_path)
    +    key = disk.allocate_page(heap_relation(1))
    +    pool = BufferPool(disk, frame_count=1)
    +
    +    with pool.fetch_page(key) as guard:
    +        guard.mark_dirty(1)
    +
    +    with pytest.raises(RuntimeError, match="WAL"):
    +        pool.flush_page(key)
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert frame.key is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/storage/test_clock_replacer.py"
    ```diff
    diff --git a/tests/unit/storage/test_clock_replacer.py b/tests/unit/storage/test_clock_replacer.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..790bb2183967b0a8d327e481e952c2429fcd0203
    --- /dev/null
    +++ b/tests/unit/storage/test_clock_replacer.py
    @@ -0,0 +1,43 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.storage.replacer import ClockReplacer
    +
    +
    +def test_clock_skips_pinned_and_gives_referenced_frame_second_chance() -> None:
    +    clock = ClockReplacer(frame_count=3)
    +    clock.mark_evictable(0, True)
    +    clock.mark_evictable(1, False)
    +    clock.mark_evictable(2, True)
    +    clock.record_access(0)
    +
    +    assert clock.evict() == 2
    +    assert clock.evict() == 0
    +
    +
    +def test_clock_returns_none_when_every_frame_is_pinned() -> None:
    +    clock = ClockReplacer(frame_count=2)
    +
    +    assert clock.evict() is None
    +
    +
    +def test_evicted_frame_must_be_registered_again_before_reuse() -> None:
    +    clock = ClockReplacer(frame_count=1)
    +    clock.mark_evictable(0, True)
    +
    +    assert clock.evict() == 0
    +    assert clock.evict() is None
    +    clock.mark_evictable(0, True)
    +    assert clock.evict() == 0
    +
    +
    +def test_clock_rejects_invalid_capacity_and_frame_ids() -> None:
    +    with pytest.raises(ValueError):
    +        ClockReplacer(frame_count=0)
    +
    +    clock = ClockReplacer(frame_count=2)
    +    with pytest.raises(IndexError):
    +        clock.record_access(2)
    +    with pytest.raises(IndexError):
    +        clock.mark_evictable(-1, True)
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert frame.key is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/storage/test_disk_manager.py"
    ```diff
    diff --git a/tests/unit/storage/test_disk_manager.py b/tests/unit/storage/test_disk_manager.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..1bd538303a4b0ed03a81a31112b0fc80f96a977d
    --- /dev/null
    +++ b/tests/unit/storage/test_disk_manager.py
    @@ -0,0 +1,65 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +import pytest
    +
    +from minipostgres.errors import CorruptPage, DatabaseClosed
    +from minipostgres.storage.constants import PAGE_SIZE, PageKind
    +from minipostgres.storage.disk import DiskManager, relation_path
    +from minipostgres.storage.identifiers import heap_relation
    +from minipostgres.storage.page import encode_page
    +
    +
    +def test_disk_manager_allocates_reads_and_reopens_pages(tmp_path: Path) -> None:
    +    manager = DiskManager.open(tmp_path)
    +    relation = heap_relation(4)
    +    key = manager.allocate_page(relation)
    +    page = encode_page(key, PageKind.HEAP, 0, b"durable")
    +
    +    manager.write_page(key, page)
    +    manager.sync_relation(relation)
    +    manager.close()
    +    reopened = DiskManager.open(tmp_path)
    +
    +    assert reopened.read_page(key) == page
    +    assert reopened.page_count(relation) == 1
    +    reopened.close()
    +
    +
    +def test_disk_manager_rejects_short_relation_files(tmp_path: Path) -> None:
    +    relation = heap_relation(1)
    +    path = relation_path(tmp_path, relation)
    +    path.parent.mkdir(parents=True)
    +    path.write_bytes(b"partial")
    +
    +    with pytest.raises(CorruptPage, match="multiple of"):
    +        DiskManager.open(tmp_path).page_count(relation)
    +
    +
    +def test_disk_manager_validates_page_identity_before_write(tmp_path: Path) -> None:
    +    manager = DiskManager.open(tmp_path)
    +    relation = heap_relation(1)
    +    first = manager.allocate_page(relation)
    +    wrong = encode_page(
    +        manager.allocate_page(relation),
    +        PageKind.HEAP,
    +        0,
    +        b"wrong page",
    +    )
    +
    +    with pytest.raises(CorruptPage, match="identity"):
    +        manager.write_page(first, wrong)
    +    assert relation_path(tmp_path, relation).stat().st_size == 2 * PAGE_SIZE
    +
    +
    +def test_disk_manager_close_is_idempotent_and_blocks_new_io(
    +    tmp_path: Path,
    +) -> None:
    +    manager = DiskManager.open(tmp_path)
    +    manager.close()
    +    manager.close()
    +
    +    with pytest.raises(DatabaseClosed):
    +        manager.page_count(heap_relation(1))
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert frame.key is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/storage/test_free_space.py"
    ```diff
    diff --git a/tests/unit/storage/test_free_space.py b/tests/unit/storage/test_free_space.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..72de6fae9d1ca5df7115a1e46dde1d721673d908
    --- /dev/null
    +++ b/tests/unit/storage/test_free_space.py
    @@ -0,0 +1,36 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +from minipostgres.storage.free_space import FreeSpaceMap
    +
    +
    +def test_free_space_map_persists_categories_and_orders_candidates(
    +    tmp_path: Path,
    +) -> None:
    +    path = tmp_path / "table-1.fsm"
    +    free_space = FreeSpaceMap.open(path, maximum_free_bytes=1_000)
    +    free_space.record(page_id=0, free_bytes=100)
    +    free_space.record(page_id=1, free_bytes=800)
    +    free_space.record(page_id=2, free_bytes=500)
    +
    +    reopened = FreeSpaceMap.open(path, maximum_free_bytes=1_000)
    +
    +    assert reopened.candidate_pages(required_bytes=400) == (1, 2)
    +    assert reopened.candidate_pages(required_bytes=900) == ()
    +
    +
    +def test_free_space_map_repairs_and_extends_sparse_page_entries(
    +    tmp_path: Path,
    +) -> None:
    +    free_space = FreeSpaceMap.open(
    +        tmp_path / "table-1.fsm",
    +        maximum_free_bytes=1_000,
    +    )
    +
    +    free_space.record(page_id=4, free_bytes=1_000)
    +    free_space.record(page_id=4, free_bytes=0)
    +
    +    assert free_space.page_count == 5
    +    assert 4 not in free_space.candidate_pages(required_bytes=1)
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert frame.key is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/storage/test_page_guard.py"
    ```diff
    diff --git a/tests/unit/storage/test_page_guard.py b/tests/unit/storage/test_page_guard.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..8b2e8a25e3ae54fc6346977cfb0bcd24df7ef493
    --- /dev/null
    +++ b/tests/unit/storage/test_page_guard.py
    @@ -0,0 +1,56 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +import pytest
    +
    +from minipostgres.errors import DatabaseClosed
    +from minipostgres.storage.buffer import BufferPool
    +from minipostgres.storage.constants import PageKind
    +from minipostgres.storage.disk import DiskManager
    +from minipostgres.storage.identifiers import heap_relation
    +from minipostgres.storage.page import decode_page, encode_page
    +
    +
    +def test_page_guard_unpins_and_records_dirty_lsn(tmp_path: Path) -> None:
    +    disk = DiskManager.open(tmp_path)
    +    key = disk.allocate_page(heap_relation(1))
    +    pool = BufferPool(disk, frame_count=1, wal_flush_gate=lambda _lsn: None)
    +
    +    with pool.fetch_page(key) as guard:
    +        guard.replace_bytes(encode_page(key, PageKind.HEAP, 0, b"changed"))
    +        guard.mark_dirty(page_lsn=17)
    +        assert pool.pin_count(key) == 1
    +        assert decode_page(key, guard.page_bytes).page_lsn == 17
    +
    +    assert pool.pin_count(key) == 0
    +    assert pool.frame(key).page_lsn == 17
    +    assert pool.frame(key).dirty is True
    +
    +
    +def test_page_guard_release_is_idempotent_and_blocks_late_mutation(
    +    tmp_path: Path,
    +) -> None:
    +    disk = DiskManager.open(tmp_path)
    +    key = disk.allocate_page(heap_relation(1))
    +    pool = BufferPool(disk, frame_count=1)
    +    guard = pool.fetch_page(key)
    +
    +    guard.release()
    +    guard.release()
    +
    +    assert pool.pin_count(key) == 0
    +    with pytest.raises(DatabaseClosed, match="guard"):
    +        guard.mark_dirty(0)
    +
    +
    +def test_page_guard_rejects_decreasing_lsn(tmp_path: Path) -> None:
    +    disk = DiskManager.open(tmp_path)
    +    key = disk.allocate_page(heap_relation(1))
    +    pool = BufferPool(disk, frame_count=1, wal_flush_gate=lambda _lsn: None)
    +
    +    with pool.fetch_page(key) as guard:
    +        guard.mark_dirty(11)
    +        with pytest.raises(ValueError, match="decrease"):
    +            guard.mark_dirty(10)
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert frame.key is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/storage/test_slotted_page.py"
    ```diff
    diff --git a/tests/unit/storage/test_slotted_page.py b/tests/unit/storage/test_slotted_page.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..0344d5fb312e9a2037f68ee451e2e849fea2f73e
    --- /dev/null
    +++ b/tests/unit/storage/test_slotted_page.py
    @@ -0,0 +1,64 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.errors import CorruptPage
    +from minipostgres.storage.slotted import SlottedPage
    +
    +
    +def test_compaction_moves_bytes_without_renumbering_live_slots() -> None:
    +    page = SlottedPage.empty(page_id=0)
    +    first = page.insert(b"a" * 100)
    +    second = page.insert(b"b" * 100)
    +    third = page.insert(b"c" * 100)
    +
    +    page.delete(second)
    +    page.compact()
    +
    +    assert (first, third) == (0, 2)
    +    assert page.read(first) == b"a" * 100
    +    assert page.read(third) == b"c" * 100
    +    assert page.live_slots() == (0, 2)
    +
    +
    +def test_insertion_reuses_a_dead_slot_without_changing_other_slot_ids() -> None:
    +    page = SlottedPage.empty(page_id=4)
    +    first = page.insert(b"first")
    +    deleted = page.insert(b"deleted")
    +    third = page.insert(b"third")
    +    page.delete(deleted)
    +
    +    reused = page.insert(b"replacement")
    +
    +    assert reused == deleted
    +    assert (first, third) == (0, 2)
    +    assert page.read(reused) == b"replacement"
    +
    +
    +def test_slotted_body_round_trip_preserves_dead_and_live_slots() -> None:
    +    page = SlottedPage.empty(page_id=8)
    +    page.insert(b"first")
    +    deleted = page.insert(b"deleted")
    +    page.insert(b"third")
    +    page.delete(deleted)
    +
    +    restored = SlottedPage.from_body(page_id=8, body=page.to_body())
    +
    +    assert restored.live_slots() == (0, 2)
    +    assert restored.read(0) == b"first"
    +    assert restored.read(2) == b"third"
    +    with pytest.raises(KeyError):
    +        restored.read(1)
    +
    +
    +def test_slotted_body_decoder_rejects_overlapping_extents() -> None:
    +    page = SlottedPage.empty(page_id=0)
    +    page.insert(b"first")
    +    page.insert(b"second")
    +    encoded = bytearray(page.to_body())
    +
    +    # Copy slot zero's extent descriptor over slot one.
    +    encoded[20:28] = encoded[12:20]
    +
    +    with pytest.raises(CorruptPage, match="overlap"):
    +        SlottedPage.from_body(page_id=0, body=bytes(encoded))
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert frame.key is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/storage/test_tuple_codec.py"
    ```diff
    diff --git a/tests/unit/storage/test_tuple_codec.py b/tests/unit/storage/test_tuple_codec.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..e926901536a9f2201a37e6083b5e0d00b748d59c
    --- /dev/null
    +++ b/tests/unit/storage/test_tuple_codec.py
    @@ -0,0 +1,85 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.catalog.model import Column, Schema
    +from minipostgres.errors import CorruptPage, RowTooLarge
    +from minipostgres.row import TID
    +from minipostgres.storage.tuple import SYSTEM_XID, TupleCodec, TupleVersion
    +from minipostgres.types import DataType
    +
    +
    +@pytest.fixture
    +def schema() -> Schema:
    +    return Schema.create(
    +        (
    +            Column("id", DataType.INT64, nullable=False),
    +            Column("score", DataType.FLOAT64),
    +            Column("active", DataType.BOOLEAN),
    +            Column("name", DataType.TEXT),
    +            Column("note", DataType.TEXT),
    +        )
    +    )
    +
    +
    +def test_tuple_codec_preserves_nulls_unicode_and_version_header(
    +    schema: Schema,
    +) -> None:
    +    version = TupleVersion(
    +        xmin=SYSTEM_XID,
    +        xmax=9,
    +        next_tid=TID(7, 3),
    +        values=(7, 1.5, True, "雪", None),
    +    )
    +
    +    encoded = TupleCodec(schema).encode(version)
    +
    +    assert TupleCodec(schema).decode(encoded) == version
    +
    +
    +def test_tuple_codec_rejects_wrong_schema_and_truncated_payload(
    +    schema: Schema,
    +) -> None:
    +    encoded = TupleCodec(schema).encode(
    +        TupleVersion(SYSTEM_XID, 0, None, (7, 1.5, False, "Ada", None))
    +    )
    +    other_schema = Schema.create(
    +        (
    +            Column("id", DataType.INT64, nullable=False),
    +            Column("score", DataType.FLOAT64),
    +            Column("active", DataType.BOOLEAN),
    +            Column("renamed", DataType.TEXT),
    +            Column("note", DataType.TEXT),
    +        )
    +    )
    +
    +    with pytest.raises(CorruptPage, match="schema"):
    +        TupleCodec(other_schema).decode(encoded)
    +    with pytest.raises(CorruptPage, match=r"truncated|length"):
    +        TupleCodec(schema).decode(encoded[:-1])
    +
    +
    +def test_tuple_codec_rejects_invalid_boolean_and_trailing_bytes(
    +    schema: Schema,
    +) -> None:
    +    encoded = bytearray(
    +        TupleCodec(schema).encode(
    +            TupleVersion(SYSTEM_XID, 0, None, (7, 1.5, True, "Ada", None))
    +        )
    +    )
    +    # Fixed header (44), one-byte null bitmap, INT64, FLOAT64, then BOOLEAN.
    +    encoded[61] = 2
    +
    +    with pytest.raises(CorruptPage, match="boolean"):
    +        TupleCodec(schema).decode(bytes(encoded))
    +    with pytest.raises(CorruptPage, match="length"):
    +        TupleCodec(schema).decode(bytes(encoded) + b"\x00")
    +
    +
    +def test_tuple_codec_rejects_a_value_larger_than_one_slot(schema: Schema) -> None:
    +    huge = "x" * 9_000
    +
    +    with pytest.raises(RowTooLarge):
    +        TupleCodec(schema).encode(
    +            TupleVersion(SYSTEM_XID, 0, None, (7, 1.5, True, huge, None))
    +        )
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert frame.key is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is persistent heap files. Pages, slots, tuple bytes, disk IO, replacement, and buffer ownership must compose into stable row locations.

### Why this mechanism is necessary

Pages, slots, tuple bytes, disk IO, replacement, and buffer ownership must compose into stable row locations. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Pinned dirty pages reach disk through owned guards, and tuple IDs remain stable across restart.

### Mechanism blocks

#### Persistent heap files mechanism

Pinned dirty pages reach disk through owned guards, and tuple IDs remain stable across restart.

??? note "File diff: src/minipostgres/errors.py"
    ```diff
    diff --git a/src/minipostgres/errors.py b/src/minipostgres/errors.py
    index c62d4ca2570ef52330276d1ffb92ea27aacaa9b5..7c8d894356a3148061f0129df73997bc22b61ccc 100644
    --- a/src/minipostgres/errors.py
    +++ b/src/minipostgres/errors.py
    @@ -43,6 +43,14 @@ class RowTooLarge(MiniPostgresError):
         """A tuple cannot fit in one heap page."""


    +class PageFull(MiniPostgresError):
    +    """A page cannot fit a requested tuple or index entry."""
    +
    +
    +class BufferPoolFull(MiniPostgresError):
    +    """Every buffer frame is pinned and no page can be admitted."""
    +
    +
     class CorruptPage(MiniPostgresError):
         """A page failed structural or checksum validation."""

    @@ -57,4 +65,3 @@ class CatalogError(MiniPostgresError):

     class DatabaseClosed(MiniPostgresError):
         """An operation was attempted on a closed database."""
    -
    ```

??? note "File diff: src/minipostgres/storage/buffer.py"
    ```diff
    diff --git a/src/minipostgres/storage/buffer.py b/src/minipostgres/storage/buffer.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..32833202c80266429801498a44257d2a81fb65e7
    --- /dev/null
    +++ b/src/minipostgres/storage/buffer.py
    @@ -0,0 +1,335 @@
    +"""Pinned fixed-frame page cache with WAL-before-data flush ordering."""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Callable
    +from dataclasses import dataclass
    +from pathlib import Path
    +from threading import RLock
    +from types import TracebackType
    +from typing import Protocol, runtime_checkable
    +
    +from minipostgres.errors import BufferPoolFull, DatabaseClosed
    +from minipostgres.storage.constants import PageKind
    +from minipostgres.storage.identifiers import PageKey, RelationId
    +from minipostgres.storage.page import decode_page, encode_page
    +from minipostgres.storage.replacer import ClockReplacer
    +
    +
    +class PageDisk(Protocol):
    +    """The page I/O surface required by the buffer pool."""
    +
    +    def read_page(self, key: PageKey) -> bytes: ...
    +
    +    def write_page(self, key: PageKey, encoded: bytes) -> None: ...
    +
    +
    +@runtime_checkable
    +class AllocatingPageDisk(PageDisk, Protocol):
    +    """Page disk extension used by ``new_page``."""
    +
    +    def allocate_page(
    +        self,
    +        relation: RelationId,
    +        kind: PageKind | None = None,
    +    ) -> PageKey: ...
    +
    +
    +@runtime_checkable
    +class CountingPageDisk(PageDisk, Protocol):
    +    """Page disk extension used to inspect relation length."""
    +
    +    def page_count(self, relation: RelationId) -> int: ...
    +
    +
    +@runtime_checkable
    +class RootedPageDisk(PageDisk, Protocol):
    +    """Page disk extension exposing the database storage root."""
    +
    +    root: Path
    +
    +
    +@dataclass(slots=True)
    +class _Frame:
    +    frame_id: int
    +    key: PageKey | None = None
    +    page_bytes: bytes = b""
    +    page_lsn: int = 0
    +    pin_count: int = 0
    +    dirty: bool = False
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class FrameSnapshot:
    +    """Read-only diagnostic view of one resident frame."""
    +
    +    frame_id: int
    +    key: PageKey
    +    page_lsn: int
    +    pin_count: int
    +    dirty: bool
    +
    +
    +def _no_wal_yet(page_lsn: int) -> None:
    +    if page_lsn != 0:
    +        raise RuntimeError(
    +            "nonzero page LSN cannot flush before WAL is implemented"
    +        )
    +
    +
    +class BufferPool:
    +    """Mediate all normal relation-page reads, writes, pins, and eviction."""
    +
    +    def __init__(
    +        self,
    +        disk: PageDisk,
    +        frame_count: int,
    +        *,
    +        wal_flush_gate: Callable[[int], None] | None = None,
    +    ) -> None:
    +        if type(frame_count) is not int or frame_count <= 0:
    +            raise ValueError("frame_count must be a positive integer")
    +        self._disk = disk
    +        self._frames = [_Frame(frame_id) for frame_id in range(frame_count)]
    +        self._page_table: dict[PageKey, int] = {}
    +        self._free_frames = list(range(frame_count))
    +        self._clock = ClockReplacer(frame_count)
    +        self._wal_flush_gate = wal_flush_gate or _no_wal_yet
    +        self._lock = RLock()
    +
    +    @property
    +    def resident_page_count(self) -> int:
    +        with self._lock:
    +            return len(self._page_table)
    +
    +    @property
    +    def storage_root(self) -> Path:
    +        """Return the database root required by persistent sidecars."""
    +
    +        if not isinstance(self._disk, RootedPageDisk):
    +            raise TypeError("configured page disk does not expose a storage root")
    +        return self._disk.root
    +
    +    def page_count(self, relation: RelationId) -> int:
    +        """Return the number of allocated pages in a physical relation."""
    +
    +        if not isinstance(self._disk, CountingPageDisk):
    +            raise TypeError("configured page disk cannot count relation pages")
    +        return self._disk.page_count(relation)
    +
    +    def fetch_page(self, key: PageKey) -> PageGuard:
    +        """Pin a resident page or load it into a free/evictable frame."""
    +
    +        with self._lock:
    +            resident = self._page_table.get(key)
    +            if resident is not None:
    +                frame = self._frames[resident]
    +                frame.pin_count += 1
    +                self._clock.mark_evictable(resident, False)
    +                self._clock.record_access(resident)
    +                return PageGuard(self, resident, key)
    +
    +            frame_id, from_free_list = self._select_frame()
    +            frame = self._frames[frame_id]
    +            try:
    +                if frame.key is not None:
    +                    self._flush_frame(frame)
    +                page_bytes = self._disk.read_page(key)
    +                decoded = decode_page(key, page_bytes)
    +            except BaseException:
    +                if from_free_list:
    +                    self._free_frames.insert(0, frame_id)
    +                else:
    +                    self._clock.mark_evictable(frame_id, True)
    +                raise
    +
    +            if frame.key is not None:
    +                del self._page_table[frame.key]
    +            frame.key = key
    +            frame.page_bytes = page_bytes
    +            frame.page_lsn = decoded.page_lsn
    +            frame.pin_count = 1
    +            frame.dirty = False
    +            self._page_table[key] = frame_id
    +            self._clock.record_access(frame_id)
    +            self._clock.mark_evictable(frame_id, False)
    +            return PageGuard(self, frame_id, key)
    +
    +    def new_page(
    +        self,
    +        relation: RelationId,
    +        kind: PageKind | None = None,
    +    ) -> PageGuard:
    +        """Allocate and immediately pin a new physical page."""
    +
    +        if not isinstance(self._disk, AllocatingPageDisk):
    +            raise TypeError("configured page disk does not support allocation")
    +        key = self._disk.allocate_page(relation, kind)
    +        return self.fetch_page(key)
    +
    +    def pin_count(self, key: PageKey) -> int:
    +        with self._lock:
    +            return self._resident_frame(key).pin_count
    +
    +    def frame(self, key: PageKey) -> FrameSnapshot:
    +        """Return an immutable diagnostic snapshot for tests and metrics."""
    +
    +        with self._lock:
    +            frame = self._resident_frame(key)
    +            assert frame.key is not None
    +            return FrameSnapshot(
    +                frame.frame_id,
    +                frame.key,
    +                frame.page_lsn,
    +                frame.pin_count,
    +                frame.dirty,
    +            )
    +
    +    def flush_page(self, key: PageKey) -> None:
    +        """Flush one dirty resident page after satisfying the WAL gate."""
    +
    +        with self._lock:
    +            self._flush_frame(self._resident_frame(key))
    +
    +    def flush_all(self) -> None:
    +        """Flush all dirty frames in deterministic frame order."""
    +
    +        with self._lock:
    +            for frame in self._frames:
    +                if frame.key is not None:
    +                    self._flush_frame(frame)
    +
    +    def _select_frame(self) -> tuple[int, bool]:
    +        if self._free_frames:
    +            return self._free_frames.pop(0), True
    +        victim = self._clock.evict()
    +        if victim is None:
    +            raise BufferPoolFull("all buffer frames are pinned")
    +        return victim, False
    +
    +    def _resident_frame(self, key: PageKey) -> _Frame:
    +        frame_id = self._page_table.get(key)
    +        if frame_id is None:
    +            raise KeyError(f"page is not resident: {key}")
    +        return self._frames[frame_id]
    +
    +    def _flush_frame(self, frame: _Frame) -> None:
    +        if not frame.dirty:
    +            return
    +        assert frame.key is not None
    +        self._wal_flush_gate(frame.page_lsn)
    +        self._disk.write_page(frame.key, frame.page_bytes)
    +        frame.dirty = False
    +
    +    def guard_page_bytes(self, frame_id: int, key: PageKey) -> bytes:
    +        """Return bytes while a matching guard owns a live pin."""
    +
    +        with self._lock:
    +            frame = self._guarded_frame(frame_id, key)
    +            return frame.page_bytes
    +
    +    def guard_replace_bytes(
    +        self,
    +        frame_id: int,
    +        key: PageKey,
    +        page_bytes: bytes,
    +    ) -> None:
    +        """Replace bytes while a matching guard owns a live pin."""
    +
    +        with self._lock:
    +            frame = self._guarded_frame(frame_id, key)
    +            decoded = decode_page(key, page_bytes)
    +            if decoded.page_lsn < frame.page_lsn:
    +                raise ValueError("page replacement cannot decrease its LSN")
    +            frame.page_bytes = page_bytes
    +            frame.page_lsn = decoded.page_lsn
    +
    +    def guard_mark_dirty(
    +        self,
    +        frame_id: int,
    +        key: PageKey,
    +        page_lsn: int,
    +    ) -> None:
    +        """Mark a guarded frame dirty at a nondecreasing LSN."""
    +
    +        with self._lock:
    +            frame = self._guarded_frame(frame_id, key)
    +            if page_lsn < frame.page_lsn:
    +                raise ValueError("dirty page LSN cannot decrease")
    +            decoded = decode_page(key, frame.page_bytes)
    +            frame.page_bytes = encode_page(
    +                key,
    +                decoded.kind,
    +                page_lsn,
    +                decoded.body,
    +            )
    +            frame.page_lsn = page_lsn
    +            frame.dirty = True
    +
    +    def release_guard(self, frame_id: int, key: PageKey) -> None:
    +        """Release one pin owned by a matching page guard."""
    +
    +        with self._lock:
    +            frame = self._guarded_frame(frame_id, key)
    +            if frame.pin_count <= 0:
    +                raise RuntimeError("buffer frame pin count underflow")
    +            frame.pin_count -= 1
    +            if frame.pin_count == 0:
    +                self._clock.mark_evictable(frame_id, True)
    +
    +    def _guarded_frame(self, frame_id: int, key: PageKey) -> _Frame:
    +        frame = self._frames[frame_id]
    +        if frame.key != key or frame.pin_count <= 0:
    +            raise DatabaseClosed("page guard no longer owns a pinned frame")
    +        return frame
    +
    +
    +class PageGuard:
    +    """RAII-style ownership of exactly one buffer-frame pin."""
    +
    +    def __init__(self, pool: BufferPool, frame_id: int, key: PageKey) -> None:
    +        self._pool = pool
    +        self._frame_id = frame_id
    +        self.key = key
    +        self._released = False
    +
    +    def __enter__(self) -> PageGuard:
    +        self._ensure_active()
    +        return self
    +
    +    def __exit__(
    +        self,
    +        exc_type: type[BaseException] | None,
    +        exc_value: BaseException | None,
    +        traceback: TracebackType | None,
    +    ) -> None:
    +        self.release()
    +
    +    @property
    +    def page_bytes(self) -> bytes:
    +        self._ensure_active()
    +        return self._pool.guard_page_bytes(self._frame_id, self.key)
    +
    +    def replace_bytes(self, page_bytes: bytes) -> None:
    +        """Replace the complete checksummed page held by this guard."""
    +
    +        self._ensure_active()
    +        self._pool.guard_replace_bytes(self._frame_id, self.key, page_bytes)
    +
    +    def mark_dirty(self, page_lsn: int) -> None:
    +        """Mark changed bytes dirty at a nondecreasing page LSN."""
    +
    +        self._ensure_active()
    +        self._pool.guard_mark_dirty(self._frame_id, self.key, page_lsn)
    +
    +    def release(self) -> None:
    +        """Release this guard's pin exactly once."""
    +
    +        if self._released:
    +            return
    +        self._pool.release_guard(self._frame_id, self.key)
    +        self._released = True
    +
    +    def _ensure_active(self) -> None:
    +        if self._released:
    +            raise DatabaseClosed("page guard has been released")
    ```

??? note "File diff: src/minipostgres/storage/constants.py"
    ```diff
    diff --git a/src/minipostgres/storage/constants.py b/src/minipostgres/storage/constants.py
    index 4db89adf1fa79fa7b582e223e3567145604f3266..9ab59c469b91670411b53bcf73dc17109c826ecb 100644
    --- a/src/minipostgres/storage/constants.py
    +++ b/src/minipostgres/storage/constants.py
    @@ -7,6 +7,8 @@ from enum import IntEnum
     PAGE_SIZE = 8192
     PAGE_MAGIC = b"MPG1"
     PAGE_FORMAT_VERSION = 1
    +PAGE_HEADER_SIZE = 44
    +PAGE_BODY_SIZE = PAGE_SIZE - PAGE_HEADER_SIZE


     class PageKind(IntEnum):
    @@ -16,4 +18,3 @@ class PageKind(IntEnum):
         BTREE_META = 2
         BTREE_INTERNAL = 3
         BTREE_LEAF = 4
    -
    ```

??? note "File diff: src/minipostgres/storage/disk.py"
    ```diff
    diff --git a/src/minipostgres/storage/disk.py b/src/minipostgres/storage/disk.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..83566a88b7911ffc8098396d3394bdd61e698aa7
    --- /dev/null
    +++ b/src/minipostgres/storage/disk.py
    @@ -0,0 +1,164 @@
    +"""Fixed-page relation-file I/O for heap and B+Tree forks."""
    +
    +from __future__ import annotations
    +
    +import os
    +from pathlib import Path
    +from types import TracebackType
    +
    +from minipostgres.errors import CorruptPage, DatabaseClosed
    +from minipostgres.storage.constants import PAGE_SIZE, PageKind
    +from minipostgres.storage.identifiers import ForkKind, PageKey, RelationId
    +from minipostgres.storage.page import decode_page, encode_page
    +
    +
    +def relation_path(root: Path, relation: RelationId) -> Path:
    +    """Return the stable on-disk path for one physical relation."""
    +
    +    if relation.fork is ForkKind.HEAP:
    +        return root / "relations" / f"table-{relation.object_id}.heap"
    +    return root / "indexes" / f"index-{relation.object_id}.btree"
    +
    +
    +class DiskManager:
    +    """Own relation descriptors and exact fixed-size page I/O."""
    +
    +    def __init__(self, root: Path) -> None:
    +        self.root = root
    +        self._descriptors: dict[RelationId, int] = {}
    +        self._closed = False
    +
    +    @classmethod
    +    def open(cls, root: Path) -> DiskManager:
    +        """Open a database storage root, creating fork directories as needed."""
    +
    +        root = Path(root)
    +        root.mkdir(parents=True, exist_ok=True)
    +        (root / "relations").mkdir(exist_ok=True)
    +        (root / "indexes").mkdir(exist_ok=True)
    +        return cls(root)
    +
    +    def __enter__(self) -> DiskManager:
    +        self._ensure_open()
    +        return self
    +
    +    def __exit__(
    +        self,
    +        exc_type: type[BaseException] | None,
    +        exc_value: BaseException | None,
    +        traceback: TracebackType | None,
    +    ) -> None:
    +        self.close()
    +
    +    def page_count(self, relation: RelationId) -> int:
    +        """Return the number of complete physical pages in a relation."""
    +
    +        descriptor = self._descriptor(relation)
    +        size = os.fstat(descriptor).st_size
    +        if size % PAGE_SIZE:
    +            raise CorruptPage(
    +                f"relation size {size} is not a multiple of page size {PAGE_SIZE}"
    +            )
    +        return size // PAGE_SIZE
    +
    +    def allocate_page(
    +        self,
    +        relation: RelationId,
    +        kind: PageKind | None = None,
    +    ) -> PageKey:
    +        """Append one valid empty page and return its stable identity."""
    +
    +        page_id = self.page_count(relation)
    +        key = PageKey(relation, page_id)
    +        if kind is None:
    +            kind = (
    +                PageKind.HEAP
    +                if relation.fork is ForkKind.HEAP
    +                else PageKind.BTREE_LEAF
    +            )
    +        encoded = encode_page(key, kind, page_lsn=0, body=b"")
    +        self._pwrite_exact(self._descriptor(relation), encoded, page_id * PAGE_SIZE)
    +        return key
    +
    +    def read_page(self, key: PageKey) -> bytes:
    +        """Read one exact page and validate its checksum and identity."""
    +
    +        descriptor = self._descriptor(key.relation)
    +        encoded = self._pread_exact(descriptor, PAGE_SIZE, key.page_id * PAGE_SIZE)
    +        decode_page(key, encoded)
    +        return encoded
    +
    +    def write_page(self, key: PageKey, encoded: bytes) -> None:
    +        """Validate and overwrite one already allocated physical page."""
    +
    +        decode_page(key, encoded)
    +        if key.page_id >= self.page_count(key.relation):
    +            raise CorruptPage(f"page {key.page_id} is not allocated")
    +        self._pwrite_exact(
    +            self._descriptor(key.relation),
    +            encoded,
    +            key.page_id * PAGE_SIZE,
    +        )
    +
    +    def sync_relation(self, relation: RelationId) -> None:
    +        """Make prior writes to one relation durable."""
    +
    +        os.fsync(self._descriptor(relation))
    +
    +    def close(self) -> None:
    +        """Close every cached descriptor; repeated close is harmless."""
    +
    +        if self._closed:
    +            return
    +        self._closed = True
    +        descriptors = tuple(self._descriptors.values())
    +        self._descriptors.clear()
    +        for descriptor in descriptors:
    +            os.close(descriptor)
    +
    +    def _ensure_open(self) -> None:
    +        if self._closed:
    +            raise DatabaseClosed("disk manager is closed")
    +
    +    def _descriptor(self, relation: RelationId) -> int:
    +        self._ensure_open()
    +        descriptor = self._descriptors.get(relation)
    +        if descriptor is not None:
    +            return descriptor
    +        path = relation_path(self.root, relation)
    +        created = not path.exists()
    +        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    +        self._descriptors[relation] = descriptor
    +        if created:
    +            directory = os.open(path.parent, os.O_RDONLY)
    +            try:
    +                os.fsync(directory)
    +            finally:
    +                os.close(directory)
    +        return descriptor
    +
    +    @staticmethod
    +    def _pread_exact(descriptor: int, size: int, offset: int) -> bytes:
    +        chunks: list[bytes] = []
    +        remaining = size
    +        while remaining:
    +            chunk = os.pread(descriptor, remaining, offset + size - remaining)
    +            if not chunk:
    +                actual = size - remaining
    +                raise CorruptPage(
    +                    f"short page read: expected {size} bytes, got {actual}"
    +                )
    +            chunks.append(chunk)
    +            remaining -= len(chunk)
    +        return b"".join(chunks)
    +
    +    @staticmethod
    +    def _pwrite_exact(descriptor: int, data: bytes, offset: int) -> None:
    +        written = 0
    +        while written < len(data):
    +            count = os.pwrite(descriptor, data[written:], offset + written)
    +            if count <= 0:
    +                raise OSError(
    +                    f"short page write: expected {len(data)} bytes, got {written}"
    +                )
    +            written += count
    ```

??? note "File diff: src/minipostgres/storage/free_space.py"
    ```diff
    diff --git a/src/minipostgres/storage/free_space.py b/src/minipostgres/storage/free_space.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..a122e2f230e3dea3a2c1b30331eb772fb5e0d6a6
    --- /dev/null
    +++ b/src/minipostgres/storage/free_space.py
    @@ -0,0 +1,99 @@
    +"""Approximate, atomically replaced free-space sidecar for one heap."""
    +
    +from __future__ import annotations
    +
    +import os
    +from pathlib import Path
    +
    +
    +class FreeSpaceMap:
    +    """Store one conservative byte category per heap page."""
    +
    +    def __init__(
    +        self,
    +        path: Path,
    +        maximum_free_bytes: int,
    +        categories: bytearray,
    +    ) -> None:
    +        if maximum_free_bytes <= 0:
    +            raise ValueError("maximum_free_bytes must be positive")
    +        self.path = path
    +        self.maximum_free_bytes = maximum_free_bytes
    +        self._categories = categories
    +
    +    @classmethod
    +    def open(
    +        cls,
    +        path: Path,
    +        *,
    +        maximum_free_bytes: int,
    +    ) -> FreeSpaceMap:
    +        """Load an existing sidecar or create an empty in-memory map."""
    +
    +        path = Path(path)
    +        categories = bytearray(path.read_bytes()) if path.exists() else bytearray()
    +        return cls(path, maximum_free_bytes, categories)
    +
    +    @property
    +    def page_count(self) -> int:
    +        return len(self._categories)
    +
    +    def record(self, page_id: int, free_bytes: int) -> None:
    +        """Record an estimate and atomically publish the updated sidecar."""
    +
    +        if type(page_id) is not int or page_id < 0:
    +            raise ValueError("page_id must be a non-negative integer")
    +        if (
    +            type(free_bytes) is not int
    +            or free_bytes < 0
    +            or free_bytes > self.maximum_free_bytes
    +        ):
    +            raise ValueError("free_bytes is outside the configured page capacity")
    +        while len(self._categories) <= page_id:
    +            self._categories.append(0)
    +        self._categories[page_id] = self._category(free_bytes)
    +        self._persist()
    +
    +    def candidate_pages(self, required_bytes: int) -> tuple[int, ...]:
    +        """Return possible fits ordered from most to least estimated space."""
    +
    +        if type(required_bytes) is not int or required_bytes < 0:
    +            raise ValueError("required_bytes must be non-negative")
    +        if required_bytes > self.maximum_free_bytes:
    +            return ()
    +        required_category = self._category(required_bytes)
    +        candidates = (
    +            (category, page_id)
    +            for page_id, category in enumerate(self._categories)
    +            if category >= required_category
    +        )
    +        return tuple(
    +            page_id
    +            for _, page_id in sorted(
    +                candidates,
    +                key=lambda item: (-item[0], item[1]),
    +            )
    +        )
    +
    +    def _category(self, free_bytes: int) -> int:
    +        if free_bytes == 0:
    +            return 0
    +        return min(
    +            255,
    +            (free_bytes * 255 + self.maximum_free_bytes - 1)
    +            // self.maximum_free_bytes,
    +        )
    +
    +    def _persist(self) -> None:
    +        self.path.parent.mkdir(parents=True, exist_ok=True)
    +        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
    +        with temporary.open("wb") as stream:
    +            stream.write(self._categories)
    +            stream.flush()
    +            os.fsync(stream.fileno())
    +        os.replace(temporary, self.path)
    +        directory = os.open(self.path.parent, os.O_RDONLY)
    +        try:
    +            os.fsync(directory)
    +        finally:
    +            os.close(directory)
    ```

??? note "File diff: src/minipostgres/storage/heap.py"
    ```diff
    diff --git a/src/minipostgres/storage/heap.py b/src/minipostgres/storage/heap.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..2dde750c9da4bfaa8198bfe27f08f812814aa0f6
    --- /dev/null
    +++ b/src/minipostgres/storage/heap.py
    @@ -0,0 +1,195 @@
    +"""Persistent heap-table access over slotted pages and tuple versions."""
    +
    +from __future__ import annotations
    +
    +import threading
    +from collections.abc import Iterator
    +
    +from minipostgres.catalog.model import TableMetadata
    +from minipostgres.errors import CorruptPage, PageFull
    +from minipostgres.row import TID
    +from minipostgres.storage.buffer import BufferPool, PageGuard
    +from minipostgres.storage.constants import PAGE_BODY_SIZE, PageKind
    +from minipostgres.storage.free_space import FreeSpaceMap
    +from minipostgres.storage.identifiers import heap_page_key, heap_relation
    +from minipostgres.storage.page import decode_page, encode_page
    +from minipostgres.storage.slotted import SLOT_ENTRY_SIZE, SlottedPage
    +from minipostgres.storage.tuple import SYSTEM_XID, TupleCodec, TupleVersion
    +from minipostgres.types import Scalar
    +
    +
    +class HeapTable:
    +    """TableAccess implementation backed by stable physical heap TIDs."""
    +
    +    def __init__(
    +        self,
    +        buffer_pool: BufferPool,
    +        metadata: TableMetadata,
    +        free_space: FreeSpaceMap,
    +    ) -> None:
    +        self._pool = buffer_pool
    +        self._metadata = metadata
    +        self.table_id = metadata.table_id
    +        self.schema = metadata.schema
    +        self.free_space = free_space
    +        self._relation = heap_relation(metadata.table_id)
    +        self._codec = TupleCodec(metadata.schema)
    +        self._lock = threading.RLock()
    +
    +    @classmethod
    +    def open(
    +        cls,
    +        buffer_pool: BufferPool,
    +        metadata: TableMetadata,
    +    ) -> HeapTable:
    +        """Open a heap and repair missing free-space entries from actual pages."""
    +
    +        free_space = FreeSpaceMap.open(
    +            buffer_pool.storage_root
    +            / "relations"
    +            / f"table-{metadata.table_id}.fsm",
    +            maximum_free_bytes=PAGE_BODY_SIZE,
    +        )
    +        heap = cls(buffer_pool, metadata, free_space)
    +        heap._bootstrap_free_space()
    +        return heap
    +
    +    def insert(self, values: tuple[Scalar, ...]) -> TID:
    +        """Insert one physical tuple, repairing stale free-space estimates."""
    +
    +        validated = self.schema.validate_row(values)
    +        encoded_tuple = self._codec.encode(
    +            TupleVersion(SYSTEM_XID, 0, None, validated)
    +        )
    +        required = len(encoded_tuple) + SLOT_ENTRY_SIZE
    +        with self._lock:
    +            for page_id in self.free_space.candidate_pages(required):
    +                tid = self._try_insert(page_id, encoded_tuple)
    +                if tid is not None:
    +                    return tid
    +            return self._insert_new_page(encoded_tuple)
    +
    +    def fetch(self, tid: TID) -> tuple[Scalar, ...] | None:
    +        """Fetch a live physical tuple by stable TID."""
    +
    +        with self._lock:
    +            if tid.page_id >= self._pool.page_count(self._relation):
    +                return None
    +            with self._pool.fetch_page(
    +                heap_page_key(self.table_id, tid.page_id)
    +            ) as guard:
    +                page = self._slotted_page(guard)
    +                try:
    +                    encoded = page.read(tid.slot_id)
    +                except KeyError:
    +                    return None
    +                return self._codec.decode(encoded).values
    +
    +    def scan(self) -> Iterator[tuple[TID, tuple[Scalar, ...]]]:
    +        """Return a page-order, slot-order snapshot of current live tuples."""
    +
    +        with self._lock:
    +            rows: list[tuple[TID, tuple[Scalar, ...]]] = []
    +            for page_id in range(self._pool.page_count(self._relation)):
    +                key = heap_page_key(self.table_id, page_id)
    +                with self._pool.fetch_page(key) as guard:
    +                    page = self._slotted_page(guard)
    +                    rows.extend(
    +                        (
    +                            TID(page_id, slot_id),
    +                            self._codec.decode(page.read(slot_id)).values,
    +                        )
    +                        for slot_id in page.live_slots()
    +                    )
    +            return iter(rows)
    +
    +    def replace(
    +        self,
    +        tid: TID,
    +        values: tuple[Scalar, ...],
    +    ) -> TID | None:
    +        """Insert a replacement tuple and retire the old physical slot."""
    +
    +        validated = self.schema.validate_row(values)
    +        with self._lock:
    +            if self.fetch(tid) is None:
    +                return None
    +            replacement = self.insert(validated)
    +            if not self.delete(tid):
    +                raise RuntimeError("heap tuple disappeared during serialized replace")
    +            return replacement
    +
    +    def delete(self, tid: TID) -> bool:
    +        """Mark one physical slot dead without renumbering other TIDs."""
    +
    +        with self._lock:
    +            if tid.page_id >= self._pool.page_count(self._relation):
    +                return False
    +            key = heap_page_key(self.table_id, tid.page_id)
    +            with self._pool.fetch_page(key) as guard:
    +                page = self._slotted_page(guard)
    +                try:
    +                    page.delete(tid.slot_id)
    +                except KeyError:
    +                    return False
    +                self._publish_page(guard, page)
    +                self.free_space.record(tid.page_id, page.contiguous_free_bytes)
    +                return True
    +
    +    def _try_insert(self, page_id: int, encoded_tuple: bytes) -> TID | None:
    +        if page_id >= self._pool.page_count(self._relation):
    +            raise CorruptPage("free-space map refers to an unallocated heap page")
    +        key = heap_page_key(self.table_id, page_id)
    +        with self._pool.fetch_page(key) as guard:
    +            page = self._slotted_page(guard)
    +            try:
    +                slot_id = page.insert(encoded_tuple)
    +            except PageFull:
    +                self.free_space.record(page_id, page.contiguous_free_bytes)
    +                return None
    +            self._publish_page(guard, page)
    +            self.free_space.record(page_id, page.contiguous_free_bytes)
    +            return TID(page_id, slot_id)
    +
    +    def _insert_new_page(self, encoded_tuple: bytes) -> TID:
    +        with self._pool.new_page(self._relation, PageKind.HEAP) as guard:
    +            page = SlottedPage.empty(guard.key.page_id)
    +            slot_id = page.insert(encoded_tuple)
    +            self._publish_page(guard, page)
    +            self.free_space.record(
    +                guard.key.page_id,
    +                page.contiguous_free_bytes,
    +            )
    +            return TID(guard.key.page_id, slot_id)
    +
    +    def _slotted_page(self, guard: PageGuard) -> SlottedPage:
    +        decoded = decode_page(guard.key, guard.page_bytes)
    +        if decoded.kind is not PageKind.HEAP:
    +            raise CorruptPage("heap relation contains a non-heap page")
    +        if not decoded.body:
    +            return SlottedPage.empty(guard.key.page_id)
    +        return SlottedPage.from_body(guard.key.page_id, decoded.body)
    +
    +    @staticmethod
    +    def _publish_page(guard: PageGuard, page: SlottedPage) -> None:
    +        guard.replace_bytes(
    +            encode_page(
    +                guard.key,
    +                PageKind.HEAP,
    +                page_lsn=0,
    +                body=page.to_body(),
    +            )
    +        )
    +        guard.mark_dirty(page_lsn=0)
    +
    +    def _bootstrap_free_space(self) -> None:
    +        page_count = self._pool.page_count(self._relation)
    +        if self.free_space.page_count > page_count:
    +            raise CorruptPage(
    +                "free-space map contains entries beyond the heap relation"
    +            )
    +        for page_id in range(self.free_space.page_count, page_count):
    +            key = heap_page_key(self.table_id, page_id)
    +            with self._pool.fetch_page(key) as guard:
    +                page = self._slotted_page(guard)
    +                self.free_space.record(page_id, page.contiguous_free_bytes)
    ```

??? note "File diff: src/minipostgres/storage/identifiers.py"
    ```diff
    diff --git a/src/minipostgres/storage/identifiers.py b/src/minipostgres/storage/identifiers.py
    index 1aa2cbf74bb1c797a9eb0532f2ae3458a10436b8..f99a5fb671553f01f25cebf2e97ebab7d2e738df 100644
    --- a/src/minipostgres/storage/identifiers.py
    +++ b/src/minipostgres/storage/identifiers.py
    @@ -42,13 +42,25 @@ class PageKey:
             _validate_uint64(self.page_id, "page_id")


    +def heap_relation(table_id: int) -> RelationId:
    +    """Build the canonical physical identity for a heap relation."""
    +
    +    return RelationId(ForkKind.HEAP, table_id)
    +
    +
    +def btree_relation(index_id: int) -> RelationId:
    +    """Build the canonical physical identity for a B+Tree relation."""
    +
    +    return RelationId(ForkKind.BTREE, index_id)
    +
    +
     def heap_page_key(table_id: int, page_id: int) -> PageKey:
         """Build the canonical page identity for a heap relation."""

    -    return PageKey(RelationId(ForkKind.HEAP, table_id), page_id)
    +    return PageKey(heap_relation(table_id), page_id)


     def btree_page_key(index_id: int, page_id: int) -> PageKey:
         """Build the canonical page identity for a B+Tree relation."""

    -    return PageKey(RelationId(ForkKind.BTREE, index_id), page_id)
    +    return PageKey(btree_relation(index_id), page_id)
    ```

??? note "File diff: src/minipostgres/storage/page.py"
    ```diff
    diff --git a/src/minipostgres/storage/page.py b/src/minipostgres/storage/page.py
    index 3d547f014f8b90f0c4f7b8e8af65a950a62134af..e96017a4d926db0dd7536fa15ee3f7e896954847 100644
    --- a/src/minipostgres/storage/page.py
    +++ b/src/minipostgres/storage/page.py
    @@ -9,6 +9,7 @@ from dataclasses import dataclass
     from minipostgres.errors import CorruptPage, RowTooLarge
     from minipostgres.storage.constants import (
         PAGE_FORMAT_VERSION,
    +    PAGE_HEADER_SIZE,
         PAGE_MAGIC,
         PAGE_SIZE,
         PageKind,
    @@ -22,6 +23,8 @@ _CHECKSUM_OFFSET = _HEADER.size - struct.calcsize(">I")
     _MAX_BODY_SIZE = PAGE_SIZE - _HEADER.size
     _MAX_UINT64 = 2**64 - 1

    +assert _HEADER.size == PAGE_HEADER_SIZE
    +

     @dataclass(frozen=True, slots=True)
     class DecodedPage:
    ```

??? note "File diff: src/minipostgres/storage/replacer.py"
    ```diff
    diff --git a/src/minipostgres/storage/replacer.py b/src/minipostgres/storage/replacer.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..38d3406b3c04273aa02bf1910757c2c5395703f8
    --- /dev/null
    +++ b/src/minipostgres/storage/replacer.py
    @@ -0,0 +1,49 @@
    +"""Deterministic Clock replacement for buffer-pool frames."""
    +
    +from __future__ import annotations
    +
    +
    +class ClockReplacer:
    +    """Select unpinned frames using reference-bit second chances."""
    +
    +    def __init__(self, frame_count: int) -> None:
    +        if type(frame_count) is not int or frame_count <= 0:
    +            raise ValueError("frame_count must be a positive integer")
    +        self._referenced = [False] * frame_count
    +        self._evictable = [False] * frame_count
    +        self._hand = 0
    +
    +    def record_access(self, frame_id: int) -> None:
    +        """Give a frame one second chance on a future Clock sweep."""
    +
    +        self._validate_frame_id(frame_id)
    +        self._referenced[frame_id] = True
    +
    +    def mark_evictable(self, frame_id: int, evictable: bool) -> None:
    +        """Change whether the frame is currently eligible for eviction."""
    +
    +        self._validate_frame_id(frame_id)
    +        self._evictable[frame_id] = evictable
    +
    +    def evict(self) -> int | None:
    +        """Return one victim after at most two complete sweeps."""
    +
    +        for _ in range(len(self._evictable) * 2):
    +            frame_id = self._hand
    +            self._hand = (self._hand + 1) % len(self._evictable)
    +            if not self._evictable[frame_id]:
    +                continue
    +            if self._referenced[frame_id]:
    +                self._referenced[frame_id] = False
    +                continue
    +            self._evictable[frame_id] = False
    +            return frame_id
    +        return None
    +
    +    def _validate_frame_id(self, frame_id: int) -> None:
    +        if (
    +            type(frame_id) is not int
    +            or frame_id < 0
    +            or frame_id >= len(self._evictable)
    +        ):
    +            raise IndexError(f"frame ID out of range: {frame_id}")
    ```

??? note "File diff: src/minipostgres/storage/slotted.py"
    ```diff
    diff --git a/src/minipostgres/storage/slotted.py b/src/minipostgres/storage/slotted.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3413829f9ee3bc9101a1914e3d8f965b8164618b
    --- /dev/null
    +++ b/src/minipostgres/storage/slotted.py
    @@ -0,0 +1,227 @@
    +"""Stable-slot variable-length page body."""
    +
    +from __future__ import annotations
    +
    +import struct
    +from dataclasses import dataclass
    +from itertools import pairwise
    +
    +from minipostgres.errors import CorruptPage, PageFull
    +from minipostgres.storage.constants import PAGE_BODY_SIZE
    +
    +SLOTTED_BODY_SIZE = PAGE_BODY_SIZE
    +_SLOTTED_MAGIC = b"SLT1"
    +_BODY_HEADER = struct.Struct(">4sHHH2x")
    +_SLOT = struct.Struct(">HHB3x")
    +_DEAD = 0
    +_LIVE = 1
    +SLOT_ENTRY_SIZE = _SLOT.size
    +MAX_SLOT_PAYLOAD = SLOTTED_BODY_SIZE - _BODY_HEADER.size - SLOT_ENTRY_SIZE
    +
    +
    +@dataclass(slots=True)
    +class _Slot:
    +    offset: int
    +    length: int
    +    flags: int
    +
    +    @property
    +    def live(self) -> bool:
    +        return self.flags == _LIVE
    +
    +
    +class SlottedPage:
    +    """One page body whose slot numbers remain stable across compaction."""
    +
    +    def __init__(
    +        self,
    +        page_id: int,
    +        buffer: bytearray,
    +        slots: list[_Slot],
    +        upper: int,
    +    ) -> None:
    +        if type(page_id) is not int or page_id < 0:
    +            raise ValueError("page_id must be a non-negative integer")
    +        self.page_id = page_id
    +        self._buffer = buffer
    +        self._slots = slots
    +        self._upper = upper
    +        self._validate()
    +
    +    @classmethod
    +    def empty(cls, page_id: int) -> SlottedPage:
    +        """Create an empty page body."""
    +
    +        return cls(page_id, bytearray(SLOTTED_BODY_SIZE), [], SLOTTED_BODY_SIZE)
    +
    +    @classmethod
    +    def from_bytes(cls, page_id: int, body: bytes) -> SlottedPage:
    +        """Decode and validate a complete slotted-page body."""
    +
    +        if len(body) != SLOTTED_BODY_SIZE:
    +            raise CorruptPage(
    +                f"slotted page body must contain {SLOTTED_BODY_SIZE} bytes"
    +            )
    +        magic, slot_count, lower, upper = _BODY_HEADER.unpack_from(body)
    +        if magic != _SLOTTED_MAGIC:
    +            raise CorruptPage("invalid slotted page magic")
    +        expected_lower = _BODY_HEADER.size + slot_count * _SLOT.size
    +        if lower != expected_lower:
    +            raise CorruptPage("invalid slotted page bounds")
    +        slots: list[_Slot] = []
    +        for index in range(slot_count):
    +            offset = _BODY_HEADER.size + index * _SLOT.size
    +            tuple_offset, length, flags = _SLOT.unpack_from(body, offset)
    +            if flags not in {_DEAD, _LIVE}:
    +                raise CorruptPage("invalid slot flags")
    +            slots.append(_Slot(tuple_offset, length, flags))
    +        try:
    +            return cls(page_id, bytearray(body), slots, upper)
    +        except ValueError as error:
    +            raise CorruptPage(str(error)) from error
    +
    +    @classmethod
    +    def from_body(cls, page_id: int, body: bytes) -> SlottedPage:
    +        """Decode a page body using the access-method-facing name."""
    +
    +        return cls.from_bytes(page_id, body)
    +
    +    @property
    +    def lower(self) -> int:
    +        """First byte after the slot directory."""
    +
    +        return _BODY_HEADER.size + len(self._slots) * _SLOT.size
    +
    +    @property
    +    def upper(self) -> int:
    +        """First byte in the tuple extent region."""
    +
    +        return self._upper
    +
    +    @property
    +    def contiguous_free_bytes(self) -> int:
    +        """Bytes immediately available without adding a new slot."""
    +
    +        return self._upper - self.lower
    +
    +    def live_slots(self) -> tuple[int, ...]:
    +        """Return live slot IDs in stable numeric order."""
    +
    +        return tuple(index for index, slot in enumerate(self._slots) if slot.live)
    +
    +    def read(self, slot_id: int) -> bytes:
    +        """Read a live tuple extent."""
    +
    +        slot = self._live_slot(slot_id)
    +        return bytes(self._buffer[slot.offset : slot.offset + slot.length])
    +
    +    def insert(self, value: bytes) -> int:
    +        """Insert bytes, reusing the first dead slot when possible."""
    +
    +        dead_slot = next(
    +            (index for index, slot in enumerate(self._slots) if not slot.live),
    +            None,
    +        )
    +        directory_growth = 0 if dead_slot is not None else _SLOT.size
    +        required = len(value) + directory_growth
    +        if required > self.contiguous_free_bytes:
    +            self.compact()
    +        if required > self.contiguous_free_bytes:
    +            raise PageFull(
    +                f"tuple needs {required} bytes, "
    +                f"page has {self.contiguous_free_bytes}"
    +            )
    +
    +        self._upper -= len(value)
    +        self._buffer[self._upper : self._upper + len(value)] = value
    +        new_slot = _Slot(self._upper, len(value), _LIVE)
    +        if dead_slot is None:
    +            slot_id = len(self._slots)
    +            self._slots.append(new_slot)
    +        else:
    +            slot_id = dead_slot
    +            self._slots[slot_id] = new_slot
    +        self._validate()
    +        return slot_id
    +
    +    def delete(self, slot_id: int) -> bytes:
    +        """Mark a slot dead without renumbering any other slot."""
    +
    +        value = self.read(slot_id)
    +        self._slots[slot_id] = _Slot(0, 0, _DEAD)
    +        self._validate()
    +        return value
    +
    +    def compact(self) -> None:
    +        """Pack live tuple bytes while preserving every slot ID."""
    +
    +        compacted = bytearray(SLOTTED_BODY_SIZE)
    +        cursor = SLOTTED_BODY_SIZE
    +        for slot_id, slot in enumerate(self._slots):
    +            if not slot.live:
    +                continue
    +            value = bytes(self._buffer[slot.offset : slot.offset + slot.length])
    +            cursor -= len(value)
    +            compacted[cursor : cursor + len(value)] = value
    +            self._slots[slot_id] = _Slot(cursor, len(value), _LIVE)
    +        self._buffer = compacted
    +        self._upper = cursor
    +        self._validate()
    +
    +    def to_bytes(self) -> bytes:
    +        """Encode a complete fixed-size body."""
    +
    +        self._validate()
    +        encoded = bytearray(self._buffer)
    +        _BODY_HEADER.pack_into(
    +            encoded,
    +            0,
    +            _SLOTTED_MAGIC,
    +            len(self._slots),
    +            self.lower,
    +            self._upper,
    +        )
    +        for index, slot in enumerate(self._slots):
    +            _SLOT.pack_into(
    +                encoded,
    +                _BODY_HEADER.size + index * _SLOT.size,
    +                slot.offset,
    +                slot.length,
    +                slot.flags,
    +            )
    +        return bytes(encoded)
    +
    +    def to_body(self) -> bytes:
    +        """Encode a page body using the access-method-facing name."""
    +
    +        return self.to_bytes()
    +
    +    def _live_slot(self, slot_id: int) -> _Slot:
    +        if type(slot_id) is not int or slot_id < 0 or slot_id >= len(self._slots):
    +            raise KeyError(slot_id)
    +        slot = self._slots[slot_id]
    +        if not slot.live:
    +            raise KeyError(slot_id)
    +        return slot
    +
    +    def _validate(self) -> None:
    +        if len(self._buffer) != SLOTTED_BODY_SIZE:
    +            raise ValueError("invalid slotted page body size")
    +        lower = self.lower
    +        if not (_BODY_HEADER.size <= lower <= self._upper <= SLOTTED_BODY_SIZE):
    +            raise ValueError("invalid slotted page bounds")
    +        extents: list[tuple[int, int]] = []
    +        for slot in self._slots:
    +            if not slot.live:
    +                continue
    +            end = slot.offset + slot.length
    +            if slot.offset < self._upper or end > SLOTTED_BODY_SIZE:
    +                raise ValueError("live slot extent is outside tuple bounds")
    +            if slot.length:
    +                extents.append((slot.offset, end))
    +        extents.sort()
    +        if any(
    +            left_end > right_start
    +            for (_, left_end), (right_start, _) in pairwise(extents)
    +        ):
    +            raise ValueError("live slot extents overlap")
    ```

??? note "File diff: src/minipostgres/storage/tuple.py"
    ```diff
    diff --git a/src/minipostgres/storage/tuple.py b/src/minipostgres/storage/tuple.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..67f3d162e85c4a3889bf3db8def2640ef6921b63
    --- /dev/null
    +++ b/src/minipostgres/storage/tuple.py
    @@ -0,0 +1,226 @@
    +"""Schema-directed encoding for persistent heap tuple versions."""
    +
    +from __future__ import annotations
    +
    +import struct
    +import zlib
    +from dataclasses import dataclass
    +
    +from minipostgres.catalog.model import Schema
    +from minipostgres.errors import CatalogError, CorruptPage, RowTooLarge
    +from minipostgres.row import TID
    +from minipostgres.storage.slotted import MAX_SLOT_PAYLOAD
    +from minipostgres.types import DataType, Scalar
    +
    +SYSTEM_XID = 1
    +
    +_TUPLE_MAGIC = b"TUP1"
    +_TUPLE_VERSION = 1
    +_HAS_NEXT_TID = 1
    +_HEADER = struct.Struct(">4sBBHQQQIII")
    +_INT64 = struct.Struct(">q")
    +_FLOAT64 = struct.Struct(">d")
    +_TEXT_LENGTH = struct.Struct(">I")
    +_MAX_UINT64 = 2**64 - 1
    +_MAX_UINT32 = 2**32 - 1
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class TupleVersion:
    +    """One physical row version and its future MVCC chain link."""
    +
    +    xmin: int
    +    xmax: int
    +    next_tid: TID | None
    +    values: tuple[Scalar, ...]
    +
    +
    +def _schema_fingerprint(schema: Schema) -> int:
    +    payload = bytearray()
    +    for column in schema.columns:
    +        name = column.name.encode("utf-8")
    +        payload.extend(len(name).to_bytes(4, "big"))
    +        payload.extend(name)
    +        payload.extend(column.data_type.value.encode("ascii"))
    +        payload.extend(
    +            bytes(
    +                (
    +                    column.nullable,
    +                    column.primary_key,
    +                    column.unique,
    +                )
    +            )
    +        )
    +    return zlib.crc32(payload) & _MAX_UINT32
    +
    +
    +def _validate_uint(value: int, maximum: int, field: str) -> None:
    +    if type(value) is not int or value < 0 or value > maximum:
    +        raise ValueError(f"{field} is outside the encoded integer domain")
    +
    +
    +class TupleCodec:
    +    """Encode and decode tuple versions against one immutable schema."""
    +
    +    def __init__(self, schema: Schema) -> None:
    +        self._schema = schema
    +        self._schema_hash = _schema_fingerprint(schema)
    +
    +    def encode(self, version: TupleVersion) -> bytes:
    +        """Encode a validated row with a fixed version header."""
    +
    +        _validate_uint(version.xmin, _MAX_UINT64, "xmin")
    +        _validate_uint(version.xmax, _MAX_UINT64, "xmax")
    +        try:
    +            values = self._schema.validate_row(version.values)
    +        except CatalogError:
    +            raise
    +
    +        flags = 0
    +        next_page = 0
    +        next_slot = 0
    +        if version.next_tid is not None:
    +            _validate_uint(version.next_tid.page_id, _MAX_UINT64, "next page")
    +            _validate_uint(version.next_tid.slot_id, _MAX_UINT32, "next slot")
    +            flags |= _HAS_NEXT_TID
    +            next_page = version.next_tid.page_id
    +            next_slot = version.next_tid.slot_id
    +
    +        null_bitmap = bytearray((len(values) + 7) // 8)
    +        payload = bytearray(null_bitmap)
    +        for index, (column, value) in enumerate(
    +            zip(self._schema.columns, values, strict=True)
    +        ):
    +            if value is None:
    +                payload[index // 8] |= 1 << (index % 8)
    +                continue
    +            if column.data_type is DataType.INT64:
    +                assert type(value) is int
    +                payload.extend(_INT64.pack(value))
    +            elif column.data_type is DataType.FLOAT64:
    +                assert type(value) is float
    +                payload.extend(_FLOAT64.pack(value))
    +            elif column.data_type is DataType.BOOLEAN:
    +                assert type(value) is bool
    +                payload.append(1 if value else 0)
    +            else:
    +                assert type(value) is str
    +                encoded_text = value.encode("utf-8")
    +                if len(encoded_text) > _MAX_UINT32:
    +                    raise RowTooLarge("TEXT value exceeds encoded length limit")
    +                payload.extend(_TEXT_LENGTH.pack(len(encoded_text)))
    +                payload.extend(encoded_text)
    +
    +        encoded = _HEADER.pack(
    +            _TUPLE_MAGIC,
    +            _TUPLE_VERSION,
    +            flags,
    +            len(values),
    +            version.xmin,
    +            version.xmax,
    +            next_page,
    +            next_slot,
    +            self._schema_hash,
    +            len(payload),
    +        ) + bytes(payload)
    +        if len(encoded) > MAX_SLOT_PAYLOAD:
    +            raise RowTooLarge(
    +                f"encoded tuple is {len(encoded)} bytes; "
    +                f"maximum is {MAX_SLOT_PAYLOAD}"
    +            )
    +        return encoded
    +
    +    def decode(self, encoded: bytes) -> TupleVersion:
    +        """Decode one tuple and reject any non-canonical or corrupt payload."""
    +
    +        if len(encoded) < _HEADER.size:
    +            raise CorruptPage("truncated tuple header")
    +        (
    +            magic,
    +            version,
    +            flags,
    +            column_count,
    +            xmin,
    +            xmax,
    +            next_page,
    +            next_slot,
    +            schema_hash,
    +            payload_length,
    +        ) = _HEADER.unpack_from(encoded)
    +        if magic != _TUPLE_MAGIC or version != _TUPLE_VERSION:
    +            raise CorruptPage("unsupported tuple format")
    +        if flags & ~_HAS_NEXT_TID:
    +            raise CorruptPage("invalid tuple flags")
    +        if column_count != len(self._schema.columns):
    +            raise CorruptPage("tuple schema column count does not match")
    +        if schema_hash != self._schema_hash:
    +            raise CorruptPage("tuple schema fingerprint does not match")
    +        if len(encoded) != _HEADER.size + payload_length:
    +            raise CorruptPage("tuple payload length does not match")
    +
    +        bitmap_length = (column_count + 7) // 8
    +        if payload_length < bitmap_length:
    +            raise CorruptPage("truncated tuple null bitmap")
    +        payload = memoryview(encoded)[_HEADER.size:]
    +        bitmap = payload[:bitmap_length]
    +        cursor = bitmap_length
    +        values: list[Scalar] = []
    +        for index, column in enumerate(self._schema.columns):
    +            if bitmap[index // 8] & (1 << (index % 8)):
    +                values.append(None)
    +                continue
    +            if column.data_type is DataType.INT64:
    +                end = self._require_bytes(payload, cursor, _INT64.size)
    +                value = _INT64.unpack_from(payload, cursor)[0]
    +                cursor = end
    +            elif column.data_type is DataType.FLOAT64:
    +                end = self._require_bytes(payload, cursor, _FLOAT64.size)
    +                value = _FLOAT64.unpack_from(payload, cursor)[0]
    +                cursor = end
    +            elif column.data_type is DataType.BOOLEAN:
    +                if cursor >= len(payload):
    +                    raise CorruptPage("truncated boolean value")
    +                boolean = int(payload[cursor])
    +                cursor += 1
    +                if boolean not in (0, 1):
    +                    raise CorruptPage("invalid boolean value")
    +                value = boolean == 1
    +            else:
    +                end = self._require_bytes(payload, cursor, _TEXT_LENGTH.size)
    +                raw_length = _TEXT_LENGTH.unpack_from(payload, cursor)[0]
    +                cursor = end
    +                end = cursor + raw_length
    +                if end > len(payload):
    +                    raise CorruptPage("truncated TEXT value")
    +                try:
    +                    value = bytes(payload[cursor:end]).decode("utf-8")
    +                except UnicodeDecodeError as error:
    +                    raise CorruptPage("invalid UTF-8 TEXT value") from error
    +                cursor = end
    +            values.append(value)
    +        if cursor != len(payload):
    +            raise CorruptPage("tuple payload has trailing bytes")
    +
    +        if flags & _HAS_NEXT_TID:
    +            next_tid = TID(next_page, next_slot)
    +        else:
    +            if next_page != 0 or next_slot != 0:
    +                raise CorruptPage("tuple has hidden next-TID fields")
    +            next_tid = None
    +        result = TupleVersion(xmin, xmax, next_tid, tuple(values))
    +        try:
    +            self._schema.validate_row(result.values)
    +        except CatalogError as error:
    +            raise CorruptPage("tuple values violate the encoded schema") from error
    +        return result
    +
    +    @staticmethod
    +    def _require_bytes(
    +        payload: memoryview,
    +        cursor: int,
    +        size: int,
    +    ) -> int:
    +        end = cursor + size
    +        if end > len(payload):
    +            raise CorruptPage("truncated fixed-width tuple value")
    +        return end
    ```

**What it is and why it appears**

The central mechanism is persistent heap files. Pages, slots, tuple bytes, disk IO, replacement, and buffer ownership must compose into stable row locations.

**Runtime role**

Pinned dirty pages reach disk through owned guards, and tuple IDs remain stable across restart.

**Statement understanding**

The durable boundary is this: pinned dirty pages reach disk through owned guards, and tuple IDs remain stable across restart.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/12-persistent-heap/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: pinned dirty pages reach disk through owned guards, and tuple IDs remain stable across restart.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/03-storage.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/12-persistent-heap/stage.patch)
