# MiniPostgres Tutorial / MiniPostgres 教程

> English quick start / 英文快速开始 · [Chinese edition / 中文版](zh/index.md)

MiniPostgres is a single-process relational database kernel written in Python.
It makes a complete query path inspectable—from SQL parsing and cost-based
planning through Volcano execution, heap and B+Tree storage, MVCC, WAL,
recovery, VACUUM, and HOT updates. It is PostgreSQL-inspired, not PostgreSQL
wire- or SQL-compatible.

MiniPostgres 是一个用 Python 编写的单进程关系数据库内核。它让完整查询路径
可检查：从 SQL 解析、代价优化和 Volcano 执行，到堆/B+Tree 存储、MVCC、
WAL、恢复、VACUUM 与 HOT 更新。它受 PostgreSQL 启发，但不兼容 PostgreSQL
线协议或完整 SQL。

## Install / 安装

```bash
git clone https://github.com/system-in-miniature/MiniPostgres.git
cd MiniPostgres
uv sync
```

Python 3.12+ and [uv](https://docs.astral.sh/uv/) are required.

需要 Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)。

## First experiment / 第一个实验

```bash
uv run python examples/demo.py
```

The demo reports an `IndexScan` point-lookup plan, contrasts repeatable-read
snapshots with a fresh view, performs `VACUUM`, checkpoints, reopens the
database, and prints the recovered row.

示例会报告点查使用的 `IndexScan`，对比可重复读快照与新视图，执行
`VACUUM` 和 checkpoint，重新打开数据库，并打印恢复出的行。

Continue with the [query-kernel tour](tour.md), then use the
[PostgreSQL mapping](postgresql-mapping.md) to classify each mechanism.

接着阅读[查询内核导览](tour.md)，再用
[PostgreSQL 机制映射](postgresql-mapping.md)给每个机制分类。

For the complete feature and verification reference, read the
[repository README](https://github.com/system-in-miniature/MiniPostgres/blob/main/README.md).

完整功能和验证参考见
[仓库中文 README](https://github.com/system-in-miniature/MiniPostgres/blob/main/README.zh-CN.md)。
