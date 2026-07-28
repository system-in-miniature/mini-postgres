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
enforces `NOT NULL`; concurrency-safe primary/unique enforcement starts with
the indexed storage phases.

## Accepted later phases

- Phase B: slotted pages, tuple codecs, disk manager, buffer pool, heap, B+Tree.
- Phase C: statistics, index scans, costing, rewrites, join selection/order.
- Phase D: transactions, snapshots, locks, MVCC, WAL, checkpoint, recovery.
- Phase E: Vacuum, stable-slot reuse, compaction, HOT, differential and final
  acceptance.

## Non-goals

- PostgreSQL wire or on-disk compatibility;
- complete PostgreSQL grammar, casts, errors, collations, or system catalogs;
- users, privileges, foreign keys, views, triggers, stored procedures;
- parallel query, multiple server processes, replication, or logical decoding;
- full ARIES, TOAST, SSI, XID wraparound, or production autovacuum;
- course content inside the reference repository.
