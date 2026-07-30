# 9. 锁与确定性死锁检测

MVCC 允许读写重叠，但它本身不能保证冲突写入安全。MiniPostgres 使用可重入的
排他锁串行化写者，锁资源是逻辑元组根或编码后的唯一键，等待者按 FIFO 排队。
锁管理器从队列推导 wait-for 图；若出现环，它会确定性地选择最大 XID 作为
受害者。本章把资源身份、队列公平、唯一性、环检测和事务清理连接起来。

## 学习目标

完成本章后，你将能够：

- 区分元组根锁和唯一键锁，并解释二者为什么都需要；
- 根据拥有者与 FIFO 队列推导 wait-for 图的边；
- 跟踪两行死锁并推导出最大 XID 受害者；
- 解释中止受害者如何释放资源并唤醒幸存者；
- 对比 MiniPostgres 的进程内排他锁与 PostgreSQL 的锁模式及死锁策略。

## 两种资源身份

`src/minipostgres/transaction/locks.py` 定义了不可变的
`TupleLockKey(table_id, tid)` 和
`UniqueKeyLockKey(index_id, encoded_key)`。它们解决不同的竞态。

元组锁串行化一个逻辑行的更新或删除。使用的 TID 是版本链根，而不是碰巧可见
的某个后继。`src/minipostgres/storage/indexed.py` 中的 `replace_mvcc()` 和
`delete_mvcc()` 会在 `LockManager.acquire()` 前调用
`HeapTable.root_tid()`。如果每个版本都有独立锁，两个写者可能锁住同一逻辑行
的不同版本并同时继续。

唯一键锁串行化一个键的“缺席或归属”。两个事务可能同时插入一个当前不存在的
新键，此时没有共同元组 TID 可锁。`_acquire_unique_keys()` 会在
`_check_unique_global()` 解析已提交、进行中和已中止候选版本前锁住编码键。
第一个事务结束后，第二个重新检查全局唯一性：若第一个中止则可继续，若已提交
则抛出 `ConstraintViolation`。

这些都只是排他锁，没有共享读行锁、表级模式、意向锁、谓词锁或锁升级。
普通快照读取不会取得它们。

## FIFO 获取与可重入

`LockManager.acquire()` 使用一个 `threading.Condition` 保护全部拥有者和队列
状态。`_owners` 把资源映射到 XID，`_queues` 把资源映射到等待 XID 的
`deque`。如果事务已经拥有资源，获取是可重入的，并立即把资源记录在事务资源
集合中。

否则 XID 只会追加一次。只有资源没有拥有者并且自己位于队首时才能获得：

```python
while owner is not None or queue[0] != transaction.xid:
    ...
    condition.wait()
```

队首条件十分关键。若没有它，释放锁后一个刚被调度的新等待者可能抢在更早被
唤醒的等待者之前。FIFO 是局部公平合同，不保证事务在有界时间内完成：事务可
无限期持有资源，依赖链也仍可能阻塞许多等待者。

`LockManager.release_all()` 会移除已经拥有的资源和排队请求，把事务从诊断
状态中删除，并调用 `notify_all()`。随后每个等待者重新检查循环条件。释放与
`TransactionManager.commit()` 和 `TransactionManager.abort()` 绑定，因此
锁不会跨越事务结果。

## 从队列构建 wait-for 图

死锁不是“查询等太久”，而是一组依赖成环，单纯继续等待无法让任何成员前进。
`LockManager._wait_graph()` 会从当前拥有者和队列顺序重建依赖。

若一个资源由 XID 4 拥有，队列为 `[7, 9]`，则 XID 7 等待 4。XID 9 同时等待
4 和更早的等待者 7，因为 FIFO 不允许 9 在 4 释放后先获得锁。因此图包含
`7 -> 4` 和 `9 -> {4, 7}`。队列顺序本身就是阻塞关系的一部分。

`src/minipostgres/transaction/deadlock.py` 的
`WaitForGraph.deadlock_victim()` 执行深度优先搜索。`visited` 避免重复搜索
已经完成的节点；`active` 和 `stack` 表示当前递归路径。指向活跃节点的边说明
出现环，函数从该节点处截取栈并返回环中最大 XID。

对节点和目标排序可以让遍历确定，但稳定测试更依赖受害者规则：最大 XID 失败。
这是教学策略，不代表最新事务总是具有最小回滚成本。

## 两行死锁的逐步过程

设低 XID 10 更新账户 A，高 XID 11 更新账户 B，各自拥有一个元组根锁。随后：

1. XID 10 请求 B，排在拥有者 11 后，产生边 `10 -> 11`。
2. XID 11 请求 A，排在拥有者 10 后，产生边 `11 -> 10`。
3. `deadlock_victim()` 看到环 `{10, 11}`，选择 11。
4. `LockManager._abort_victim()` 调用事务管理器的受害者处理器。
5. `TransactionManager._abort_deadlock_victim()` 把 11 标为失败并中止；
   中止释放 B，并移除 11 对 A 的排队请求。
6. 条件变量唤醒 XID 10，它取得 B 并继续。
7. 受害者 11 的获取调用抛出 `DeadlockDetected`。

仓库并发测试既断言异常，也断言幸存者最终提交的值。只断言某个线程停止，会
遗漏关键的恢复合同。

死锁检测在等待循环中同步进行，而不是交给后台检测器。没有
`deadlock_timeout`、周期性 worker 或用户可配置的受害者成本。小型状态空间
使即时建图清晰且确定。

## 锁、MVCC 与唯一性汇合

锁不决定可见性。等待结束后，存储访问方法用事务状态和快照解析全局活跃或
快照可见版本。因此，第 8 章的 RR 冲突和 RC 谓词重查都发生在取得元组锁之后。

同样，唯一键锁本身不能证明唯一。它为
`src/minipostgres/storage/indexed.py` 中的 `_check_unique_global()` 提供
串行化。该函数检查匹配的索引候选和堆版本状态。一次中止插入可能留下并不代表
活跃冲突的派生索引状态；已提交插入则会冲突。锁使检查与安装序列对该键保持
排他。

获取多个唯一键本身也可能参与等待环。MiniPostgres 使用一个共同的
`LockManager` 和联合类型 `LockKey`，所以元组与键依赖会出现在同一张图中，
而不是分散在互不相知的检测器里。

## 失败状态与客户端责任

死锁受害者会被管理器中止，其获取调用抛出 `DeadlockDetected`。客户端应把
整个事务视为失败；若要重试，应开始新事务。只重试最后一条 SQL 会遗漏在已
中止事务快照下做出的早先决定。

幸存者不会自动提交，它只是恢复可运行，并在原有隔离规则下继续。这一点在系统
表述中很重要：解决死锁恢复的是“进展”，而不是保证所有剩余事务成功。

`waiting_xids()` 提供诊断快照，确定性测试可以等待事务真正进入队列，而不是
用长时间 sleep 猜测。它并不是承诺稳定生产兼容性的监控 API。

## 与 PostgreSQL 18 对照

PostgreSQL 重量级锁管理器的核心位于
`src/backend/storage/lmgr/lock.c`；行级元组锁横跨堆访问方法和 multixact
机制。死锁搜索与报告位于 `src/backend/storage/lmgr/deadlock.c`，通常在
`deadlock_timeout` 后触发。唯一索引使用访问方法协作和推测插入，而不是
MiniPostgres 的单一编码键锁抽象。

两个系统都会推理阻塞依赖，并通过中止受害者打破环。PostgreSQL 拥有许多锁
模式、由队列顺序形成的软边、预备事务、更丰富的受害者考虑、详细诊断和跨进程
共享内存。MiniPostgres 则使用进程内 Python 条件变量、排他模式和“最大 XID
失败”。

这个边界记录在[行为矩阵](../BEHAVIOR_MATRIX.md)的 `locks` 行和
[与 PostgreSQL 的差异](../DIFFERENCES_FROM_POSTGRESQL.md#事务与维护)中。
[PostgreSQL 映射](../postgresql-mapping.md)按合同而不是文件格式或 API
兼容性标记对应关系。

## 动手实验：隔离图策略

这个实验直接调用纯图对象，避免调度噪声：

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline python - <<'PY'
from minipostgres.transaction.deadlock import WaitForGraph
print("cycle victim:", WaitForGraph({7: {9}, 9: {12}, 12: {7}}).deadlock_victim())
print("acyclic:", WaitForGraph({7: {9}, 9: {12}}).deadlock_victim())
PY
```

实测输出：

```text
cycle victim: 12
acyclic: None
```

再验证 FIFO 获取和完整引擎级两行环：

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline pytest -q \
  tests/unit/transaction/test_locks.py::test_lock_waiters_acquire_in_fifo_order \
  tests/concurrency/test_deadlock.py::test_two_row_deadlock_aborts_highest_xid
```

实测输出：

```text
..                                                                       [100%]
2 passed in 0.62s
```

第一个测试观察到获取顺序为 2 再 3。第二个等待真实入队，创建环，在高 XID
会话观察到 `DeadlockDetected`，并验证低 XID 事务可以提交。

## 练习

1. **理解题。** 资源 R 由 XID 3 拥有，FIFO 队列为 `[5, 8]`。
   `_wait_graph()` 会增加哪些边？

    验收方式：包含队列顺序阻塞者，而不只写拥有者。

    ??? note "参考答案"
        它增加 `5 -> {3}` 和 `8 -> {3, 5}`。即使拥有者 3 释放，XID 8
        也不能越过 XID 5。

2. **理解题。** 为什么在两个事务拥有共同元组 TID 之前，就可能存在唯一插入
   冲突？

    验收方式：指出必须串行化的资源，以及等待后执行的检查。

    ??? note "参考答案"
        两个事务竞争同一个编码索引键，而各自预期的元组 TID 不同或尚未发布。
        `UniqueKeyLockKey` 串行化该键；取得锁后 `_check_unique_global()`
        判断现有候选是否全局活跃并构成冲突。

3. **动手题。** 在一次性 worktree 中添加一个四节点图的单元测试：其中包含
   三节点环以及一个指向环的无环入口节点。不要修改教程作者工作树的 `src/`。

    验收方式：受害者必须是环内最大 XID，而不是全图最大 XID；再为自环添加
    断言。运行 `tests/unit/transaction/test_deadlock_graph.py`。

    ??? note "参考答案"
        可使用 `{20: {7}, 7: {9}, 9: {12}, 12: {7}}`。XID 20 不在环中，
        因此受害者是 12。自环 `{4: {4}}` 返回 4。无需修改生产代码，因为
        `deadlock_victim()` 只从重复节点处截取活跃 DFS 栈。

## 小结

MiniPostgres 使用一个排他 FIFO 管理器锁住逻辑元组根和唯一编码键。队列拥有者
及顺序产生 wait-for 图；深度优先环检测选择环中最大 XID，中止会释放其资源，
幸存者继续但不会被隐式提交。下一章会让这些事务结果持久化：WAL 顺序必须保证
脏页或成功提交都不能先于其恢复证据到达外部世界。
