# MiniPostgres

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
→ Physical Plan
→ Volcano Executor
→ TableAccess
```

Phase A uses a retained `MemoryTable` implementation behind `TableAccess`.
Later phases replace the access method with heap pages, a buffer pool, and
B+Tree indexes without rewriting the SQL executor.

## Direct API

```python
from minipostgres import Database

with Database.open("./demo") as db:
    db.execute("CREATE TABLE users (id INT NOT NULL, name TEXT)")
    db.execute("INSERT INTO users VALUES (1, 'Ada'), (2, 'Grace')")
    result = db.execute(
        "SELECT name FROM users WHERE id >= 1 ORDER BY id DESC"
    )
    print(result.columns)
    print(result.rows)
```

`QueryResult` contains immutable `columns`, `rows`, and `command_tag` fields.
`EXPLAIN` additionally returns a structured physical plan. `EXPLAIN` does not
execute its child; `EXPLAIN ANALYZE` does.

## Phase A behavior

Implemented:

- typed catalog metadata that survives restart;
- a bounded SQL lexer and recursive-descent parser;
- catalog-aware binding, SQL three-valued predicates, and `INT64 → FLOAT64`
  widening;
- immutable logical and physical plan trees;
- sequential scans, filters, projections, nested-loop and hash joins;
- grouped and global aggregates, sorting, limits, inserts, updates, deletes;
- structured `EXPLAIN` and executor cleanup after failure.

Catalog metadata is durable in Phase A. Rows are intentionally volatile
because `MemoryTable` is still the access method. Persistent heap storage,
indexes, optimizer statistics, MVCC, WAL, recovery, Vacuum, and HOT belong to
the later accepted phases.

## Verification

```bash
uv sync
uv run ruff check .
uv run pyright src
uv run pytest -q
git diff --check
```

See [SCOPE.md](SCOPE.md), [ARCHITECTURE.md](ARCHITECTURE.md),
[BEHAVIORAL_CONTRACT.md](BEHAVIORAL_CONTRACT.md), and
[DIFFERENCES_FROM_POSTGRESQL.md](DIFFERENCES_FROM_POSTGRESQL.md).

This repository is the finished-reference-project workspace.
The course is designed after the reference project; no chapters, days, quizzes,
or teaching handoffs are generated here.
