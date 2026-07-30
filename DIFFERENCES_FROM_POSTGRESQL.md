# Differences from PostgreSQL

> **Language**: English | [简体中文](docs/zh/DIFFERENCES_FROM_POSTGRESQL.md)

MiniPostgres borrows mechanisms and vocabulary from PostgreSQL but deliberately
differs in product scope and implementation.

## Interface

- synchronous Python API instead of a server process;
- no PostgreSQL wire protocol, `psql`, authentication, roles, or privileges;
- a small frozen grammar rather than PostgreSQL's SQL dialect;
- typed Python exceptions rather than PostgreSQL SQLSTATE/error text parity.

## Query engine

- handwritten parser and binder;
- no `HAVING`, `DISTINCT`, `OFFSET`, subqueries, `IN`, `BETWEEN`, `LIKE`,
  `OUTER JOIN`, or column `DEFAULT` values;
- no `DROP TABLE`, `DROP INDEX`, `ALTER`, `SELECT FOR UPDATE`, shared row
  locks, or PostgreSQL-complete lock modes;
- immutable teaching-oriented plan nodes;
- exact full-table `ANALYZE`, rather than PostgreSQL sampling and its full
  statistics catalog;
- a small fixed relative cost model with deterministic defaults;
- sequential and single-column B+Tree scans only;
- connected dynamic-programming join ordering only up to four relations;
- deterministic in-memory joins, aggregates, and sorts;
- structured plan objects rather than PostgreSQL EXPLAIN text compatibility;
- per-node timings are evidence from Python execution, not PostgreSQL cost
  units or production latency predictions.

## Storage

- the catalog is deterministic JSON, not transactional system tables;
- heap and B+Tree relation files use custom checksummed 8192-byte pages;
- heap tuples use a teaching-oriented schema fingerprint and version header,
  not PostgreSQL heap tuple headers or line pointers;
- the buffer pool uses a deterministic Clock policy rather than PostgreSQL's
  shared-buffer replacement and background writer machinery;
- B+Tree pages and ordered key encoding are custom and support a bounded scalar
  subset with no NULL keys or collation framework;
- clean restart and injected-crash REDO use a custom full-page-image WAL;
- WAL, checkpoint, control, and failpoint formats are custom and versioned;
- no PostgreSQL page, relation-fork, WAL, checkpoint, or savepoint format
  compatibility is claimed.

### Why the WAL records whole pages

MiniPostgres appends a complete post-change page image for every logged heap
page mutation. PostgreSQL normally writes a full-page image only on the first
change to a page after each checkpoint when `full_page_writes` is enabled.
That image is attached to the normal resource-manager WAL record; block-local
data may be omitted when the image itself is sufficient. Later changes can use
the normal physiological record stream without another full-page image.

PostgreSQL makes this split because the first image after a checkpoint is
enough to repair a torn page whose older on-disk version belongs to that
checkpoint. Once that protection exists, compact block-local operation records
greatly reduce WAL volume, memory bandwidth, storage traffic, replication
traffic, and recovery I/O while retaining physical page-level REDO. The design
also preserves the resource-manager operation structure instead of reducing
every change to an opaque page replacement. MiniPostgres chooses an image every
time because it makes WAL-before-data and REDO idempotence directly observable,
at the deliberate cost of much larger WAL and without PostgreSQL's
physiological record model.

## Transactions and maintenance

Transactions run inside one process with Read Committed or Repeatable Read.
They do not model PostgreSQL's SSI, subtransactions, savepoints, speculative
insertion, deferrable constraints, composite table constraints, NULL
uniqueness options, or concurrent index build.

Self-joins are rejected explicitly. Runtime column and TID identity is keyed by
catalog table ID, so two aliases of the same relation are not silently treated
as independent relation instances.

Statistics change only through explicit `ANALYZE`; there are no automatic
analyze thresholds, extended statistics, bitmap/index-only paths, or
PostgreSQL planner configuration surface.

Recovery is REDO-only: aborted versions remain physically present and
invisible until Vacuum. Vacuum is explicit, not automatic. HOT is limited to
same-page updates with unchanged index keys rather than PostgreSQL's complete
pruning, visibility-map, freeze, and wraparound machinery.
