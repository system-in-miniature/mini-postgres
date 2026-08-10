# 自主重建

每个 Stage 都是一节可独立浏览的完整课：先理解当前问题、基本概念与必要性，再按机制板块连接相关文件和关键语句，最后用验证证据和自己的话完成理解闭环。

这是三种学习模式中的浏览器自主学习路径。按主题学习请进入[机制教程](../index.md)；需要 CLI 互动请查看 [Agent 带教使用教程](../agent-guide.md)。

如果希望在编辑器里聚焦当前增量，运行 `python -m journey.tools.build_journey study N`，再打开 `../MiniPostgres-journey-workspace`。

| Stage | 主题 | 新增测试 | 教材章节 |
|---:|---|---:|---:|
| [01](stage-01.md) | 值与行契约 | 2 | [1](../tutorial/01-getting-started.md) |
| [02](stage-02.md) | 持久化类型目录 | 2 | [1](../tutorial/01-getting-started.md) |
| [03](stage-03.md) | 冻结 SQL 词法器 | 2 | [2](../tutorial/02-sql-frontend.md) |
| [04](stage-04.md) | 感知优先级的 SQL Parser | 3 | [2](../tutorial/02-sql-frontend.md) |
| [05](stage-05.md) | 名称与类型绑定 | 3 | [2](../tutorial/02-sql-frontend.md) |
| [06](stage-06.md) | 逻辑与物理计划 | 2 | [6](../tutorial/06-planning.md) |
| [07](stage-07.md) | 参考内存表 | 2 | [7](../tutorial/07-execution.md) |
| [08](stage-08.md) | Volcano 迭代器执行 | 3 | [7](../tutorial/07-execution.md) |
| [09](stage-09.md) | 带校验的 DML 查询闭环 | 5 | [7](../tutorial/07-execution.md) |
| [10](stage-10.md) | Explain 与 Executor 清理 | 2 | [7](../tutorial/07-execution.md) |
| [11](stage-11.md) | 带校验和的存储页 | 2 | [3](../tutorial/03-storage.md) |
| [12](stage-12.md) | 持久 Heap File | 13 | [3](../tutorial/03-storage.md) |
| [13](stage-13.md) | 持久 BTree 核心 | 10 | [5](../tutorial/05-btree.md) |
| [14](stage-14.md) | 已发布表索引 | 5 | [5](../tutorial/05-btree.md) |
| [15](stage-15.md) | 统计信息与 ANALYZE | 5 | [6](../tutorial/06-planning.md) |
| [16](stage-16.md) | 带成本的逻辑改写 | 6 | [6](../tutorial/06-planning.md) |
| [17](stage-17.md) | Optimizer 与执行度量 | 8 | [6](../tutorial/06-planning.md) |
| [18](stage-18.md) | MVCC 状态模型 | 5 | [4](../tutorial/04-mvcc.md) |
| [19](stage-19.md) | 事务与快照生命周期 | 3 | [8](../tutorial/08-isolation.md) |
| [20](stage-20.md) | 版本化 Heap 可见性 | 2 | [4](../tutorial/04-mvcc.md) |
| [21](stage-21.md) | 写锁与死锁 | 2 | [9](../tutorial/09-locks-deadlock.md) |
| [22](stage-22.md) | 带校验和的 WAL Record | 2 | [10](../tutorial/10-wal-recovery.md) |
| [23](stage-23.md) | 恢复与死锁受害者 | 5 | [10](../tutorial/10-wal-recovery.md) |
| [24](stage-24.md) | Sharp Checkpoint 持久性 | 2 | [10](../tutorial/10-wal-recovery.md) |
| [25](stage-25.md) | WAL 持久性与清理 Horizon | 5 | [11](../tutorial/11-vacuum-hot.md) |
| [26](stage-26.md) | Vacuum、HOT 与崩溃矩阵 | 10 | [12](../tutorial/12-testing-methodology.md) |
| [27](stage-27.md) | 维护领域闭环 | 9 | [11](../tutorial/11-vacuum-hot.md) |
| [28](stage-28.md) | 自连接作用域拒绝 | 2 | [2](../tutorial/02-sql-frontend.md) |
| [29](stage-29.md) | 跨层正确性回归 | 7 | [12](../tutorial/12-testing-methodology.md) |
| [30](stage-30.md) | HOT 审计闭环 | 2 | [11](../tutorial/11-vacuum-hot.md) |
