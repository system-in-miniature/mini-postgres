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
- clean close/restart is supported, but crash recovery is not yet claimed;
- WAL formats arriving later remain custom and versioned;
- no PostgreSQL page, relation-fork, WAL, checkpoint, or savepoint format
  compatibility is claimed.

## Transactions and maintenance

Phase C statements are serialized inside one process. Unique checks are
statement-local and do not model PostgreSQL's speculative insertion,
deferrable constraints, composite table constraints, NULL uniqueness options,
or concurrent index build.

Statistics change only through explicit `ANALYZE`; there are no automatic
analyze thresholds, extended statistics, bitmap/index-only paths, or
PostgreSQL planner configuration surface.

Transactions, MVCC, locks, WAL recovery, Vacuum, and HOT are accepted later
phases. Their goal is to expose PostgreSQL-shaped invariants, not reproduce
every lock mode, isolation anomaly, WAL record, pruning optimization, or
autovacuum policy.
