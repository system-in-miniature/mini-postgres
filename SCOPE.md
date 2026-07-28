# Scope

## Product boundary

MiniPostgres is an in-process relational database kernel, not a network
service. PostgreSQL 18 is the semantic and architectural reference, not a
compatibility target.

## Phase A

Phase A accepts:

```text
CREATE TABLE
INSERT
SELECT
UPDATE
DELETE
EXPLAIN [ANALYZE]
```

Query clauses:

```text
WHERE
INNER JOIN / JOIN
GROUP BY
ORDER BY [ASC|DESC] [NULLS FIRST|LAST]
LIMIT
```

Aggregates:

```text
COUNT
SUM
AVG
MIN
MAX
```

Types:

```text
INT64 (INT, INTEGER, BIGINT syntax)
FLOAT64 (FLOAT syntax)
BOOLEAN
TEXT
NULL
```

`NOT NULL`, `PRIMARY KEY`, and `UNIQUE` are parsed into metadata. Phase A
enforces `NOT NULL`.

## Phase B

Phase B adds:

```text
CREATE [UNIQUE] INDEX
checksummed fixed pages
stable slotted heap storage
buffer pool and Clock eviction
persistent B+Tree indexes
clean close and restart
```

The frozen index subset rejects NULL keys. Explicit unique B+Tree indexes are
enforced under the single-process statement latch. Accepted single-column
`PRIMARY KEY` and inline `UNIQUE` declarations create automatic unique B+Tree
indexes. Composite constraints remain outside this phase.

## Phase C

Phase C adds:

```text
ANALYZE [table]
durable exact table and column statistics
fixed-point logical rewrites
sequential versus B+Tree index scan costing
nested-loop versus hash join costing
connected inner-join ordering for two through four relations
per-node EXPLAIN ANALYZE instrumentation
```

Costs are relative comparisons, not milliseconds. DML deliberately leaves
statistics stale until the next explicit `ANALYZE`. Five or more joined
relations retain source order.

## Phase D

Phase D adds transactions, statement/transaction snapshots, tuple versions,
writer locks, deadlock detection, checksummed WAL, sharp checkpoints, and
REDO recovery.

## Phase E

Phase E adds explicit `VACUUM`, cleanup horizons, index cleanup before
stable-slot reuse, page compaction without TID renumbering, same-page HOT
updates for unchanged index keys, and final acceptance evidence.

## Non-goals

- PostgreSQL wire or on-disk compatibility;
- complete PostgreSQL grammar, casts, errors, collations, or system catalogs;
- users, privileges, foreign keys, views, triggers, stored procedures;
- parallel query, multiple server processes, replication, or logical decoding;
- full ARIES/UNDO, TOAST, SSI, XID wraparound/freeze, savepoints, or
  production autovacuum;
- PostgreSQL-complete HOT-chain pruning or compatible WAL/checkpoint formats;
- course content inside the reference repository.
