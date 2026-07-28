# Differences from PostgreSQL

MiniPostgres borrows mechanisms and vocabulary from PostgreSQL but deliberately
differs in product scope and implementation.

## Interface

- synchronous Python API instead of a server process;
- no PostgreSQL wire protocol, `psql`, authentication, roles, or privileges;
- a small frozen grammar rather than PostgreSQL's SQL dialect;
- typed Python exceptions rather than PostgreSQL SQLSTATE/error text parity.

## Query engine

- handwritten parser and binder;
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
