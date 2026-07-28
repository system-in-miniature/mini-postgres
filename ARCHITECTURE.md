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
               MemoryTable
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

The Phase A `MemoryTable` assigns stable monotonic TIDs and retains tombstones.
Later `HeapTable` implements the same query-facing boundary. Normal execution
must not access heap files, index files, or Python storage lists directly.

## Current persistence

The catalog writes deterministic, versioned JSON through:

```text
temporary file
→ fsync
→ atomic replace
→ parent-directory fsync
```

Only catalog metadata is durable in Phase A. Reopening constructs empty
`MemoryTable` instances for known tables.
