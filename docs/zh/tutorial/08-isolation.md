# 8. 隔离级别、写冲突与 EPQ 重查

MVCC 会为一个逻辑行保留多个物理版本。隔离级别规定事务可以把哪一段已提交
历史当作自己的数据库。MiniPostgres 实现了两种有用策略：读已提交（RC）在
每条语句刷新快照，可重复读（RR）则固定第一次数据快照。这个差异看似很小，
却决定了读现象、并发更新行为，以及等待中的写者应该重查谓词还是抛出序列化
冲突。

## 学习目标

完成本章后，你将能够：

- 根据 `xmax` 与活跃 XID 集合推导 RC 或 RR 快照；
- 把创建者/删除者可见性规则应用到带 `xmin`/`xmax` 的元组版本；
- 解释为什么 RR 即使仍能读取旧版本，也必须拒绝基于旧版本的写入；
- 跟踪 RC 写者从元组锁等待到 EPQ 风格谓词重算的路径；
- 准确说明 MiniPostgres 保留和未保留哪些 PostgreSQL 隔离保证。

## 快照是可见性边界，不是行的副本

`src/minipostgres/transaction/snapshot.py` 中的 `Snapshot` 保存两个事实：
创建快照时的下一个 XID `xmax`，以及当时仍在进行的其他事务集合
`active_xids`。它不复制堆页或行，之后只需用这个紧凑边界判断元组版本。

`src/minipostgres/transaction/manager.py` 中的
`TransactionManager.statement_snapshot()` 拥有快照策略。RC 事务每条语句
都会构造新 `Snapshot`。RR 则把第一个快照保存到
`Transaction.repeatable_snapshot`，后续语句返回同一个对象：

```python
if transaction.isolation is REPEATABLE_READ:
    transaction.repeatable_snapshot = snapshot
```

假设下一个 XID 是 20，事务 17 与 19 仍活跃，则快照为
`(xmax=20, active={17, 19})`。XID 18 创建的版本在 18 已提交时可能可见；
20 及以后的版本太新；17 创建的版本会被排除，因为 17 在快照时仍活跃。
仍然必须查询状态表：单凭数字位置无法判断更老的创建者是提交还是中止。

MiniPostgres 在进程内分配 XID，并把事务结果保存在
`TransactionStatusTable`。当前事务无需等待状态表转换就能看到自己的插入并
隐藏自己的删除。这条“读己之写”规则是显式事务能够实用的基础。

## 可见性判定

`src/minipostgres/transaction/visibility.py` 中的 `is_visible()` 先判断
创建者。如果创建者未提交、XID 大于等于快照 `xmax`，或出现在
`active_xids` 中，版本就会被拒绝。系统创建的版本被视为已提交。创建者通过
后，若 `xmax` 为零，说明没有事务删除或取代它，因此版本可见。

若元组 `xmax` 非零，函数会判断删除事务对该快照是否可见。一个已提交、早于
`xmax` 且当时不活跃的删除者会让旧版本不可见。已中止、太新或在快照中活跃的
删除者则不会遮蔽旧版本。

所以 MVCC 并不是“选择最大的 `xmin`”。可见性依赖两个事务结果和快照的活跃
集合。这也解释了为什么中止事务的物理版本可以安全留在磁盘，等 VACUUM 再
回收：可见性判断会先拒绝它们。

源码注释正确指向 PostgreSQL 的 `HeapTupleSatisfiesMVCC`，但 MiniPostgres
的状态模型小得多：没有 hint bit、子事务祖先、command ID、multixact 或 XID
回卷。

## 读已提交与可重复读

考虑两个会话。两者都读到 10。第三个事务提交值 11。RC 下一条语句取得新快照，
其边界包含已提交写者，因此读到 11。RR 复用旧快照，仍读到 10。这正是仓库中
可执行的不可重复读差异。

实现从未声称 RC 是事务级快照；它明确是语句级。RR 也不等于串行执行。RR
保持稳定读视图，但其他事务仍可并发提交。稳定可见性还引出写入规则：RR 事务
不能盲目覆盖在其快照之后出现的版本。

`src/minipostgres/storage/indexed.py` 中的
`IndexedTableAccess._check_repeatable_read_write_conflict()` 会在取得写锁后，
比较事务保存快照下可见的 TID 与当前全局活跃 TID。若两者不同，就抛出
`SerializationConflict("could not serialize access due to concurrent update")`。
旧版本仍能读，但基于它写入会丢失或错误排序中间更新。事务必须回滚，应用可以
从新快照重试。

冲突检查必须位于取得锁之后。等待前候选仍可能是最新版本；等待期间锁拥有者
可能提交后继版本。写者必须判断自己实际要修改的状态，而不是阻塞前看到的状态。

## 读已提交与 EvalPlanQual 风格重查

RC 走另一条路径。语句因谓词为真找到候选 TID `t`，随后等待持有该逻辑行的
另一个写者。获得锁时，全局活跃版本的值可能已经变化。若不重查就更新，可能
修改一行已经不再满足语句条件的数据。

规划器把修改谓词带入 `PhysicalModifyTable.recheck_predicate`。执行器中的
`src/minipostgres/executor/operators.py` 的
`UpdateExecutor._predicate_recheck()` 或 `DeleteExecutor._predicate_recheck()`
会把绑定表达式变成针对最新元组值的可调用对象。它重建一个小型
`ExecutionRow` 并调用 `evaluate()`，只有 `True` 才通过。

取得元组锁后，`IndexedTableAccess.replace_mvcc()` 解析全局活跃版本。对 RC
而言，若重查函数返回假，它就报告 `(None, False)`。
`UpdateExecutor._open()` 随后跳过该候选，所以命令标签可能是 `UPDATE 0`。
`delete_mvcc()` 对删除采用同一规则。源码注释称其为 PostgreSQL
EvalPlanQual（EPQ）的简化等价物。

必须准确描述积极机制：MiniPostgres 会在写锁等待后，对最新行重新计算这个
有界语句谓词。它没有复现 PostgreSQL 面向连接、rowmark、触发器、分区和复杂
计划状态的完整 EPQ 机制。

## 事务失败与调用方恢复

`src/minipostgres/engine.py` 中的 `Database.execute_for_session()` 会在绑定
或执行抛错时，把活跃的显式事务标记为失败。之后的工作会调用
`Transaction.require_usable()` 并被拒绝，直到 `ROLLBACK`。隐式事务则由
引擎立即中止。

成功提交时，`TransactionManager.commit()` 只有在完成第 10 章的持久化协议
后才发布事务状态。提交与中止都会把事务从活跃集合移除并释放锁。因此后续快照
看到的是稳定结果，而不是一个凭空消失的进行中 XID。

MiniPostgres 没有保存点或子事务。一个错误会毒化整个显式事务。这与
PostgreSQL 默认事务块行为方向一致，但不能通过回滚到保存点恢复。

## 与 PostgreSQL 18 对照

PostgreSQL 的快照获取主要位于 `src/backend/utils/time/snapmgr.c`，堆可见性
判断位于 `src/backend/access/heap/heapam_visibility.c`。执行器并发更新路径
与 EPQ 机制分布在 `src/backend/executor/nodeModifyTable.c`、`execMain.c`
和访问方法代码中。PostgreSQL 的 `READ COMMITTED` 每条命令取得新快照；
`REPEATABLE READ` 使用事务级快照，并可能对并发更新产生 SQLSTATE `40001`。

MiniPostgres 保留了这些教学合同，但既不支持 PostgreSQL 的 Serializable
Snapshot Isolation，也没有谓词锁。它只有 RC 和 RR、进程内 XID/状态表，
并使用类型化 Python 异常而不是 SQLSTATE 一致性。它还拒绝自连接，因为运行
时身份按目录 table ID，而不是独立的范围表实例来表示。

使用[行为矩阵](../BEHAVIOR_MATRIX.md)的 `mvcc` 行、
[与 PostgreSQL 的差异](../DIFFERENCES_FROM_POSTGRESQL.md#事务与维护)的事务
章节以及[架构参考](../ARCHITECTURE.md#事务与持久性)，可以把等价思想与产品
兼容性区分开。

## 动手实验：观察快照分叉

在仓库根目录运行：

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres import Database
from minipostgres.errors import SerializationConflict
from minipostgres.transaction.model import IsolationLevel

with TemporaryDirectory() as root, Database.open(root) as db:
    db.execute("CREATE TABLE counters (id INT PRIMARY KEY, value INT)")
    db.execute("INSERT INTO counters VALUES (1, 10)")
    rc = db.session()
    rr = db.session(isolation=IsolationLevel.REPEATABLE_READ)
    rc.execute("BEGIN"); rr.execute("BEGIN")
    print("first:", rc.execute("SELECT value FROM counters").rows,
          rr.execute("SELECT value FROM counters").rows)
    db.execute("UPDATE counters SET value = 11 WHERE id = 1")
    print("second:", rc.execute("SELECT value FROM counters").rows,
          rr.execute("SELECT value FROM counters").rows)
    try:
        rr.execute("UPDATE counters SET value = 12 WHERE id = 1")
    except SerializationConflict as error:
        print(type(error).__name__ + ":", error)
    rr.execute("ROLLBACK"); rc.execute("COMMIT")
PY
```

实测输出：

```text
first: ((10,),) ((10,),)
second: ((11,),) ((10,),)
SerializationConflict: could not serialize access due to concurrent update
```

仓库中的线程化 EPQ 回归也已实跑：

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline pytest -q \
  tests/concurrency/test_write_conflicts.py::test_read_committed_writer_rechecks_predicate_after_lock_wait
```

```text
..                                                                       [100%]
2 passed in 0.74s
```

该节点对 `UPDATE` 和 `DELETE` 做参数化，因此有两个用例。

## 练习

1. **理解题。** 给定快照 `(xmax=12, active={9})`，事务 10 能否看到版本
   `(xmin=8 已提交, xmax=9 进行中)`？

    验收方式：分别应用创建者规则与删除者规则。

    ??? note "参考答案"
        能。创建者 8 在快照边界前提交，且不在活跃集合。删除者 9 在快照中
        活跃，所以其删除不可见，旧版本仍可见。

2. **理解题。** 为什么 RR 要在取得元组锁之后，才比较快照可见 TID 与全局
   活跃 TID？

    验收方式：说明等待期间可能发生的状态转换，以及所防止的异常。

    ??? note "参考答案"
        该写者等待期间，另一个拥有者可能提交一个后继版本。锁后比较可以发现
        RR 写者的来源已经过时，防止基于旧快照造成丢失更新。

3. **动手题。** 在一次性 worktree 中添加一个并发测试：RC 的
   `DELETE ... WHERE value = 10` 等待另一个把值改为 11 的事务。不要修改
   教程作者工作树中的 `src/`。

    验收方式：使用确定性的队列观察，而不是用 `sleep()` 作为同步断言；
    删除必须返回 `DELETE 0`，最终行必须包含值 11。若装有对应插件，用
    `pytest --count` 连跑三次；否则在 shell 中循环精确节点。

    ??? note "参考答案"
        参考 `tests/concurrency/test_write_conflicts.py` 的
        `test_read_committed_writer_rechecks_predicate_after_lock_wait`。
        启动两个事务，第一个更新为 11，在单 worker 线程池中提交删除，
        等待第二个 XID 出现在 `waiting_xids()`，然后提交第一个事务。
        因为 `DeleteExecutor` 会在值 11 上重查 `value = 10`，待处理结果是
        `DELETE 0`。

## 小结

快照是紧凑的可见性边界。RC 每条语句刷新快照，并对等待写者的谓词在最新行上
重查；RR 固定一份快照，当写入来源不再是全局当前版本时抛出
`SerializationConflict`。两种行为都来自事务状态、元组版本、锁和执行器谓词
求值的组合。下一章将打开锁管理器本身：FIFO 队列通常有用，但依赖一旦成环，
系统就必须确定性地解决死锁。
