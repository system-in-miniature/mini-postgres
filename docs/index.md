# MiniPostgres Tutorial

> English quick start · [中文版](zh/index.md)

MiniPostgres is a single-process relational database kernel written in Python.
It makes a complete query path inspectable—from SQL parsing and cost-based
planning through Volcano execution, heap and B+Tree storage, MVCC, WAL,
recovery, VACUUM, and HOT updates. It is PostgreSQL-inspired, not PostgreSQL
wire- or SQL-compatible.

中文简述：MiniPostgres 用 Python 实现一条可观察的关系数据库内核路径，覆盖
SQL、优化器、执行器、页面/索引、MVCC、WAL 与维护机制；它受 PostgreSQL 启发，
但不兼容 PostgreSQL。

## Install

```bash
git clone https://github.com/system-in-miniature/MiniPostgres.git
cd MiniPostgres
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
[PostgreSQL mapping](postgresql-mapping.md) to classify each mechanism.

For the complete feature and verification reference, read the
[repository README](https://github.com/system-in-miniature/MiniPostgres/blob/main/README.md).
