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
- only sequential scans in Phase A;
- deterministic in-memory joins, aggregates, and sorts;
- structured plan objects rather than PostgreSQL EXPLAIN text compatibility.

## Storage

- Phase A rows live in `MemoryTable` and do not survive restart;
- the catalog is deterministic JSON, not transactional system tables;
- later page, heap, B+Tree, and WAL formats are custom and versioned;
- no PostgreSQL page, relation-fork, WAL, checkpoint, or savepoint format
  compatibility is claimed.

## Transactions and maintenance

Transactions, MVCC, locks, WAL recovery, Vacuum, and HOT are accepted later
phases. Their goal is to expose PostgreSQL-shaped invariants, not reproduce
every lock mode, isolation anomaly, WAL record, pruning optimization, or
autovacuum policy.
