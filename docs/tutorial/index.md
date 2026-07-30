# MiniPostgres: A Database Kernel in Twelve Chapters

This is the main textbook for MiniPostgres. Read it in order to follow one
relational kernel from SQL text to verified behavior. Each chapter names its
source owners, runs copyable experiments, and states where the teaching model
differs from PostgreSQL.

MiniPostgres is a synchronous, single-process Python database kernel. It is not
a PostgreSQL-compatible server: there is no wire protocol, `psql`, production
file-format compatibility, or complete SQL dialect. Use the chapters to learn
mechanisms, then use the reference material to inspect exact project scope and
evidence.

## Book contents

1. [Meet MiniPostgres](01-getting-started.md) — position, environment, the
   direct `Database` API, and the full-book map.
2. [The SQL Front End](02-sql-frontend.md) — positioned lexing,
   recursive-descent parsing, catalog-aware binding, three-valued logic, and
   numeric widening.
3. [Pages and the Buffer Pool](03-storage.md) — checksummed 8192-byte pages,
   stable slotted-page TIDs, pin ownership, Clock replacement, and the
   free-space map.
4. [MVCC, Tuple Versions, and Snapshots](04-mvcc.md) — `xmin`/`xmax` history,
   creator/deleter visibility, snapshots, Read Committed, and Repeatable Read.
5. [Persistent B+Tree Indexes](05-btree.md) — ordered key encoding, point and
   range access, split propagation, borrowing, merging, root contraction, and
   unique-build visibility.
6. [Statistics and Cost-Based Planning](06-planning.md) — exact ANALYZE,
   MCVs and histograms, selectivity, SeqScan/IndexScan crossover, bounded join
   dynamic programming, and EXPLAIN.
7. [Volcano Execution](07-execution.md) — executor trees, pull-based
   `open/next/close`, expression evaluation with INT64 semantics, and
   `EXPLAIN ANALYZE`.
8. [Isolation Levels, Write Conflicts, and EPQ](08-isolation.md) — snapshot
   policy, serialization conflicts, and post-wait predicate rechecks.
9. [Locks and Deterministic Deadlock Detection](09-locks-deadlock.md) — FIFO
   tuple/key locks, wait-for graphs, and deterministic victim selection.
10. [WAL, Checkpoints, and Recovery](10-wal-recovery.md) — full-page images,
    LSN gates, sharp checkpoints, torn-tail repair, and REDO-only recovery.
11. [VACUUM and HOT](11-vacuum-hot.md) — reclamation horizons, index cleanup,
    stable-slot reuse, HOT chains, and pruning.
12. [Testing Methodology](12-testing-methodology.md) — the repository's five
    verification layers and differential checking against PostgreSQL 18.

## How to use the book

Run commands from the repository root with `uv run`. Chapter outputs are
observations from this tree, not illustrative guesses. Exercises never require
you to edit the tutorial's `src/` tree in place: make proposed diffs in a
throwaway branch or reason from the folded reference answer, and use each
exercise's acceptance checks.

For claims outside the chapter narrative, continue to:

- [Differences from PostgreSQL](../differences.md);
- [MiniPostgres → PostgreSQL mapping](../postgresql-mapping.md);
- [behavior matrix](../behavior-matrix.md);
- [architecture reference](../architecture-reference.md); and
- [labs and focused test nodes](../labs-guide.md).

Start with [Chapter 1](01-getting-started.md).
