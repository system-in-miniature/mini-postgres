# Phase B Persistent Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Phase A's volatile table registry with fixed-size slotted heap pages reached through a buffer pool, then add a persistent page-based B+Tree whose entries map encoded keys to candidate TIDs.

**Architecture:** Relation files are arrays of 8192-byte pages. Heap and B+Tree access methods request `PageKey` values through one buffer-pool API; page guards own pins and dirty transitions, and a Clock replacer selects only unpinned frames. Heap pages preserve stable slot IDs, while indexes remain derived state and always return candidate TIDs for heap recheck.

**Tech Stack:** Python 3.12, `os.pread`/`os.pwrite`, `struct`, CRC32C-compatible standard-library CRC32 for the custom format, uv, pytest, Hypothesis, Ruff, Pyright.

---

## File map

```text
src/minipostgres/storage/constants.py    format constants and page kinds
src/minipostgres/storage/identifiers.py  relation/fork/page keys
src/minipostgres/storage/page.py         common header and checksum codec
src/minipostgres/storage/slotted.py      stable slotted-page mutation
src/minipostgres/storage/tuple.py        typed tuple/version codec
src/minipostgres/storage/disk.py         relation files and fixed-page I/O
src/minipostgres/storage/replacer.py     deterministic Clock policy
src/minipostgres/storage/buffer.py       frames, pins, guards, flush gates
src/minipostgres/storage/free_space.py   approximate heap free-space map
src/minipostgres/storage/heap.py         persistent TableAccess
src/minipostgres/index/key.py            typed composite-key encoding
src/minipostgres/index/pages.py          B+Tree metapage/internal/leaf codecs
src/minipostgres/index/btree.py          search/insert/delete/rebalance
src/minipostgres/index/iterator.py       sibling-backed range iterator
tests/unit/storage/                       page, tuple, disk, buffer tests
tests/unit/index/                         key and tree operation tests
tests/property/                           stable-slot and sorted-multimap models
tests/integration/                        heap/index restart and engine wiring
tests/acceptance/test_phase_b.py          persistent-storage acceptance
```

### Task 1: Common page identity, header, and checksum

**Files:**
- Create: `src/minipostgres/storage/__init__.py`
- Create: `src/minipostgres/storage/constants.py`
- Create: `src/minipostgres/storage/identifiers.py`
- Create: `src/minipostgres/storage/page.py`
- Create: `tests/unit/storage/test_page_header.py`

- [ ] **Step 1: Write failing format tests**

```python
def test_page_round_trip_preserves_identity_lsn_and_payload() -> None:
    key = PageKey(RelationId(ForkKind.HEAP, 7), page_id=3)
    encoded = encode_page(key, PageKind.HEAP, page_lsn=91, body=b"abc")
    decoded = decode_page(key, encoded)
    assert len(encoded) == PAGE_SIZE == 8192
    assert decoded.kind is PageKind.HEAP
    assert decoded.page_lsn == 91
    assert decoded.body.startswith(b"abc")


def test_page_checksum_detects_torn_or_wrong_relation_page() -> None:
    encoded = bytearray(
        encode_page(heap_page_key(1, 0), PageKind.HEAP, 0, b"row")
    )
    encoded[-1] ^= 0xFF
    with pytest.raises(CorruptPage, match="checksum"):
        decode_page(heap_page_key(1, 0), bytes(encoded))
    with pytest.raises(CorruptPage, match="identity"):
        decode_page(heap_page_key(2, 0), bytes(encoded))
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest -q tests/unit/storage/test_page_header.py
```

Expected: collection fails because storage page modules do not exist.

- [ ] **Step 3: Implement the frozen page envelope**

Define:

```python
PAGE_SIZE = 8192
PAGE_MAGIC = b"MPG1"
PAGE_FORMAT_VERSION = 1

class ForkKind(Enum): HEAP, BTREE
class PageKind(Enum): HEAP, BTREE_META, BTREE_INTERNAL, BTREE_LEAF
@dataclass(frozen=True, slots=True)
class RelationId: fork: ForkKind; object_id: int
@dataclass(frozen=True, slots=True)
class PageKey: relation: RelationId; page_id: int
```

Use a fixed `struct.Struct` header containing magic, version, kind, object ID,
page ID, page LSN, lower, upper, special, and CRC32. Encode zero-filled pages
and calculate CRC with the checksum field zeroed. Decode validates exact size,
identity, bounds, kind, version, and checksum.

- [ ] **Step 4: Run page tests and checks**

```bash
uv run pytest -q tests/unit/storage/test_page_header.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/storage tests/unit/storage/test_page_header.py
git commit -m "feat: define checksummed storage pages"
```

### Task 2: Stable slotted-page body

**Files:**
- Create: `src/minipostgres/storage/slotted.py`
- Create: `tests/unit/storage/test_slotted_page.py`
- Create: `tests/property/test_slotted_page_model.py`

- [ ] **Step 1: Write failing stable-slot tests**

```python
def test_compaction_moves_bytes_without_renumbering_live_slots() -> None:
    page = SlottedPage.empty(page_id=0)
    first = page.insert(b"a" * 100)
    second = page.insert(b"b" * 100)
    third = page.insert(b"c" * 100)
    page.delete(second)
    page.compact()
    assert (first, third) == (0, 2)
    assert page.read(first) == b"a" * 100
    assert page.read(third) == b"c" * 100


@given(st.lists(st.binary(min_size=0, max_size=128), max_size=40))
def test_slotted_page_matches_stable_slot_reference(values) -> None:
    page = SlottedPage.empty(page_id=0)
    model: dict[int, bytes] = {}
    for value in values:
        try:
            slot = page.insert(value)
        except PageFull:
            break
        model[slot] = value
    assert {slot: page.read(slot) for slot in page.live_slots()} == model
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/storage/test_slotted_page.py \
  tests/property/test_slotted_page_model.py
```

Expected: imports fail because `SlottedPage` does not exist.

- [ ] **Step 3: Implement stable slots and compaction**

Slots are fixed-size `(offset, length, flags)` entries growing from `lower`.
Tuple extents grow backward from `upper`. Deletion marks a slot dead without
renumbering. `compact()` repacks live extents from the page end and changes
only slot offsets. Insertion first reuses a dead slot when enough contiguous
space exists, then appends a slot. Every mutation revalidates:

```text
header <= lower <= upper <= special <= PAGE_SIZE
all live extents are in body bounds
all live extents are disjoint
```

- [ ] **Step 4: Run slotted-page tests**

```bash
uv run pytest -q tests/unit/storage/test_slotted_page.py \
  tests/property/test_slotted_page_model.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/storage/slotted.py tests/unit/storage \
  tests/property/test_slotted_page_model.py
git commit -m "feat: store tuples in stable page slots"
```

### Task 3: Typed tuple and version codec

**Files:**
- Create: `src/minipostgres/storage/tuple.py`
- Create: `tests/unit/storage/test_tuple_codec.py`
- Create: `tests/property/test_tuple_codec.py`

- [ ] **Step 1: Write failing tuple round-trip tests**

```python
def test_tuple_codec_preserves_nulls_unicode_and_version_header() -> None:
    version = TupleVersion(
        xmin=SYSTEM_XID,
        xmax=0,
        next_tid=None,
        values=(7, 1.5, True, "雪", None),
    )
    encoded = TupleCodec(schema).encode(version)
    assert TupleCodec(schema).decode(encoded) == version


def test_tuple_codec_rejects_wrong_schema_and_truncated_payload() -> None:
    encoded = TupleCodec(users_schema).encode(users_version)
    with pytest.raises(CorruptPage):
        TupleCodec(other_schema).decode(encoded)
    with pytest.raises(CorruptPage):
        TupleCodec(users_schema).decode(encoded[:-1])
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/storage/test_tuple_codec.py \
  tests/property/test_tuple_codec.py
```

Expected: imports fail because tuple codec does not exist.

- [ ] **Step 3: Implement tuple versions and length-delimited values**

Define:

```python
SYSTEM_XID = 1
@dataclass(frozen=True, slots=True)
class TupleVersion:
    xmin: int
    xmax: int
    next_tid: TID | None
    values: tuple[Scalar, ...]
```

Encode a fixed version header, column count, null bitmap, then schema-directed
fixed-width INT64/FLOAT64/BOOLEAN values and 32-bit length-delimited UTF-8
TEXT. Decode validates lengths, UTF-8, bool bytes, column count, and exact
payload consumption. Reject encoded tuples larger than the maximum slotted
page payload with `RowTooLarge`.

- [ ] **Step 4: Run tuple tests**

```bash
uv run pytest -q tests/unit/storage/test_tuple_codec.py \
  tests/property/test_tuple_codec.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/storage/tuple.py tests/unit/storage/test_tuple_codec.py \
  tests/property/test_tuple_codec.py
git commit -m "feat: encode typed tuple versions"
```

### Task 4: Relation-file disk manager

**Files:**
- Create: `src/minipostgres/storage/disk.py`
- Create: `tests/unit/storage/test_disk_manager.py`
- Create: `tests/integration/test_disk_restart.py`

- [ ] **Step 1: Write failing fixed-page I/O tests**

```python
def test_disk_manager_allocates_reads_and_reopens_pages(tmp_path: Path) -> None:
    manager = DiskManager.open(tmp_path)
    key = manager.allocate_page(RelationId(ForkKind.HEAP, 4))
    page = encode_page(key, PageKind.HEAP, 0, b"durable")
    manager.write_page(key, page)
    manager.sync_relation(key.relation)
    reopened = DiskManager.open(tmp_path)
    assert reopened.read_page(key) == page
    assert reopened.page_count(key.relation) == 1


def test_disk_manager_rejects_short_relation_files(tmp_path: Path) -> None:
    relation_path(tmp_path, heap_relation(1)).write_bytes(b"partial")
    with pytest.raises(CorruptPage, match="multiple of"):
        DiskManager.open(tmp_path).page_count(heap_relation(1))
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/storage/test_disk_manager.py \
  tests/integration/test_disk_restart.py
```

Expected: imports fail because `DiskManager` does not exist.

- [ ] **Step 3: Implement relation files**

Store heap files under `relations/table-<id>.heap` and B+Tree files under
`indexes/index-<id>.btree`. Use `os.open`, `os.pread`, and `os.pwrite`; reject
short reads/writes. Page allocation appends one checksummed empty page and
returns its `PageKey`. Relation sync calls `fsync`; first creation also fsyncs
the parent directory. Close is idempotent.

- [ ] **Step 4: Run disk tests**

```bash
uv run pytest -q tests/unit/storage/test_disk_manager.py \
  tests/integration/test_disk_restart.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/storage/disk.py tests/unit/storage/test_disk_manager.py \
  tests/integration/test_disk_restart.py
git commit -m "feat: persist fixed relation pages"
```

### Task 5: Clock replacer

**Files:**
- Create: `src/minipostgres/storage/replacer.py`
- Create: `tests/unit/storage/test_clock_replacer.py`

- [ ] **Step 1: Write failing deterministic replacement tests**

```python
def test_clock_skips_pinned_and_gives_referenced_frame_second_chance() -> None:
    clock = ClockReplacer(frame_count=3)
    clock.mark_evictable(0, True)
    clock.mark_evictable(1, False)
    clock.mark_evictable(2, True)
    clock.record_access(0)
    assert clock.evict() == 2
    assert clock.evict() == 0


def test_clock_returns_none_when_every_frame_is_pinned() -> None:
    clock = ClockReplacer(frame_count=2)
    assert clock.evict() is None
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/storage/test_clock_replacer.py
```

Expected: import fails because `ClockReplacer` does not exist.

- [ ] **Step 3: Implement Clock state**

Maintain one reference bit, one evictable bit, and a circular hand per frame.
`record_access` sets reference. `mark_evictable` changes eligibility.
`evict` scans at most two complete cycles, clears one reference bit as a
second chance, and returns the first unreferenced evictable frame.

- [ ] **Step 4: Run replacer tests**

```bash
uv run pytest -q tests/unit/storage/test_clock_replacer.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/storage/replacer.py \
  tests/unit/storage/test_clock_replacer.py
git commit -m "feat: select unpinned frames with Clock"
```

### Task 6: Buffer pool and page guards

**Files:**
- Create: `src/minipostgres/storage/buffer.py`
- Create: `tests/unit/storage/test_buffer_pool.py`
- Create: `tests/unit/storage/test_page_guard.py`
- Create: `tests/integration/test_buffer_eviction.py`

- [ ] **Step 1: Write failing pin, dirty, and eviction tests**

```python
def test_page_guard_unpins_and_records_dirty_lsn(buffer_pool, heap_key) -> None:
    with buffer_pool.fetch_page(heap_key) as guard:
        guard.replace_bytes(changed_page)
        guard.mark_dirty(page_lsn=17)
        assert buffer_pool.pin_count(heap_key) == 1
    assert buffer_pool.pin_count(heap_key) == 0
    assert buffer_pool.frame(heap_key).page_lsn == 17


def test_dirty_eviction_flushes_wal_before_page(
    disk: RecordingDisk, wal_gate: RecordingWalGate
) -> None:
    pool = BufferPool(disk, frame_count=1, wal_flush_gate=wal_gate)
    dirty_one_page(pool, first_key, page_lsn=44)
    with pool.fetch_page(second_key):
        pass
    assert wal_gate.calls == [44]
    assert disk.writes[0].key == first_key
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/storage/test_buffer_pool.py \
  tests/unit/storage/test_page_guard.py tests/integration/test_buffer_eviction.py
```

Expected: imports fail because buffer components do not exist.

- [ ] **Step 3: Implement frames, pool, and guards**

`BufferPool` owns fixed frames, a `PageKey → frame_id` table, free frames,
Clock, and a lock. `fetch_page` pins an existing frame or selects a free/
evictable frame, flushes its victim if dirty, then reads and decodes the
requested page. `new_page` asks `DiskManager` to allocate and pins it.

`PageGuard` is a context manager exposing a mutable decoded page view. It can
mark dirty only with a nondecreasing LSN and unpins exactly once. Pool flush
calls `wal_flush_gate(page_lsn)` before `DiskManager.write_page`. Until Phase D,
the default gate records no WAL and accepts only LSN zero.

- [ ] **Step 4: Run buffer tests**

```bash
uv run pytest -q tests/unit/storage/test_buffer_pool.py \
  tests/unit/storage/test_page_guard.py tests/integration/test_buffer_eviction.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/storage/buffer.py tests/unit/storage \
  tests/integration/test_buffer_eviction.py
git commit -m "feat: mediate pages through a buffer pool"
```

### Task 7: Heap file and approximate free-space map

**Files:**
- Create: `src/minipostgres/storage/free_space.py`
- Create: `src/minipostgres/storage/heap.py`
- Create: `tests/unit/storage/test_free_space.py`
- Create: `tests/integration/test_heap_table.py`
- Create: `tests/property/test_heap_table_model.py`

- [ ] **Step 1: Write failing persistent TableAccess tests**

```python
def test_heap_insert_fetch_scan_update_delete_and_restart(storage, users_meta) -> None:
    heap = HeapTable.open(storage.buffer_pool, users_meta)
    first = heap.insert((1, "A", 20))
    second = heap.insert((2, "B", 30))
    replacement = heap.replace(second, (2, "B", 31))
    heap.delete(first)
    storage.flush_and_close()
    reopened = HeapTable.open(reopen_pool(), users_meta)
    assert reopened.fetch(first) is None
    assert reopened.fetch(replacement) == (2, "B", 31)
    assert list(reopened.scan()) == [(replacement, (2, "B", 31))]


def test_heap_repairs_stale_free_space_estimate(storage, users_meta) -> None:
    heap = HeapTable.open(storage.buffer_pool, users_meta)
    heap.free_space.record(page_id=0, free_bytes=PAGE_SIZE)
    tid = heap.insert(large_but_valid_row)
    assert heap.fetch(tid) == large_but_valid_row
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/storage/test_free_space.py \
  tests/integration/test_heap_table.py tests/property/test_heap_table_model.py
```

Expected: imports fail because heap components do not exist.

- [ ] **Step 3: Implement heap access through the pool**

The free-space map stores one byte category per page and persists as an
atomically replaced sidecar. Heap insertion tries candidate pages in category
order, checks actual free bytes, repairs stale estimates, compacts once, then
allocates a page. Phase B tuple versions use `xmin=SYSTEM_XID`, `xmax=0`.

`replace` inserts a new physical tuple and deletes the old slot because MVCC
does not own version chains until Phase D. `scan` visits page and live slot
order. Every method uses page guards and returns/accepts the common `TID`.

- [ ] **Step 4: Run heap tests**

```bash
uv run pytest -q tests/unit/storage tests/integration/test_heap_table.py \
  tests/property/test_heap_table_model.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/storage/free_space.py \
  src/minipostgres/storage/heap.py tests
git commit -m "feat: store rows in persistent heap files"
```

### Task 8: Typed index-key codec

**Files:**
- Create: `src/minipostgres/index/__init__.py`
- Create: `src/minipostgres/index/key.py`
- Create: `tests/unit/index/test_key_codec.py`
- Create: `tests/property/test_key_order.py`

- [ ] **Step 1: Write failing key-order tests**

```python
def test_key_codec_preserves_scalar_and_composite_order() -> None:
    codec = KeyCodec((DataType.INT64, DataType.TEXT))
    values = [(-2, "z"), (1, "a"), (1, "b"), (9, "")]
    assert sorted(values, key=codec.encode) == values


def test_unique_index_rejects_null_key_in_frozen_scope() -> None:
    codec = KeyCodec((DataType.INT64,))
    with pytest.raises(TypeMismatch, match="NULL index key"):
        codec.encode((None,))
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/index/test_key_codec.py \
  tests/property/test_key_order.py
```

Expected: imports fail because index key modules do not exist.

- [ ] **Step 3: Implement order-preserving keys**

Encode signed INT64 by flipping its sign bit in big-endian representation,
FLOAT64 with the standard sign-aware sortable transform, BOOLEAN as one byte,
and TEXT as escaped UTF-8 terminated by `0x00 0x00`. Prefix each composite
component with a type tag. The frozen index subset rejects NULL keys rather
than reproducing PostgreSQL's null uniqueness options.

- [ ] **Step 4: Run key tests**

```bash
uv run pytest -q tests/unit/index/test_key_codec.py \
  tests/property/test_key_order.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/index tests/unit/index tests/property/test_key_order.py
git commit -m "feat: encode ordered BTree keys"
```

### Task 9: B+Tree page formats and search/insert

**Files:**
- Create: `src/minipostgres/index/pages.py`
- Create: `src/minipostgres/index/btree.py`
- Create: `tests/unit/index/test_btree_pages.py`
- Create: `tests/unit/index/test_btree_insert.py`
- Create: `tests/property/test_btree_multimap.py`

- [ ] **Step 1: Write failing split and multimap tests**

```python
def test_btree_root_and_leaf_split_preserve_search(tmp_tree) -> None:
    inserted = [(encode_int(key), TID(key // 3, key % 3)) for key in range(500)]
    for key, tid in inserted:
        tmp_tree.insert(key, tid)
    assert tmp_tree.height > 1
    for key, tid in inserted:
        assert tid in tmp_tree.search(key)


@given(st.lists(st.tuples(st.integers(), tids()), max_size=500))
def test_btree_matches_sorted_multimap(entries, tree) -> None:
    model: dict[bytes, list[TID]] = defaultdict(list)
    for value, tid in entries:
        key = encode_int(value)
        tree.insert(key, tid)
        if tid not in model[key]:
            model[key].append(tid)
    assert [(key, tree.search(key)) for key in sorted(model)] == [
        (key, tuple(sorted(tids))) for key, tids in sorted(model.items())
    ]
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/index/test_btree_pages.py \
  tests/unit/index/test_btree_insert.py tests/property/test_btree_multimap.py
```

Expected: imports fail because tree pages and BTree do not exist.

- [ ] **Step 3: Implement metapage, internal, leaf, and recursive split**

The metapage stores root page ID and height. Internal pages store sorted
separator keys with child page IDs. Leaves store sorted `(key, TID)` pairs and
left/right sibling page IDs. Duplicate `(key, TID)` insertion is idempotent.

Search descends with binary search. Insert latches one path, inserts in leaf,
splits at byte-balanced boundaries, propagates one separator upward, and
creates a new root when required. All I/O uses page guards.

- [ ] **Step 4: Run insertion tests**

```bash
uv run pytest -q tests/unit/index/test_btree_pages.py \
  tests/unit/index/test_btree_insert.py tests/property/test_btree_multimap.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/index tests/unit/index \
  tests/property/test_btree_multimap.py
git commit -m "feat: insert and split persistent BTree pages"
```

### Task 10: B+Tree deletion, rebalance, and range iteration

**Files:**
- Modify: `src/minipostgres/index/btree.py`
- Create: `src/minipostgres/index/iterator.py`
- Create: `tests/unit/index/test_btree_delete.py`
- Create: `tests/unit/index/test_btree_range.py`
- Create: `tests/integration/test_btree_restart.py`

- [ ] **Step 1: Write failing delete/merge/range tests**

```python
def test_delete_redistributes_merges_and_collapses_root(tree) -> None:
    for key in range(300):
        tree.insert(encode_int(key), TID(0, key))
    for key in range(299):
        assert tree.delete(encode_int(key), TID(0, key))
    assert tree.height == 1
    assert tree.search(encode_int(299)) == (TID(0, 299),)


def test_range_iterator_crosses_leaf_siblings_and_restarts(tree_path) -> None:
    tree = build_tree(tree_path, range(500))
    expected = list(range(123, 322))
    assert decode_range(tree.range(encode_int(123), encode_int(321))) == expected
    tree.close()
    reopened = reopen_tree(tree_path)
    assert decode_range(
        reopened.range(encode_int(123), encode_int(321))
    ) == expected
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/index/test_btree_delete.py \
  tests/unit/index/test_btree_range.py tests/integration/test_btree_restart.py
```

Expected: deletion/range assertions fail because operations are absent.

- [ ] **Step 3: Implement removal and sibling-backed iteration**

Delete one exact `(key, TID)`. Underflow first borrows from a sibling with
surplus entries, otherwise merges and removes the parent separator recursively.
Collapse an internal root with one child. Empty root remains an empty leaf.

Range iteration seeks the lower bound once and follows right-sibling IDs until
the inclusive upper bound is exceeded. The iterator pins only its current leaf
and releases it on advance or close.

- [ ] **Step 4: Run complete tree tests**

```bash
uv run pytest -q tests/unit/index tests/property/test_btree_multimap.py \
  tests/integration/test_btree_restart.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/index tests/unit/index \
  tests/integration/test_btree_restart.py
git commit -m "feat: rebalance and iterate BTree ranges"
```

### Task 11: Catalog index publication and persistent engine wiring

**Files:**
- Modify: `src/minipostgres/catalog/catalog.py`
- Modify: `src/minipostgres/engine.py`
- Modify: `src/minipostgres/executor/factory.py`
- Modify: `src/minipostgres/executor/operators.py`
- Create: `tests/integration/test_engine_heap_restart.py`
- Create: `tests/integration/test_create_index.py`
- Create: `tests/contract/test_unique_index.py`

- [ ] **Step 1: Write failing engine persistence/index tests**

```python
def test_committed_phase_b_rows_survive_clean_restart(tmp_path: Path) -> None:
    with Database.open(tmp_path) as db:
        db.execute("CREATE TABLE users (id INT, name TEXT)")
        db.execute("INSERT INTO users VALUES (1, 'A'), (2, 'B')")
    with Database.open(tmp_path) as db:
        assert db.execute("SELECT * FROM users ORDER BY id").rows == (
            (1, "A"), (2, "B")
        )


def test_create_unique_index_builds_existing_rows_before_publication(engine) -> None:
    seed_users(engine)
    engine.execute("CREATE UNIQUE INDEX users_id ON users (id)")
    with pytest.raises(ConstraintViolation):
        engine.execute("INSERT INTO users VALUES (1, 'duplicate')")
    assert engine.catalog.index("users_id").unique
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/integration/test_engine_heap_restart.py \
  tests/integration/test_create_index.py tests/contract/test_unique_index.py
```

Expected: rows disappear on restart and index statements are not executed.

- [ ] **Step 3: Wire HeapTable and transactional index publication**

Database startup builds one `HeapTable` per catalog table and one `BTree` per
published index. `CREATE TABLE` creates/fsyncs the empty heap before catalog
publication. `CREATE INDEX` writes to a temporary relation, scans the heap,
checks uniqueness, fsyncs, atomically renames, fsyncs the index directory, then
publishes metadata. Failed builds remove the temporary file.

Modification executors maintain every published index around heap mutation.
Phase B serializes each statement under the engine write latch, so unique
check plus heap/index change is atomic inside the process. Phase D replaces
this with key locks and MVCC-aware checks.

- [ ] **Step 4: Run engine persistence tests**

```bash
uv run pytest -q tests/integration/test_engine_heap_restart.py \
  tests/integration/test_create_index.py tests/contract/test_unique_index.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres tests/integration tests/contract/test_unique_index.py
git commit -m "feat: persist tables and publish BTree indexes"
```

### Task 12: Phase B acceptance and documentation

**Files:**
- Modify: `README.md`
- Modify: `ARCHITECTURE.md`
- Modify: `BEHAVIORAL_CONTRACT.md`
- Modify: `DIFFERENCES_FROM_POSTGRESQL.md`
- Create: `tests/acceptance/test_phase_b.py`

- [ ] **Step 1: Write failing storage acceptance**

```python
def test_phase_b_storage_acceptance(tmp_path: Path) -> None:
    with Database.open(tmp_path, buffer_frames=3) as db:
        build_multi_page_table_and_indexes(db)
        expected = query_all_rows(db)
    with Database.open(tmp_path, buffer_frames=2) as db:
        assert query_all_rows(db) == expected
        assert every_index_candidate_matches_visible_heap_scan(db)


def test_executor_has_no_direct_disk_or_collection_bypass() -> None:
    executor_sources = all_python_sources("src/minipostgres/executor")
    assert "DiskManager" not in executor_sources
    assert ".read_page(" not in executor_sources
```

- [ ] **Step 2: Run acceptance and verify RED**

```bash
uv run pytest -q tests/acceptance/test_phase_b.py
```

Expected: fails until acceptance helpers and documentation are complete.

- [ ] **Step 3: Document the physical-storage contract**

Document 8 KiB pages, stable slots/TIDs, tuple size limit, page checksum and
LSN reservation, buffer pin/dirty rules, Clock, heap/FSM behavior, B+Tree
candidate semantics, statement-serialized uniqueness, clean restart, and the
deliberate absence of WAL/MVCC in Phase B.

- [ ] **Step 4: Run full Phase B verification**

```bash
uv sync
uv run ruff check .
uv run pyright src
uv run pytest -q
git diff --check
```

Expected: all static checks and tests pass; diff check is silent.

- [ ] **Step 5: Commit Phase B acceptance**

```bash
git add README.md ARCHITECTURE.md BEHAVIORAL_CONTRACT.md \
  DIFFERENCES_FROM_POSTGRESQL.md tests/acceptance/test_phase_b.py
git commit -m "docs: accept MiniPostgres persistent storage phase"
```

## Plan self-review

- Every normal persistent page access passes through BufferPool.
- Page LSN exists now; only LSN zero is accepted before WAL ownership.
- Slot compaction cannot change a live TID.
- Phase B replacement is explicitly non-MVCC and is replaced, not hidden, in
  Phase D.
- Indexes store candidate TIDs and never own tuple visibility.
- Unique checks are statement-serialized in Phase B and not presented as the
  final concurrent behavior.
- B+Tree restart, splits, merges, duplicates, and range traversal have direct
  and property evidence.
- Catalog publication orders storage durability before metadata visibility.
- No task adds a network protocol or course artifact.
