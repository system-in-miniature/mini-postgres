# Architecture

## Query flow

```text
SQL text
   ↓
Lexer → Parser → syntax AST
                    ↓
                 Binder ← Catalog
                    ↓
              Logical Plan
                    ↓
              Physical Plan
                    ↓
              Volcano Executor
                    ↓
                TableAccess
                    ↓
           IndexedTableAccess
              ↙           ↘
         HeapTable        B+Tree
              ↘           ↙
               Buffer Pool
                    ↓
               DiskManager
```

The parser owns syntax only. The Binder is the first layer allowed to resolve
table aliases, column names, catalog IDs, types, output aliases, aggregate
legality, and contextual `NULL` types.

Logical and physical nodes are immutable. The `Planner` currently performs
baseline lowering: scans are sequential, simple equality joins use hash join,
and other joins use nested loops. Cost-based choices arrive in Phase C.

## Executor ownership

Every executor follows:

```python
open()
next() -> ExecutionRow | None
close()
```

`collect()` guarantees closure after both success and failure. Rows carry
catalog-stable `ColumnBinding` keys, source TIDs for modification operators,
and computed values for projections and aggregates.

Modification executors fully evaluate and validate all candidate rows before
calling `TableAccess`. They never mutate Python table containers directly.

## Stable storage boundary

`TableAccess` owns:

```text
insert
fetch
scan
replace
delete
```

`MemoryTable` remains a testable reference implementation. Normal execution
uses `IndexedTableAccess`, which wraps a `HeapTable` and synchronously maintains
each published B+Tree. Executors do not import the disk manager, fetch pages,
or mutate storage containers directly.

## Page and buffer ownership

Heap and index relation files are arrays of checksummed 8192-byte pages. The
common envelope binds page kind, relation identity, page number, page LSN,
bounds, and checksum. Heap bodies use stable slots:

```text
common page header
→ slotted-page header
→ slot directory growing right
→ free space
← tuple extents growing left
```

Deletion marks a slot dead. Compaction moves tuple bytes and updates extents,
but never renumbers a live slot, so `TID(page_id, slot_id)` stays stable.
Tuple payloads contain a schema fingerprint, `xmin`, `xmax`, optional chain
TID, null bitmap, and schema-directed values.

All normal page I/O passes through the fixed-frame buffer pool. A `PageGuard`
owns one pin and releases it exactly once. Clock eviction can select only
unpinned frames. Dirty flush calls the WAL gate before `DiskManager.write_page`;
until Phase D, the default gate accepts only page LSN zero.

## Heap and index persistence

The approximate free-space map is an atomically replaced sidecar. It may return
false-positive page candidates, but heap insertion always checks the real page,
repairs stale estimates, compacts once, and only then allocates another page.

B+Tree page zero is a metapage. Internal pages contain separator keys and child
IDs; leaves contain sorted `(encoded_key, TID)` pairs plus sibling links.
Splits propagate separators upward, deletion borrows or merges and may collapse
the root, and range iteration pins only its current leaf.

DDL publication follows:

```text
prepare stable catalog identity
→ create/build and fsync physical relation
→ atomic rename when building an index
→ parent-directory fsync
→ publish catalog metadata
```

## Current durability

The catalog writes deterministic, versioned JSON through:

```text
temporary file
→ fsync
→ atomic replace
→ parent-directory fsync
```

Database close flushes every dirty frame, fsyncs published heap/index
relations, and closes descriptors. Reopening reconstructs heap and index access
from catalog IDs. There is no claim of crash-safe atomic DML until WAL and
recovery arrive in Phase D.
