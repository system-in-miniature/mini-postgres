# Chapter 5 — Persistent B+Tree Indexes

A heap answers “what row version lives at this TID?” An index answers “which
TIDs might match this key?” MiniPostgres implements a persistent page-based
B+Tree sorted multimap. It supports point lookup, inclusive ranges, recursive
splits, sibling borrowing, merging, and root contraction while keeping heap
visibility as the final authority.

## Learning objectives

After this chapter, you can:

1. describe the metapage, internal page, and linked-leaf layouts;
2. explain why keys require order-preserving byte encoding;
3. trace an insert from leaf search through root creation;
4. distinguish redistribution, merge, and root contraction during deletion;
   and
5. explain why an index scan must fetch and recheck heap tuples.

## One relation, three page kinds

`BTree.open()` in `src/minipostgres/index/btree.py` owns tree bootstrap. An
empty index relation receives page 0 as `BTREE_META` and page 1 as an empty
`BTREE_LEAF`. The metapage records root page ID and height. A one-level tree
has the leaf as root. Existing trees decode page 0 and validate that the root
is allocated.

The body dataclasses and codecs are in `src/minipostgres/index/pages.py`:

- `MetaPage(root_page_id, height)` identifies traversal state;
- `InternalPage(keys, children)` requires exactly one more child than key;
- `LeafPage(entries, left_sibling, right_sibling)` stores sorted
  `LeafEntry(key, tid)` values.

`encode_internal()` checks separator order and the child-count invariant.
`encode_leaf()` checks `(key, tid.page_id, tid.slot_id)` order. Both use the
common checksummed 8192-byte envelope from Chapter 3, so page identity and kind
are validated again at read time.

Leaves carry both sibling directions. Point lookup may move left when equal
keys span pages; range iteration walks right. Internal pages guide descent but
do not contain heap TIDs.

## Byte order must be value order

The tree compares `bytes`, so `KeyCodec` in
`src/minipostgres/index/key.py` must make lexicographic byte order match the
supported SQL scalar order.

INT64 encoding flips the signed domain by adding the sign bit before emitting
big-endian bytes. FLOAT64 encoding complements negative bit patterns and flips
the sign bit for nonnegative values; NaN is rejected. BOOLEAN emits a tag and
0/1. TEXT emits UTF-8 with zero escaping and a terminator. Type tags keep
components unambiguous, and composite encodings concatenate components.

NULL index keys are outside the frozen scope. This is an explicit difference
from PostgreSQL, whose B-Tree operator classes, NULL ordering, collations, and
type-specific semantics are far richer.

## Search

`BTree._find_leaf(key)` begins at `_root_page_id`. For each internal level it
uses `bisect_right(internal.keys, key)` to choose a child and records
`(parent_page_id, child_index)` in the path. The path becomes split-propagation
evidence.

`search()` first finds a candidate leaf, then follows left siblings while the
previous leaf might contain the same key. It collects equal-key TIDs across
right siblings until keys have passed the target, deduplicates, and sorts by
physical TID. The structure is a multimap: the same key may identify several
heap rows. Inserting an identical key/TID twice is idempotent.

## Insertion and splitting

`BTree.insert()` rejects an already-present pair, finds a leaf, and inserts a
`LeafEntry` at the bisected `(key, page_id, slot_id)` position. It tries
`encode_leaf(updated)`. Successful encoding proves the body fits and is
written in place.

If the codec raises `PageFull`, `_split_leaf()` chooses a byte-aware split
position, not merely a count midpoint. It allocates a right leaf, divides
entries, repairs left/right sibling links, writes both sides, and returns the
new right leaf's first key as separator.

`_propagate_split()` consumes the saved parent path upward. It inserts the
separator and new child into the parent. An overflowing internal page is split
around a middle key by `_split_internal()`; that key is promoted rather than
retained in either child. If the path empties, the function allocates a new
internal root, increments height, and persists the metapage.

The essential invariant is routing: separators and child positions must send
every search to a leaf range that can contain the key. `_refresh_all_separators()`
later restores separators after deletion changes subtree minima.

## Range iteration and pins

`BTree.range(lower, upper)` returns `BTreeRangeIterator` from
`src/minipostgres/index/iterator.py`. Construction loads the leftmost possible
leaf. `__next__()` skips entries below the inclusive lower bound, yields until
the upper bound is passed, then closes. At leaf exhaustion it loads the right
sibling.

`_load()` releases the previous `PageGuard` before pinning the next leaf.
Therefore a long range holds at most one leaf pin. The iterator is a context
manager, and `close()` is idempotent. This is not cosmetic: forgetting a pin
can make a bounded buffer pool appear full.

## Deletion, borrowing, merging, and root contraction

`BTree.delete()` locates the exact key/TID pair, reconstructs a root path,
removes only that entry, writes the leaf, and calls `_rebalance_leaf()`.

An underfull non-root leaf first tries redistribution. It may borrow the last
entry from the left sibling or the first from the right, provided the donor
remains at least half full and the recipient still fits. The parent separator
is updated with the new subtree minimum.

If borrowing is impossible, it tries merge. Merging with the left or right
sibling combines entries, repairs the surviving leaf link, removes one child
and separator from the parent, and invokes `_rebalance_internal()`.
Internal rebalancing follows the same preference: borrow, then merge.

When the root internal page has only one child, `_rebalance_internal()` makes
that child the new root, decrements height, and writes the metapage. Physical
orphan pages are not reclaimed into a general allocator; logical reachability
and correct search are the contract.

## Index publication and visibility

`Database._create_index()` in `src/minipostgres/engine.py` prepares a stable
catalog identity, builds a tree in a temporary directory from globally live
heap rows, checks uniqueness when requested, flushes and syncs the relation,
atomically renames it into place, fsyncs the directory, and only then publishes
catalog metadata. A publication failure removes the target file.

Normal DML uses `IndexedTableAccess` in
`src/minipostgres/storage/indexed.py` to maintain published indexes beside the
heap. An index entry is still a candidate. MVCC can make its TID invisible or
redirect resolution along a version chain, so an executor fetches the heap
tuple and rechecks the complete predicate. The index accelerates discovery; it
does not decide visibility or final truth.

Unique indexes additionally coordinate key locks and validate live heap state.
The B+Tree class itself remains a multimap and does not embed transaction
policy.

## Experiment: grow and shrink a tree

Run:

```bash
uv run python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres.index.btree import BTree
from minipostgres.index.key import KeyCodec
from minipostgres.row import TID
from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.disk import DiskManager
from minipostgres.types import DataType

codec = KeyCodec((DataType.INT64,))
with TemporaryDirectory() as root:
    disk = DiskManager.open(root)
    tree = BTree.open(BufferPool(disk, frame_count=5), index_id=1)
    for value in range(500):
        tree.insert(codec.encode((value,)), TID(value // 10, value % 10))
    print("height-after-insert", tree.height)
    print("search-42", tree.search(codec.encode((42,))))
    with tree.range(codec.encode((40,)), codec.encode((43,))) as entries:
        print("range-40-43", [tid for _, tid in entries])
    for value in range(499):
        tree.delete(codec.encode((value,)), TID(value // 10, value % 10))
    print("height-after-delete", tree.height)
    print("search-499", tree.search(codec.encode((499,))))
    disk.close()
PY
```

Observed output:

```text
height-after-insert 2
search-42 (TID(page_id=4, slot_id=2),)
range-40-43 [TID(page_id=4, slot_id=0), TID(page_id=4, slot_id=1), TID(page_id=4, slot_id=2), TID(page_id=4, slot_id=3)]
height-after-delete 1
search-499 (TID(page_id=49, slot_id=9),)
```

Five hundred entries forced a leaf split and internal root. Deleting all but
the maximum triggered redistribution/merge paths until the tree contracted to
one leaf.

The persistence and deletion evidence also runs directly:

```bash
uv run pytest -q tests/integration/test_btree_restart.py \
  tests/unit/index/test_btree_delete.py
```

Observed output:

```text
....                                                                     [100%]
4 passed in 2.72s
```

No socket is involved; both experiments were runtime-verified.

## Compared with PostgreSQL

PostgreSQL's `src/backend/access/nbtree/` also has metapage state, internal and
leaf pages, splits, sibling traversal, deletion maintenance, and heap TID
references. That algorithmic vocabulary is the correspondence.

MiniPostgres omits concurrent page-lock protocols, high keys and robust
right-link traversal, deduplication, suffix truncation, operator classes,
collations, NULL keys, posting lists, vacuum-cycle machinery, index-only
scans, and crash-safe physiological WAL for index changes. Its custom key and
page formats are incompatible. Consult the storage section of
[Differences](../differences.md), stop 7 of the
[mapping](../postgresql-mapping.md), and the `btree` row in the
[behavior matrix](../behavior-matrix.md).

## Exercises

### 1. Understanding: separator promotion

Why does a leaf split copy the right leaf's first key upward, while an internal
split removes its middle key from both children?

??? note "Reference answer"

    Leaves retain all data entries; the parent stores a routing copy of the
    right minimum. Internal keys are routing separators themselves. Promoting
    the middle separator divides its left and right child ranges without
    duplicating a routing key in a child.

### 2. Understanding: candidate versus answer

Why can `search(key)` return a TID that a query must not emit?

??? note "Reference answer"

    The referenced heap version may be invisible to the query snapshot, may
    lead to a newer visible version, or may fail a residual predicate. The
    index is maintained access state, while heap MVCC and expression recheck
    determine the final row.

### 3. Hands-on: duplicate-key multimap

Write a standalone test inserting three different TIDs under key 7, including
one duplicate insertion. Verify sorted idempotent search and deletion of only
the middle TID.

Acceptance:

- search returns three distinct TIDs in `(page_id, slot_id)` order;
- reinserting one pair changes nothing; and
- deletion leaves the other two.

??? note "Reference answer"

    Use `KeyCodec((DataType.INT64,))`, a temporary `DiskManager`, and
    `BTree.open()`. Insert `TID(2, 3)`, `TID(0, 9)`, and `TID(1, 1)`, insert
    `TID(2, 3)` again, then call `delete(key, TID(1, 1))`.

### 4. Hands-on design: reclaim orphan pages

Propose, but do not implement, a free-page mechanism for pages made unreachable
by merge.

Acceptance:

- define whether free state lives in the metapage or a separate fork;
- state the crash/publication ordering; and
- include a restart test and a page-reuse test.

??? note "Reference answer"

    A separate versioned free-page sidecar keeps the teaching metapage small.
    Publish tree structural changes durably before adding an unreachable page
    to the free set; when reusing, remove and persist the free entry before
    exposing new links. Tests should force merges, close/reopen, verify all
    searches, then insert enough data to prove relation page count does not
    grow until the free supply is exhausted.

## Summary

The MiniPostgres B+Tree is a persistent ordered multimap: page 0 locates the
root, internal separators route searches, linked leaves store key/TID pairs,
insertion propagates splits, deletion borrows or merges, and a one-child root
contracts. Order-preserving keys make byte comparison meaningful, but heap
visibility remains authoritative. Chapter 6 asks when using this index is
cheaper than reading the heap sequentially.
