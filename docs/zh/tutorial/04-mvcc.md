# 第 4 章：MVCC、元组版本与快照

多版本并发控制把物理历史与逻辑可见性分开。UPDATE 无需摧毁另一个事务正在读取的行；MiniPostgres 记录创建/删除事务 ID 并链接版本，每条语句再用快照判断哪些版本可见。

## 学习目标

完成本章后，你能够：

1. 解释 `TupleVersion` 的 `xmin`、`xmax`、`next_tid`；
2. 按“先 creator、后 deleter”的顺序应用 `is_visible()`；
3. 解释 `Snapshot(xmax, active_xids)` 的边界；
4. 区分 Read Committed 刷新快照与 Repeatable Read 固定快照；
5. 指出本模型相对 PostgreSQL MVCC 的缺失部分。

## 物理历史

`src/minipostgres/storage/tuple.py::TupleVersion` 有四个字段：

```python
TupleVersion(
    xmin: int,
    xmax: int,
    next_tid: TID | None,
    values: tuple[Scalar, ...],
)
```

`xmin` 是创建该版本的事务；`xmax == 0` 表示尚未删除或替代，否则它是执行删除/替代的事务；`next_tid` 指向后继版本。值留在物理版本中，因此旧快照仍能读取旧内容。

`src/minipostgres/storage/heap.py::HeapTable.insert_version()` 以当前 XID、零 xmax、无后继编码新版本。`replace_version()` 先插入 replacement，再把旧版本改成 `xmax=current_xid`、`next_tid=replacement`。`delete_version()` 只设置 xmax，不创建后继。写者协调和等待后的冲突策略在后章讲，本章只关注表示与可见性。

## 事务状态

`src/minipostgres/transaction/manager.py::TransactionManager.begin()` 分配单调递增 XID 并记录活动 `Transaction`。事务包含隔离级别、状态、可选 repeatable snapshot、写标记与所拥有资源。

`transaction/status.py::TransactionStatusTable` 把 XID 映射为 `IN_PROGRESS`、`COMMITTED` 或 `ABORTED`；未知 XID 默认 in progress，committed/aborted 为终态。这只是 PostgreSQL 事务状态职责的进程内教学类比，不是 `pg_xact` 存储格式。

特殊 `SYSTEM_XID` 用于普通事务 DML 外的存储参考路径，`is_visible()` 把它视为已提交；正常引擎查询使用事务版本。

## 快照的含义

`src/minipostgres/transaction/snapshot.py::Snapshot` 不可变：

- `xmax` 是捕获时的 next XID；大于等于它的 XID 都属于快照未来；
- `active_xids` 是捕获时仍活动的其他事务；即使它们后来提交，快照也记得当时尚未完成。

校验要求活动 XID 为正且小于 xmax。`oldest_active_xid` 是最小活动 XID，无活动事务时为 xmax；后续 VACUUM 会用类似 horizon 防止回收旧快照仍需要的历史。

`TransactionManager.statement_snapshot()` 构造快照，并排除当前事务，因为 own changes 有专门规则。Read Committed 每条语句创建新对象；Repeatable Read 把第一次快照保存到 `transaction.repeatable_snapshot`，以后返回同一对象。隔离差异来自快照生命周期，而不是不同的行格式。

## 可见性算法

`src/minipostgres/transaction/visibility.py::is_visible()` 保留 `HeapTupleSatisfiesMVCC` 的关键决策顺序：先判断 creator 是否可见，再判断可见 deletion 是否隐藏元组。

先处理自己的版本：

```text
if xmin == current_xid:
    除非 xmax == current_xid，否则可见
```

这实现 read-your-writes，并隐藏自己的删除。

对其他 creator，满足任一条件即不可见：

1. creator 状态不是 COMMITTED；
2. `xmin >= snapshot.xmax`；
3. `xmin` 位于 `snapshot.active_xids`。

捕获后才提交的事务仍触发第 3 条；捕获后才分配的事务触发第 2 条。

Creator 可见且 `xmax == 0` 时版本可见；当前事务是 deleter 时不可见。对于其他 deleter，只要删除尚未提交、属于快照未来或捕获时仍活动，旧版本就保持可见；只有对当前快照也可见的删除才能隐藏它。因此“创建已提交”并不充分，还必须评价删除。

## 解析版本链

`HeapTable.resolve_visible()` 从一个 TID 沿 `next_tid` 前进，检查循环和缺失目标，记录每个 `is_visible()` 为真的版本，最后返回最新可见项。链上未来或 aborted 版本可被跳过，同时保留更老的可见版本。

`scan_visible()` 先物化物理版本并收集所有 continuation TID，只从链根开始解析，避免同一逻辑行按物理成员重复发出。

`root_tid()` 暴露了刻意简化：它扫描全部物理版本构造 predecessor map，再向后走，是 O(N) 教学实现。PostgreSQL HOT 元数据和 line-pointer 状态提供更直接且丰富的导航；仓内[映射页](../postgresql-mapping.md)已明确指出。

## 语句执行与隔离

`Database.execute_for_session()` 在绑定后、分发前请求快照，创建包含 transaction、snapshot、status table、lock manager 的 `ExecutionContext`；堆 scan/fetch 会收到该上下文。

隐式事务只活一条语句，自然每次使用新快照。显式会话由 `Database.session(isolation=...)` 创建；BEGIN、COMMIT、ROLLBACK 与其他语句一样解析绑定，但由 engine 协调层处理。

Read Committed 允许同一事务的下一条语句看见上条语句后新提交的行；Repeatable Read 从第一条数据语句起固定视图。它并非只读：通过 current-XID 分支，事务仍看得到自己的新版本。

## 实验：一次更新，两种视图

运行：

```bash
uv run python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres import Database
from minipostgres.transaction.model import IsolationLevel

with TemporaryDirectory() as root, Database.open(root) as db:
    db.execute("CREATE TABLE counters (id INT PRIMARY KEY, value INT)")
    db.execute("INSERT INTO counters VALUES (1, 10)")
    rc = db.session(isolation=IsolationLevel.READ_COMMITTED)
    rr = db.session(isolation=IsolationLevel.REPEATABLE_READ)
    rc.execute("BEGIN"); rr.execute("BEGIN")
    print("before", rc.execute("SELECT value FROM counters").rows,
          rr.execute("SELECT value FROM counters").rows)
    db.execute("UPDATE counters SET value = 11 WHERE id = 1")
    print("after ", rc.execute("SELECT value FROM counters").rows,
          rr.execute("SELECT value FROM counters").rows)
    rc.execute("ROLLBACK"); rr.execute("ROLLBACK")
PY
```

实测输出：

```text
before ((10,),) ((10,),)
after  ((11,),) ((10,),)
```

默认会话提交 UPDATE 后，Read Committed 的下一条语句得到新快照并看见 11；Repeatable Read 复用第一次快照，沿版本链找到旧值 10。

再运行模型测试：

```bash
uv run pytest -q tests/unit/transaction/test_visibility.py \
  tests/concurrency/test_isolation_snapshots.py
```

实测输出：

```text
.......                                                                  [100%]
7 passed in 0.15s
```

实验使用进程内 direct session，不使用 socket，已完成运行时验证。

## 与真实 PostgreSQL 对照

PostgreSQL heap tuple 也携带事务可见性元数据，快照也记录事务边界，Read Committed 与 Repeatable Read 的关键区别同样是快照生命周期。相近所有者包括 `heapam_visibility.c`、`snapmgr.c` 与 `pg_xact`。

MiniPostgres 不含 command ID、subtransaction、导出快照、SSI、speculative insertion、XID wraparound/freeze、hint bit、multixact 或生产级 HOT/line-pointer 布局；status table 在进程内，版本链使用显式 TID。本章边界详见[差异页](../DIFFERENCES_FROM_POSTGRESQL.md)事务部分、[映射页](../postgresql-mapping.md)第 5/8 站与[行为矩阵](../BEHAVIOR_MATRIX.md) `mvcc` 行。

## 练习

### 1. 理解题：迟到的提交

捕获 `Snapshot(xmax=10, active_xids={8})` 时事务 8 正活动，随后它提交。`xmin=8` 的版本对该快照可见吗？

??? note "参考答案"

    不可见。虽然状态已 COMMITTED 且 8 < 10，但 XID 8 仍在快照 active set 中；快照保存捕获时尚未完成的事实。

### 2. 理解题：未来删除

一个可见版本的 `xmax=12` 且状态已提交，读者快照 `xmax=11`。旧版本可见吗？

??? note "参考答案"

    可见。删除事务属于快照未来，因为 `12 >= 11`；之后的提交不能追溯改变该快照。

### 3. 动手题：验证 read-your-writes

创建显式 Repeatable Read 会话，插入一行，在提交前读取，随后 rollback，并证明默认会话看不到它。不要修改 `src/`。

验收方式：

- 显式会话 rollback 前返回插入行；
- `ROLLBACK` 返回正确 command tag；
- 默认会话随后返回空行。

??? note "参考答案"

    CREATE TABLE 放在显式事务外（DDL 在显式事务内会被拒绝），BEGIN 后插入并 SELECT。`xmin == current_xid` 分支让自己的行可见；rollback 后 creator 状态为 ABORTED，其他事务拒绝该版本。

### 4. 动手设计题：可见性真值表

设计参数化单测，覆盖 committed/active/future/aborted creator、committed/active deleter，以及 own insert/delete。

验收方式：

- 直接构造 `TupleVersion`、`Snapshot`、`TransactionStatusTable`；
- 包含 own insertion 与 own deletion；
- 每个 case 有描述性 pytest ID。

??? note "参考答案"

    参数行可包含 `(name, xmin, xmax, current, boundary, active, statuses, expected)`，直接调用 `is_visible()`。ID 可用 `committed_creator`、`creator_active_at_snapshot`、`future_creator`、`aborted_creator`、`active_deleter_keeps_old`、`committed_deleter_hides`、`own_insert`、`own_delete`。

## 小结

MVCC 是对持久物理历史执行的可见性计算：`TupleVersion` 记录创建者、删除者和后继，`Snapshot` 记录未来边界及捕获时活动事务，`is_visible()` 先 creator 后 deleter。Read Committed 刷新证据，Repeatable Read 保留证据。下一章将看到 B+Tree 如何指向堆历史，却不越权决定可见性。
