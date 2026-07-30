# Chapter 3 — Pages and the Buffer Pool

SQL rows eventually become bytes at stable physical addresses. MiniPostgres
uses checksummed 8192-byte pages, a slotted heap body, tuple identifiers
(`TID`s), a fixed-frame buffer pool, deterministic Clock replacement, and an
approximate free-space map. Each piece answers a different question: what is a
valid page, where is a tuple, who owns a cached page, which page may leave
memory, and where might a new tuple fit?

## Learning objectives

After this chapter, you can:

1. explain what `encode_page()` binds into an 8192-byte page checksum;
2. show why compaction preserves `TID(page_id, slot_id)`;
3. describe pin and release ownership through `PageGuard`;
4. simulate the second-chance decision in `ClockReplacer.evict()`; and
5. explain why the free-space map may be wrong without corrupting insertion.

## The common page envelope

`PAGE_SIZE` is 8192 in `src/minipostgres/storage/constants.py`. Heap and B+Tree
files are arrays of pages of exactly that size. The common codec lives in
`src/minipostgres/storage/page.py`.

`encode_page()` writes a fixed header containing magic, format version, page
kind, relation fork, relation object ID, page ID, page LSN, body bounds, and
reserved fields. It pads the remainder to 8192 bytes, computes CRC32 while the
checksum field is zero, and installs the checksum. Identity is therefore
covered: copying a valid page to a different relation or page number is not a
valid relocation.

`decode_page(expected_key, encoded)` validates length, magic, version, enum
values, reserved fields, expected physical identity, bounds, and checksum
before returning `DecodedPage`. The caller supplies the address it intended to
read, preventing bytes from defining their own trusted address.

The checksum detects corruption; it is not a cryptographic authenticity
mechanism. The page LSN is a durability ordering field used by WAL and
recovery, not a timestamp.

## Slotted pages and stable TIDs

Heap page bodies use `SlottedPage` in
`src/minipostgres/storage/slotted.py`. A small body header and slot directory
grow from the front. Variable-length tuple extents grow backward from the end:

```text
body header | slot 0 | slot 1 | ... | free space | ... tuple bytes
             lower →                         ← upper
```

A slot stores extent offset, length, and live/dead flag. The public physical
row address is `TID(page_id, slot_id)` from `src/minipostgres/row.py`.

`SlottedPage.insert()` first finds the lowest dead slot. Reusing it needs no
new directory entry. If contiguous space is insufficient, the method calls
`compact()`, then performs the exact fit check. `delete()` marks only the
chosen slot dead. `compact()` copies live extents to a fresh buffer and updates
their offsets while iterating the same slot IDs. It never renumbers a live
slot.

This separation is crucial. Extent offsets are movable storage details; slot
IDs are stable references. An index can keep a TID while compaction changes
the byte address of its tuple. A deleted slot may later be reused, but only
after the higher-level MVCC/VACUUM policy says reclamation is safe.

`available_free_bytes` means space after compaction, excluding the fixed slot
directory. `contiguous_free_bytes` means space usable immediately. Confusing
them would either waste pages or admit a tuple that cannot currently fit.

## Tuple bytes

`TupleCodec.encode()` in `src/minipostgres/storage/tuple.py` turns a
`TupleVersion` into a header plus null bitmap and schema-directed payload. The
header stores a format marker, `xmin`, `xmax`, optional next TID, schema
fingerprint, and payload length. INT64 and FLOAT64 have fixed-width encodings;
BOOLEAN is one canonical byte; TEXT is UTF-8 with a length.

`TupleCodec.decode()` validates every boundary, canonical flag, schema
fingerprint, null bitmap, Boolean byte, UTF-8 sequence, and trailing-byte
condition. A page checksum says the page arrived intact; the tuple codec says
the contained bytes obey this table's immutable schema.

## Buffer frames and pin ownership

Normal relation I/O passes through `BufferPool` in
`src/minipostgres/storage/buffer.py`. It owns a fixed list of `_Frame`s and a
page table mapping `PageKey` to frame ID. Each frame records bytes, page LSN,
pin count, and dirty state.

`BufferPool.fetch_page()` follows two paths. For a resident page it increments
the pin, marks the frame non-evictable, records access, and returns a
`PageGuard`. For a miss it selects a free or evictable frame, flushes the old
dirty occupant, reads and validates the requested page, installs it, pins it,
and returns a guard.

A `PageGuard` owns exactly one pin. Its context-manager exit calls `release()`;
repeated release is harmless, while use after release raises
`DatabaseClosed`. `BufferPool.release_guard()` decrements the pin and makes a
frame evictable only at zero. This is why storage code consistently uses:

```python
with pool.fetch_page(key) as guard:
    ...
```

An all-pinned pool raises `BufferPoolFull`; it must not evict a page still in
use. Dirty publication uses `guard.replace_bytes()` and
`guard.mark_dirty(page_lsn)`. `_flush_frame()` calls the configured WAL flush
gate with the page LSN before `write_page()`, which is the local
WAL-before-data boundary.

## Deterministic Clock replacement

`ClockReplacer` in `src/minipostgres/storage/replacer.py` tracks an evictable
bit and a referenced bit for each frame. `record_access()` sets referenced.
`evict()` circles at most twice through the frame count:

- non-evictable frames are skipped;
- an evictable referenced frame has its reference cleared and receives a
  second chance;
- an evictable unreferenced frame becomes the victim.

The fixed hand and bounded scan make tests deterministic. PostgreSQL's buffer
replacement is concurrency-aware and uses richer usage-count machinery; the
teaching invariant here is that pins prevent eviction and recent use delays
it.

## The approximate free-space map

`FreeSpaceMap` in `src/minipostgres/storage/free_space.py` persists one coarse
free-space category per heap page by writing a temporary sidecar, fsyncing,
atomically replacing, and fsyncing the directory. `candidate_pages()` returns
page IDs whose category may meet a requested size.

The map is a hint, not authority. `HeapTable.insert()` in
`src/minipostgres/storage/heap.py` encodes the tuple and tries candidate pages.
`HeapTable._try_insert()` fetches the real page and calls
`SlottedPage.insert()`. On `PageFull`, it repairs the estimate and continues.
Only after candidates fail does `_insert_new_page()` allocate. On open,
`_bootstrap_free_space()` fills missing entries from actual pages.

This two-level contract makes approximate metadata safe: false positives cost
an extra check, but the page performs the final admission decision.

## Experiment: slots, checksum, and LSN

Run:

```bash
uv run python - <<'PY'
from minipostgres.errors import CorruptPage
from minipostgres.storage.constants import PageKind
from minipostgres.storage.identifiers import heap_page_key
from minipostgres.storage.page import decode_page, encode_page
from minipostgres.storage.slotted import SlottedPage

page = SlottedPage.empty(7)
a = page.insert(b"alpha")
b = page.insert(b"bravo")
c = page.insert(b"charlie")
page.delete(b)
page.compact()
reused = page.insert(b"B")
print("slots", (a, b, c), "live", page.live_slots(), "reused", reused)
print("values", [page.read(slot).decode() for slot in page.live_slots()])
key = heap_page_key(3, 7)
encoded = encode_page(key, PageKind.HEAP, 42, page.to_body())
print("page-bytes", len(encoded), "lsn", decode_page(key, encoded).page_lsn)
broken = bytearray(encoded); broken[-1] ^= 1
try:
    decode_page(key, bytes(broken))
except CorruptPage as error:
    print(type(error).__name__ + ":", error)
PY
```

Observed output:

```text
slots (0, 1, 2) live (0, 1, 2) reused 1
values ['alpha', 'B', 'charlie']
page-bytes 8192 lsn 42
CorruptPage: page checksum mismatch
```

Compaction preserved slots 0 and 2, then insertion reused dead slot 1. The
encoded page is exactly 8192 bytes and retains its LSN. Flipping one padding
bit changes the covered checksum.

Now run the focused buffer evidence:

```bash
uv run pytest -q tests/integration/test_buffer_eviction.py \
  tests/reliability/test_wal_before_data.py::test_heap_change_is_logged_before_dirty_page_can_flush
```

Observed output:

```text
..                                                                       [100%]
2 passed in 0.32s
```

Both commands are socket-free and were runtime-verified.

## Compared with PostgreSQL

PostgreSQL also uses 8 KiB pages by default, line pointers, tuple IDs, shared
buffers, pins, and clock-sweep ideas. The conceptual correspondence is useful,
but these bytes are custom. MiniPostgres page headers, tuple headers,
fingerprints, forks, FSM sidecar, and B+Tree bodies are not PostgreSQL formats.

PostgreSQL shared buffers coordinate processes, use atomic state and usage
counts, and cooperate with background writing. Its FSM is hierarchical and
production-scaled. MiniPostgres is process-local and deterministic. Read the
storage section of [Differences](../differences.md), stops 5–6 in the
[mapping](../postgresql-mapping.md), and the `slotted_page` and `buffer_pool`
rows in the [behavior matrix](../behavior-matrix.md).

## Exercises

### 1. Understanding: stable versus reusable

Why can compaction preserve a TID while dead-slot reuse requires a higher-level
safety decision?

??? note "Reference answer"

    Compaction changes only a live slot's byte extent and updates that slot's
    offset, so `(page_id, slot_id)` still names the same logical version.
    Reuse assigns a dead slot ID to different bytes. MVCC readers or indexes
    must no longer need the old version before that identity is recycled.

### 2. Hands-on: model a full pinned pool

Write a test with a two-frame `BufferPool`, pin two distinct pages, and request
a third. Do not edit `src/`.

Acceptance:

- the third fetch raises `BufferPoolFull`;
- releasing one guard allows the third fetch; and
- all guards are released even if an assertion fails.

??? note "Reference answer"

    Allocate three pages through `DiskManager`, fetch the first two without
    exiting their guards, and use `pytest.raises(BufferPoolFull)` for the
    third. Release the first in `finally`, fetch the third in a `with` block,
    then release the second in the outer `finally`.

### 3. Hands-on design: expose Clock diagnostics

Propose a read-only method that reports the current hand and bit sets for
tests. Keep production code unchanged.

Acceptance:

- the returned object is immutable;
- no caller can mutate replacer state; and
- a test demonstrates referenced frames receive a second chance.

??? note "Reference answer"

    Add a frozen `ClockSnapshot(hand, evictable, referenced)` dataclass and a
    `snapshot()` method returning tuples/frozensets copied under the owner's
    lock. The test marks two frames evictable and referenced, calls `evict()`,
    and checks that reference bits were cleared before a victim was selected.

## Summary

The common page codec validates identity and integrity; a slotted body makes
byte movement independent of stable TIDs; tuple codecs validate schema-shaped
payloads; guards make pins explicit; Clock chooses only unpinned victims; and
the FSM remains safe because the real page decides fit. Chapter 4 adds time:
the same logical row can have several physical versions, and a snapshot decides
which one a transaction may see.
