# MiniPostgres Tutorial

> [Chinese edition](zh/index.md)

MiniPostgres is a single-process relational database kernel written in Python.
It makes a complete query path inspectable, from SQL parsing and cost-based
planning through Volcano execution, heap and B+Tree storage, MVCC, WAL,
recovery, VACUUM, and HOT updates. It is PostgreSQL-inspired, not PostgreSQL
wire- or SQL-compatible.

## Learning modes

### Mechanism Tutorial

Use the [twelve-chapter tutorial](tutorial/index.md) for concept-first study of
SQL, storage, planning, execution, MVCC, locks, WAL, recovery, VACUUM, and HOT.

### Self-Guided Rebuild

Use the [thirty-stage Journey](journey/index.md) to understand each problem,
test contract, concept boundary, and grouped code diff in a browser.

### Agent-Guided Rebuild

Use the [CLI guide](agent-guide.md) when you want Codex to teach, implement,
explain, and verify one Stage interactively.

## Install

```bash
git clone https://github.com/system-in-miniature/mini-postgres.git
cd mini-postgres
uv sync
```

Python 3.12+ and [uv](https://docs.astral.sh/uv/) are required.

## First experiment

```bash
uv run python examples/demo.py
```

The demo reports an `IndexScan` point-lookup plan, contrasts repeatable-read
snapshots with a fresh view, performs `VACUUM`, checkpoints, reopens the
database, and prints the recovered row.

Continue with the [query-kernel tour](tour.md), then use the
[PostgreSQL mapping](postgresql-mapping.md) to classify each mechanism. The
[repository README](https://github.com/system-in-miniature/mini-postgres/blob/main/README.md)
contains the complete feature and verification reference.
