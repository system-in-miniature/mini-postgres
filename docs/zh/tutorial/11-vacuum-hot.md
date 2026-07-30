# 11. VACUUM、回收视界与 HOT 链

MVCC 不会覆盖旧快照仍可能需要的版本，代价是物理残骸：中止插入、已提交旧
版本、陈旧索引条目和更新链。MiniPostgres 通过显式同步 `VACUUM` 回收它们。
全局视界保护活跃快照；堆槽位复用前先删除精确索引条目。当替换版本仍在同一页
且全部编码索引键不变时，仅堆元组（HOT）更新可以减少索引抖动。

## 学习目标

完成本章后，你将能够：

- 根据活跃事务计算保守清理视界；
- 把中止版本与已被取代版本分类为保留或死亡；
- 解释为什么槽位复用前必须删除陈旧索引条目；
- 跟踪 HOT 更新从资格判断到根 TID 查找和链可见性；
- 说明 MiniPostgres VACUUM/HOT 与 PostgreSQL autovacuum、冻结、可见性图
  和行指针重定向的区别。

## 回收需要证明

一个版本对正在执行 VACUUM 的事务不可见，并不足以证明可回收。另一个活跃 RR
事务可能持有仍能看到它的旧快照。`src/minipostgres/maintenance/horizon.py`
中的 `cleanup_horizon()` 会找出保守全局边界。

它从 `next_xid` 开始。对每个活跃事务，如果没有固定快照，就加入事务自身 XID；
否则加入固定快照的 `xmax` 与活跃 XID。最小值就是清理视界。任何可能需要旧
历史的事务都会把视界向后拉。

`classify_version()` 只返回 `KEEP` 或 `DEAD`。如果一个已中止创建者早于视界，
版本死亡。如果版本创建者和删除者都已提交，且 `xmin` 与非零 `xmax` 都早于
视界，版本也死亡。其余全部保留。“保留”可能表示当前可见、可能被活跃快照
看到、太新而无法证明安全，或仍依赖未决结果。

这个保守二元规则比生产级 vacuum 状态机更容易审计。只有证明全部受支持的
活跃快照都不再需要版本，才会回收。

## 引擎级 VACUUM 协调

`src/minipostgres/engine.py` 中的 `Database._vacuum()` 计算一次视界，选择
一张或全部表，再通过 `src/minipostgres/maintenance/coordinator.py` 的
`MaintenanceCoordinator.maintenance()` 获取每表维护租约。普通插入、更新
与删除取得对应写者租约。这会防止单进程中的物理回收与表写者竞态。

每次 `IndexedTableAccess.vacuum()` 返回 `VacuumResult`：扫描页数、删除的
死版本数、删除的索引条目数、回收字节数和剪掉的 HOT 版本数。引擎合并结果，
把统计信息标为陈旧，并返回类似 `VACUUM 2` 的命令标签。

`Database.execute_for_session()` 不允许在显式用户事务内执行 VACUUM。
它作为自己的语句事务运行，并为堆页修改发布 WAL。它是手动的：没有后台
autovacuum 线程监视死元组阈值。

## 普通死版本清理

`src/minipostgres/storage/indexed.py` 中的
`IndexedTableAccess.vacuum()` 会快照物理版本，并先识别 HOT 链。未由链
剪枝处理的版本走普通路径：

1. 用全局视界和状态表调用 `classify_version()`；
2. 对每个已发布索引删除精确 `(编码键, TID)` 条目；
3. 调用 `HeapTable.reclaim_version()` 删除槽位负载；
4. 压实分槽页并发布新的完整页 WAL 镜像。

索引删除必须先于槽位复用。TID 是 `(page_id, slot_id)`。压实会维持活跃槽位
ID 稳定，但死亡槽位以后可以存放新元组。若陈旧索引条目仍存在，同一个数字 TID
可能指向无关新行。堆重查可以保护查询谓词，但保留这种别名仍会破坏索引归属和
唯一性推理。

在状态不变时，`VACUUM` 在物理上幂等。第二次运行不会发现新死版本，报告零
删除。它会压实页，但不会截短关系文件。

## 什么让更新成为 HOT

普通 MVCC 更新会创建后继，并为它加入索引条目。索引键未变时，这会为同一逻辑
行的多个版本复制索引引用。PostgreSQL 的 HOT 思想是保留一个索引根，把同页
后继连成仅堆链。

MiniPostgres 在 `src/minipostgres/maintenance/hot.py` 的 `hot_eligible()`
集中定义规则：

```python
return same_heap_page and old_index_keys == new_index_keys
```

`IndexedTableAccess.replace_mvcc()` 先从 `HeapTable.replace_version()` 获取
实际替换 TID。它比较替换页与可见版本页，并比较每个索引的编码键。两项都成立
时，不插入后继索引条目；否则正常发布所有新键/TID。

这是基于结果的教学规则。PostgreSQL 会在放置前或放置中根据修改属性和页空间
判断资格。MiniPostgres 观察实际位置和编码键相等。比较编码结果比挑选某个 SQL
列更重要，因为全部已发布索引都参与判断。

## 跟随与剪枝 HOT 链

堆元组版本携带 `next_tid`。`src/minipostgres/storage/heap.py` 中的
`HeapTable.version_chain()` 跟随后继，同时验证链无环、引用槽位都存在且所有
成员留在根页。`HeapTable.root_tid()` 对物理版本做 O(N) 扫描，建立前驱图并
向后走到最老成员。

这个根查找明确属于简化。PostgreSQL 可以使用行指针重定向和 HOT 标志，无需
扫描全页版本即可定位链。MiniPostgres 牺牲时间，把前驱关系显式展示在 Python
代码里。

索引扫描找到根 TID。`IndexedTableAccess.fetch_mvcc()` 解析该链中对当前快照
可见的版本。因此 RR 读者可沿同一根走到较老后继，而较新事务走到最新已提交
成员。

VACUUM 中，当链根有索引而后继没有独立索引时，它符合 HOT 剪枝条件。死亡的
非根成员成为候选，但除非普通路径能删除整个逻辑行，最新物理成员会保留。
`HeapTable.prune_chain()` 改写每个前驱的 `next_tid`，绕过可删除中间成员，
回收其槽位，并记录页修改。根索引条目保持稳定。

## 长快照展示安全边界

仓库测试
`tests/integration/test_vacuum_reuse.py::test_long_repeatable_snapshot_prevents_reclamation`
在一行上打开 RR 读者，执行并发非 HOT 更新，再运行 VACUUM。第一次 VACUUM
删除零版本，因为读者固定快照降低视界。读者提交后，第二次 VACUUM 至少能回收
一个旧版本。

这比单会话中数死字节更有意义。它验证维护会尊重已对另一个活跃事务做出的
可见性承诺。行为矩阵的 `vacuum` 证据行直接指向该节点。

## 与 PostgreSQL 18 对照

PostgreSQL 堆 vacuum 与剪枝横跨
`src/backend/access/heap/vacuumlazy.c`、`pruneheap.c` 和 `heapam.c` 等文件。
Autovacuum 调度位于 `src/backend/postmaster/autovacuum.c`。PostgreSQL 使用
视界与事务元数据跟踪全局可见性，清理索引，剪枝 HOT 链，冻结旧 XID，更新
可见性图和空闲空间图，并防止回卷。

MiniPostgres 保留核心安全故事——不回收活跃快照可见内容；复用前清索引；
同页且索引不变的后继只留在堆中——但省略 autovacuum、冻结、回卷、可见性图、
成本延迟、并发索引 vacuum 协议和文件截短。其维护同步且仅限进程内。

参见[行为矩阵](../BEHAVIOR_MATRIX.md)的 `vacuum` 与 `hot` 行、
[与 PostgreSQL 的差异](../DIFFERENCES_FROM_POSTGRESQL.md#事务与维护)，以及
[架构参考](../ARCHITECTURE.md#事务与持久性)的存储流程。

## 动手实验：剪枝 HOT 链

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres import Database

with TemporaryDirectory() as root, Database.open(root) as db:
    db.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
    db.execute("INSERT INTO users VALUES (1, 20)")
    for age in (21, 22, 23):
        db.execute(f"UPDATE users SET age = {age} WHERE id = 1")
    result = db.execute("VACUUM users")
    print(result.command_tag)
    print("rows:", db.execute("SELECT * FROM users").rows)
    print("removed:", result.maintenance.dead_versions_removed)
    print("HOT pruned:", result.maintenance.hot_versions_pruned)
PY
```

实测输出：

```text
VACUUM 2
rows: ((1, 23),)
removed: 2
HOT pruned: 2
```

最新行保留，两个过时中间版本被删除。再验证快照视界与索引根合同：

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline pytest -q \
  tests/integration/test_vacuum_reuse.py::test_long_repeatable_snapshot_prevents_reclamation \
  tests/integration/test_hot_pruning.py::test_vacuum_prunes_dead_hot_intermediates_and_keeps_index_root
```

```text
..                                                                       [100%]
2 passed in 1.02s
```

## 练习

1. **理解题。** 为什么“对 VACUUM 事务不可见”弱于“可以安全回收”？

    验收方式：加入另一个会话及其快照视界。

    ??? note "参考答案"
        长生命周期 RR 会话可能保留一个仍能看到旧版本的快照，即使 VACUUM
        的新快照已经拒绝它。全局视界包含活跃快照，直到没有快照可能需要该
        历史才允许回收。

2. **理解题。** 一次更新没有改变任何 SQL 值，但替换版本被放到另一个堆页。
   在 MiniPostgres 中它是 HOT 吗？

    验收方式：应用 `hot_eligible()` 的两个条件。

    ??? note "参考答案"
        不是。编码键相等，但 `same_heap_page` 为假。后继需要普通索引条目，
        不能进入局限于根页的 HOT 链。

3. **动手题。** 在一次性 worktree 中增加测试：删除一个有索引的行后运行两次
   VACUUM，并断言索引安全与幂等。不要修改教程作者工作树中的 `src/`。

    验收方式：第一次删除一个版本，精确索引搜索为空；第二次删除零；之后插入
    新行，搜索旧键不能返回它。运行该测试及
    `tests/property/test_vacuum_idempotence.py`。

    ??? note "参考答案"
        参考 `tests/integration/test_vacuum_reuse.py` 的
        `test_vacuum_removes_dead_versions_and_stale_index_entries`。
        使用 `KeyCodec` 编码旧键，第一次 VACUUM 后检查已发布树，再捕获第二次
        前后的物理版本。无需生产补丁。

## 小结

VACUUM 是由证明驱动的物理清理。保守视界包含每个活跃受支持快照；普通死版本
在槽位可复用前失去精确索引条目，HOT 链则保留一个索引根并剪掉安全的中间
成员。这个设计保留机制，却没有 PostgreSQL 广泛的维护基础设施。最后一章将
追问如何知道每项声明为真：测试必须覆盖局部规则、生成状态空间、组件边界、
对抗性调度/崩溃以及端到端对应。
