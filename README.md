# MiniPostgres

[![CI](https://github.com/system-in-miniature/mini-postgres/actions/workflows/ci.yml/badge.svg)](https://github.com/system-in-miniature/mini-postgres/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)

> **Language**: English | [简体中文](README.zh-CN.md)

MiniPostgres is a PostgreSQL-inspired, single-process relational database
kernel written in Python. It is **not PostgreSQL-compatible**: there is no
PostgreSQL wire protocol, `psql` endpoint, or claim of complete SQL
compatibility.

The project makes this query path executable and inspectable:

```text
SQL
→ Lexer / Parser
→ Binder
→ Logical Plan
→ Rule Rewriter / Cost Optimizer
→ Physical Plan
→ Volcano Executor
→ TableAccess
→ Heap / B+Tree
→ Buffer Pool
→ Fixed Relation Pages / WAL
```

The query executor remains storage-independent. `MemoryTable` is retained as a
small reference implementation, while normal `Database` execution uses
persistent heap pages and B+Tree indexes through the same `TableAccess`
boundary.

## Direct API

```python
from minipostgres import Database

with Database.open("./demo") as db:
    db.execute("CREATE TABLE users (id INT NOT NULL, name TEXT)")
    db.execute("INSERT INTO users VALUES (1, 'Ada'), (2, 'Grace')")
    db.execute("CREATE UNIQUE INDEX users_id ON users (id)")
    result = db.execute(
        "SELECT name FROM users WHERE id >= 1 ORDER BY id DESC"
    )
    print(result.columns)
    print(result.rows)
```

`QueryResult` contains immutable `columns`, `rows`, and `command_tag` fields.
`EXPLAIN` additionally returns a structured physical plan. `EXPLAIN` does not
execute its child; `EXPLAIN ANALYZE` does.

## Implemented behavior

Implemented:

- typed catalog metadata that survives restart;
- a bounded SQL lexer and recursive-descent parser;
- catalog-aware binding, SQL three-valued predicates, and `INT64 → FLOAT64`
  widening;
- immutable logical and physical plan trees;
- sequential scans, filters, projections, nested-loop and hash joins;
- grouped and global aggregates, sorting, limits, inserts, updates, deletes;
- structured `EXPLAIN` and executor cleanup after failure;
- checksummed 8192-byte pages and stable slotted heap TIDs;
- schema-directed tuple versions and atomically replaced free-space maps;
- fixed-frame buffer pool with pins, dirty state, Clock eviction, and a
  WAL-before-data flush gate;
- persistent heap tables and page-based B+Trees with split, merge, point
  lookup, and range iteration;
- `CREATE [UNIQUE] INDEX`, index maintenance for DML, clean restart, and
  statement-local uniqueness rollback;
- durable automatic unique indexes for accepted single-column `PRIMARY KEY`
  and `UNIQUE` declarations;
- exact, durable `ANALYZE` statistics with MCV and equi-depth histograms;
- bounded predicate selectivity and an explicit relative cost model;
- constant folding, filter pushdown, and scan-column pruning;
- cost-based sequential/index scans and nested-loop/hash joins;
- connected dynamic-programming join ordering for two through four relations;
- per-node estimated/actual evidence from structured `EXPLAIN ANALYZE`.
- independent sessions with Read Committed and Repeatable Read snapshots;
- `xmin`/`xmax` tuple versions, writer/unique-key locks, and deterministic
  deadlock victim recovery;
- checksummed full-page-image WAL, page LSN enforcement, durable commit,
  sharp checkpoints, tail repair, and REDO after injected crashes;
- `VACUUM` with snapshot-safe reclamation, stable-slot reuse, index cleanup,
  and same-page HOT updates when indexed keys are unchanged.

MiniPostgres guarantees that a successful commit has a durable commit record,
dirty heap pages cannot pass their WAL record, and restart replays newer
full-page images while treating incomplete transactions as aborted. Statistics
remain stale after DML until explicit `ANALYZE`; a bad estimate may select a
slower plan but cannot change query rows.

## Verification & Benchmarks

```bash
uv sync
uv run ruff check .
uv run pyright src
uv run pytest -q
git diff --check
```

On 2026-08-04, `/usr/bin/time -p .venv/bin/python -m pytest -q` completed
with **286 passed, 1 skipped, and 0 failed**; the skip was the optional
PostgreSQL 18 differential profile because no DSN was configured.

Under the dated local protocol:

- the B+Tree equality lookup was **5,816.64x** faster than a sequential scan
  on the same 100,000-row logical dataset;
- checkpointed WAL scan + REDO was **3.43x-4.40x** faster and redid zero heap
  pages;
- real `VACUUM` improved the 100,000-row median scan by **1.04x** after
  removing 5,000 dead versions.

See the [benchmark protocol](bench/PROTOCOL.md) and
[dated report](bench/results/2026-08-04/report.md). This is a methodology
benchmark of an educational kernel; it makes no absolute-value claims.

**Benchmark-discovered fix.** Unclean startup rebuilt a predecessor map once
per HOT-chain root, turning an N-row heap scan into **O(N^2)** work. Reusing one
TID map makes the rebuild **O(N)**; complete `Database.open` at 10,000 rows
changed from **449,100.98 ms to 71.83 ms (6,252.45x)**. The
[postfix result and root-cause diagnosis](bench/results/2026-08-04-postfix/report.md)
also preserve timeout-bounded 50,000- and 100,000-row baselines.

See [SCOPE.md](SCOPE.md), [ARCHITECTURE.md](ARCHITECTURE.md),
[BEHAVIORAL_CONTRACT.md](BEHAVIORAL_CONTRACT.md), and
[DIFFERENCES_FROM_POSTGRESQL.md](DIFFERENCES_FROM_POSTGRESQL.md). Executable
experiments are indexed in [LABS.md](LABS.md).

Run the deterministic end-to-end feature tour with:

```bash
uv run python examples/demo.py
```

This repository is the finished-reference-project workspace.
The course is designed after the reference project; no chapters, days, quizzes,
or teaching handoffs are generated here.

## Trademark Notice

MiniPostgres is an independent educational project. It is not affiliated with, endorsed by, or sponsored by the PostgreSQL Community Association of Canada. "PostgreSQL" is a trademark of its respective owner.
