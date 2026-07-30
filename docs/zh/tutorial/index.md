# MiniPostgres：十二章数据库内核教材

这是 MiniPostgres 的主教材。请按顺序阅读，从 SQL 文本一路走到可验证行为。每章都会指出源码所有者，提供可复制且实测过的实验，并明确教学模型与 PostgreSQL 的边界。

MiniPostgres 是同步、单进程的 Python 数据库内核，不是 PostgreSQL 兼容服务器：它没有线协议、`psql`、生产文件格式兼容或完整 SQL 方言。用正文学习机制，再用参考资料核对精确范围与证据。

## 全书目录

1. [认识 MiniPostgres](01-getting-started.md)——定位、环境、direct `Database`
   API 与全书地图。
2. [SQL 前端](02-sql-frontend.md)——带位置 lexer、递归下降 parser、目录感知
   binder、三值逻辑与数值加宽。
3. [页与缓冲](03-storage.md)——带校验和的 8192-byte page、稳定 slotted-page
   TID、pin 所有权、Clock 淘汰与 FSM。
4. [MVCC、元组版本与快照](04-mvcc.md)——`xmin`/`xmax` 历史、创建/删除可见性、
   snapshot、Read Committed 与 Repeatable Read。
5. [B+Tree 索引](05-btree.md)——有序 key 编码、点查/range、split propagation、
   借用、合并、root contraction 与 unique build visibility。
6. [代价规划](06-planning.md)——精确 ANALYZE、MCV/histogram、selectivity、
   SeqScan/IndexScan crossover、有界 join DP 与 EXPLAIN。
7. [Volcano 执行](07-execution.md)——executor tree、pull-based
   `open/next/close`、INT64 表达式语义与 `EXPLAIN ANALYZE`。
8. [隔离级别、写冲突与 EPQ](08-isolation.md)——snapshot policy、
   serialization conflict 与等待后的谓词重查。
9. [锁与确定性死锁检测](09-locks-deadlock.md)——FIFO tuple/key lock、
   wait-for graph 与确定性 victim。
10. [WAL、Checkpoint 与恢复](10-wal-recovery.md)——full-page image、LSN gate、
    sharp checkpoint、torn-tail 修复与 REDO-only recovery。
11. [VACUUM 与 HOT](11-vacuum-hot.md)——reclamation horizon、index cleanup、
    稳定槽复用、HOT chain 与 pruning。
12. [验证方法论](12-testing-methodology.md)——仓库五层验证，以及与
    PostgreSQL 18 的差分检查。

## 如何使用

所有命令都从仓库根目录以 `uv run` 执行；章节输出来自当前工作树实测，而非示意猜测。练习不要求直接修改教程仓库的 `src/`：可以在临时分支提出 diff，或展开参考答案进行推演，并用每题验收项检查结果。

正文之外，请继续查阅：

- [与 PostgreSQL 的差异](../DIFFERENCES_FROM_POSTGRESQL.md)；
- [MiniPostgres → PostgreSQL 映射](../postgresql-mapping.md)；
- [行为矩阵](../BEHAVIOR_MATRIX.md)；
- [架构参考](../ARCHITECTURE.md)；
- [实验与聚焦测试节点](../labs-guide.md)。

从[第 1 章](01-getting-started.md)开始。
