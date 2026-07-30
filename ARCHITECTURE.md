# Architecture

> **Language**: English | [简体中文](docs/zh/ARCHITECTURE.md)

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
          Fixed-point Rule Rewriter
                    ↓
      Statistics + Selectivity + Cost Model
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

Logical and physical nodes are immutable. Rules fold literal expressions,
push single-side predicates below inner joins, and annotate the minimum scan
columns. `CostBasedOptimizer` then compares sequential and B+Tree access,
nested-loop and hash joins, and connected join orders for two through four
relations. Larger joins deliberately retain source order.

`ANALYZE` performs one exact educational-scale heap scan and atomically
publishes row/page counts, null fraction, distinct count, deterministic MCVs,
and equi-depth histogram bounds. Selectivity is always clamped to `[0, 1]`;
missing statistics use stable defaults. Costs are relative work units, not
milliseconds. Stale statistics may produce a poor plan but cannot change rows.

The missing-table defaults are 1,000 rows and 10 pages; they permit planning
but not index selection. Unsupported predicate shapes use selectivity `1/3`.
Equality first checks MCVs and then divides residual non-null mass by residual
distinct count. Ranges combine matching MCV mass with histogram interpolation;
`NOT`, `AND`, and `OR` use complement and independence formulas.

The frozen relative constants are:

```text
sequential page = 1.0
random page     = 4.0
CPU tuple       = 0.01
CPU operator    = 0.0025
```

Ties prefer SeqScan and NestedLoop. HashJoin extracts one cross-input equality
key, builds the estimated smaller side, and evaluates the complete ON
predicate as a residual. Join-memo ties then use stable relation IDs and node
kind.

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

`EXPLAIN ANALYZE` wraps every executor without changing its pull contract.
Each wrapper counts emitted rows and monotonic elapsed time across
`open/next/close`; failure still closes every opened delegate. Index scans
iterate candidate TIDs, fetch current heap tuples, and recheck the complete
predicate.

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
heap mutations first append a full-page post-image and install its WAL position
as the page LSN.

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

## Transactions and durability

The catalog writes deterministic, versioned JSON through:

```text
temporary file
→ fsync
→ atomic replace
→ parent-directory fsync
```

Each session owns at most one explicit transaction. Read Committed takes a new
snapshot per statement; Repeatable Read retains its first data snapshot.
Tuple versions carry creator/deleter XIDs. Tuple and unique-key locks serialize
conflicting writers, while a wait-for graph selects deterministic deadlock
victims.

Commit appends and fsyncs its WAL record before publishing committed status or
returning success. Sharp checkpoint ordering is:

```text
flush WAL
→ flush dirty frames
→ fsync relation files
→ append/fsync CHECKPOINT
→ atomic checksummed control-file replace
```

Recovery repairs a torn final WAL record, reconstructs transaction outcomes,
marks incomplete transactions aborted, and REDOs missing, corrupt, or older
heap pages. Indexes are derived state and are rebuilt after unclean recovery.

Vacuum computes a horizon from active snapshots, deletes exact stale index
entries before making a stable slot reusable, compacts page bytes, and logs the
post-image. HOT keeps an indexed root TID when the indexed keys are unchanged
and the replacement fits on its source page.
