# MiniPostgres

[![CI](https://github.com/system-in-miniature/MiniPostgres/actions/workflows/ci.yml/badge.svg)](https://github.com/system-in-miniature/MiniPostgres/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)

> **Language**: [English](README.md) | 简体中文

MiniPostgres 是一个受 PostgreSQL 启发、用 Python 编写的单进程关系数据库内核。
它**不兼容 PostgreSQL**：没有 PostgreSQL 线协议、`psql` 端点，也不宣称具备
完整的 SQL 兼容性。

本项目使以下查询路径可执行、可检查：

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

查询执行器保持存储无关。`MemoryTable` 被保留为小型参考实现，而常规
`Database` 执行通过同一个 `TableAccess` 边界使用持久化堆页面和 B+Tree 索引。

## 直接 API

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

`QueryResult` 包含不可变的 `columns`、`rows` 和 `command_tag` 字段。
`EXPLAIN` 还会返回结构化物理计划。`EXPLAIN` 不执行其子节点；
`EXPLAIN ANALYZE` 会执行。

## 已实现行为

已实现：

- 可跨重启保留的类型化目录元数据；
- 有界 SQL 词法分析器和递归下降解析器；
- 目录感知的绑定、SQL 三值谓词，以及 `INT64 → FLOAT64` 加宽；
- 不可变的逻辑计划树和物理计划树；
- 顺序扫描、过滤、投影、嵌套循环连接和哈希连接；
- 分组与全局聚合、排序、限制、插入、更新、删除；
- 结构化 `EXPLAIN`，以及失败后的执行器清理；
- 带校验和的 8192 字节页面和稳定的分槽堆 TID；
- 由模式指导的元组版本，以及原子替换的空闲空间映射；
- 具有固定帧、固定（pin）状态、脏状态、Clock 淘汰和
  WAL-before-data 刷新闸门的缓冲池（buffer pool）；
- 持久化堆表和基于页面的 B+Tree，支持分裂、合并、点查询和范围迭代；
- `CREATE [UNIQUE] INDEX`、DML 的索引维护、干净重启，以及语句局部的唯一性回滚；
- 针对已接受的单列 `PRIMARY KEY` 和 `UNIQUE` 声明的持久自动唯一索引；
- 精确、持久的 `ANALYZE` 统计信息，包含最常见值（most common values,
  MCV）和等深直方图；
- 有界谓词选择率和显式相对代价模型；
- 常量折叠、过滤下推和扫描列裁剪；
- 基于代价的顺序/索引扫描和嵌套循环/哈希连接；
- 针对二至四个关系的连通动态规划连接排序；
- 结构化 `EXPLAIN ANALYZE` 提供的逐节点估计/实际证据；
- 具有读已提交（Read Committed）和可重复读（Repeatable Read）快照的独立会话；
- `xmin`/`xmax` 元组版本、写者/唯一键锁，以及确定性的死锁受害者恢复；
- 带校验和的全页镜像预写式日志（write-ahead log, WAL）、页面 LSN 强制、
  持久提交、尖锐检查点、尾部修复，以及注入崩溃后的 REDO；
- `VACUUM`，支持快照安全的回收、稳定槽位复用、索引清理，以及索引键未改变时
  的同页仅堆元组更新（heap-only tuple, HOT）。

MiniPostgres 保证成功提交具有持久的提交记录，脏堆页面不能越过其 WAL 记录，
且重启会重放较新的全页镜像，同时将未完成事务视为已中止。DML 后统计信息会保持
陈旧，直到显式执行 `ANALYZE`；错误估计可能选择更慢的计划，但不能改变查询结果行。

## 验证

```bash
uv sync
uv run ruff check .
uv run pyright src
uv run pytest -q
git diff --check
```

参见 [SCOPE.md](docs/zh/SCOPE.md)、
[ARCHITECTURE.md](docs/zh/ARCHITECTURE.md)、
[BEHAVIORAL_CONTRACT.md](BEHAVIORAL_CONTRACT.md) 和
[DIFFERENCES_FROM_POSTGRESQL.md](docs/zh/DIFFERENCES_FROM_POSTGRESQL.md)。
可执行实验索引见 [LABS.md](docs/zh/LABS.md)。

使用以下命令运行确定性的端到端功能导览：

```bash
uv run python examples/demo.py
```

本仓库是已完成参考项目的工作区。课程是在参考项目完成后设计的；这里不会生成
章节、天次、测验或教学交接材料。

## 商标声明

MiniPostgres 是独立的教学项目，与 the PostgreSQL Community Association of Canada 无隶属、背书或赞助关系。"PostgreSQL" 商标归其所有者所有。
