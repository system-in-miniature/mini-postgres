# 范围

> **Language**: [English](../../SCOPE.md) | 简体中文

## 产品边界

MiniPostgres 是进程内关系数据库内核，而不是网络服务。PostgreSQL 18 是语义和
架构参考，不是兼容性目标。

## 阶段 A

阶段 A 接受：

```text
CREATE TABLE
INSERT
SELECT
UPDATE
DELETE
EXPLAIN [ANALYZE]
```

查询子句：

```text
WHERE
INNER JOIN / JOIN
GROUP BY
ORDER BY [ASC|DESC] [NULLS FIRST|LAST]
LIMIT
```

聚合：

```text
COUNT
SUM
AVG
MIN
MAX
```

类型：

```text
INT64 (INT, INTEGER, BIGINT syntax)
FLOAT64 (FLOAT syntax)
BOOLEAN
TEXT
NULL
```

`NOT NULL`、`PRIMARY KEY` 和 `UNIQUE` 会被解析为元数据。阶段 A 强制执行
`NOT NULL`。

## 阶段 B

阶段 B 增加：

```text
CREATE [UNIQUE] INDEX
checksummed fixed pages
stable slotted heap storage
buffer pool and Clock eviction
persistent B+Tree indexes
clean close and restart
```

冻结的索引子集拒绝 NULL 键。显式唯一 B+Tree 索引在单进程语句锁存器下强制
执行。已接受的单列 `PRIMARY KEY` 和内联 `UNIQUE` 声明会创建自动唯一
B+Tree 索引。复合约束仍不在此阶段范围内。

## 阶段 C

阶段 C 增加：

```text
ANALYZE [table]
durable exact table and column statistics
fixed-point logical rewrites
sequential versus B+Tree index scan costing
nested-loop versus hash join costing
connected inner-join ordering for two through four relations
per-node EXPLAIN ANALYZE instrumentation
```

代价是相对比较值，而不是毫秒。DML 会刻意让统计信息保持陈旧，直到下一次显式
执行 `ANALYZE`。五个或更多关系的连接保留源顺序。

## 阶段 D

阶段 D 增加事务、语句/事务快照、元组版本、写者锁、死锁检测、带校验和的
WAL、尖锐检查点（sharp checkpoint）和 REDO 恢复。

## 阶段 E

阶段 E 增加显式 `VACUUM`、清理水位（cleanup horizon）、稳定槽位复用前的
索引清理、不改变 TID 编号的页面压缩、索引键未改变时的同页 HOT 更新，以及
最终验收证据。

## 非目标

- PostgreSQL 线协议或磁盘格式兼容；
- 完整的 PostgreSQL 语法、类型转换、错误、排序规则或系统目录；
- `HAVING`、`DISTINCT`、`OFFSET`、子查询、`IN`、`BETWEEN`、`LIKE` 和
  `OUTER JOIN`；
- 列 `DEFAULT` 值；
- `DROP TABLE`、`DROP INDEX` 和 `ALTER`；
- `SELECT FOR UPDATE`、共享行锁和 PostgreSQL 完整的锁模式族；
- 用户、权限、外键、视图、触发器、存储过程；
- 并行查询、多个服务器进程、复制或逻辑解码；
- 完整的 ARIES/UNDO、TOAST、SSI、XID 回卷/冻结、保存点或生产级自动清理；
- PostgreSQL 完整的 HOT 链剪枝或兼容的 WAL/检查点格式；
- 参考仓库内的课程内容。
