# 7. Volcano 执行

规划阶段选择物理树，执行阶段则让这棵树真正产出行。本章从
`build_executor()` 出发，沿着 `open()`/`next()`/`close()` 协议一路追踪
MiniPostgres，再说明表达式、阻塞型算子、数据修改以及 `EXPLAIN ANALYZE`
如何围绕这一小组接口协同工作。关键并不只是“算子是一些类”，而是每个
节点都有精确的拉取式生命周期。因此，父节点可以请求一行，而不必知道
子节点正在读取堆页、探测索引、构建哈希表还是计算聚合。

## 学习目标

完成本章后，你将能够：

- 从物理计划追踪到执行器对象树，并跟随一行数据向树的上层流动；
- 区分流式算子与必须先消费输入才能返回行的算子；
- 解释 MiniPostgres 在执行边界上的整数表达式与 SQL `NULL` 语义；
- 说明为什么执行成功或失败后，执行器清理都能保持平衡；
- 解读结构化 `EXPLAIN ANALYZE` 中的估计证据和实际证据。

## 从不可变计划到活动算子树

`src/minipostgres/engine.py` 中的 `Database._execute_relational()` 是公开的
编排点。它调用 `Planner.logical()` 得到逻辑树，把它交给
`Database._optimize()`，并得到不可变的 `PhysicalPlan`。随后它调用
`src/minipostgres/executor/factory.py` 的 `build_executor()`，最后通过
`src/minipostgres/executor/base.py` 的 `collect()` 抽干结果。

这个工厂是刻意设置的边界，而不是一个方便的分支语句。
`_build_executor()` 递归地把每个物理节点映射为对应的运行时节点。
`PhysicalFilter` 变为 `FilterExecutor`，而它的子执行器已经构建好；
`PhysicalHashJoin` 变为带两个子执行器的 `HashJoinExecutor`；
`PhysicalModifyTable` 则变为插入、更新或删除执行器。规划数据保持不可变，
迭代器、哈希桶、排序缓冲区和计数器等执行状态则只存在于执行器实例中。

公共协议定义在 `src/minipostgres/executor/base.py` 的 `Executor.open()`、
`Executor.next()` 与 `Executor.close()` 中：

```python
with executor:
    while (row := executor.next()) is not None:
        rows.append(row)
```

这段短循环就是 Volcano 模型的核心。`open()` 初始化节点，`next()` 返回
一个 `ExecutionRow` 或 `None`，`close()` 释放子节点状态。公共方法会强制
执行生命周期规则：重复打开是幂等的，已关闭节点不能再次打开，未处于打开
状态时调用 `next()` 会报错。`collect()` 使用上下文管理器，因此即使子节点
在生成行时抛出异常，Python 仍会调用 `close()`。

`ExecutionRow` 不只是用于展示的一组值。扫描算子会附加目录稳定的列绑定和
来源 TID；投影与聚合节点会附加计算后的输出槽。因此，更新算子可以消费一行
由计划产生的数据，同时仍能定位其物理来源版本，而无需让每个中间算子理解
存储。这个所有权边界总结在
[架构参考](../ARCHITECTURE.md#执行器所有权)中。

## 流式算子与阻塞型算子

查看 `src/minipostgres/executor/operators.py` 中的
`SeqScanExecutor._open()` 和 `SeqScanExecutor._next()`。打开节点时会取得
表扫描迭代器。每次调用 `next()` 只推进到足以返回一个可见行为止。
`FilterExecutor._next()` 反复拉取子节点，直到 `evaluate()` 返回恰好为
`True`；`False` 与 SQL 未知值都会淘汰该行。`ProjectExecutor._next()` 拉取
一个子行并计算选择项。这些都是流式算子：通常无需物化全部输入就能返回输出。

有些算子需要阶段边界。`HashJoinExecutor._open()` 必须先把选定的构建侧抽干
到内存哈希表中，探测阶段才能产出行。`AggregateExecutor._open()` 消费子节点
来建立分组和聚合状态。`SortExecutor._open()` 抽干并排序全部行，之后
`SortExecutor._next()` 才返回第一行。它们内部虽然会阻塞，但父节点仍看到
相同的拉取接口，所以依旧是 Volcano 节点。

`NestedLoopJoinExecutor._next()` 展示了无需完整物化的有状态拉取。它保存当前
左行，在右侧行上打开或重置工作，并对每一对行计算完整连接条件。
`HashJoinExecutor._next()` 使用抽取出的等值键寻找候选，但仍把完整 `ON`
谓词作为残余条件计算。因此，改变连接算法只会改变工作量，不会改变结果语义。

这种有界设计是刻意的。连接、聚合与排序都在 Python 内存中完成；没有磁盘
溢写、并行执行器、向量化批处理或内存记账层级。不过，
`src/minipostgres/executor/memory.py` 的 `TableAccess` 仍使执行器无需关心
行来自 `MemoryTable` 还是持久化的 `IndexedTableAccess`。

## 类型化表达式求值与 int64 行为

`src/minipostgres/executor/expressions.py` 中的 `evaluate()` 只计算已经完成
绑定的表达式。名称解析和类型推断发生在更早阶段，所以执行器只需分派
`BoundLiteral`、`BoundColumn`、`BoundCast`、`BoundUnary`、`BoundBinary`
和 `BoundIsNull`。

这里有两个重要边界。第一，算术会传播 `NULL`：在用专门的 SQL 辅助函数处理
`AND`、`OR` 和比较之后，只要任一算术操作数为 `None`，`_binary()` 就返回
`None`。过滤器仅保留 Python 值 `True`，从而维持 SQL 三值谓词语义。第二，
整数算术采用有符号 64 位语义，而不是 Python 的任意精度整数语义。加、减、
乘和一元取负都通过 `src/minipostgres/types.py` 的 `validate_int64()`。
整数除法先对绝对值相除再恢复符号，因此向零截断；除数为零会抛出
`TypeMismatch`。

验证放在运算之后，是因为 Python 可以安全算出数学结果，随后 MiniPostgres
再拒绝超出数据库类型范围的值。这也意味着，查询表达式的溢出行为由求值器
定义，而不是由存储编解码器定义。

## 数据修改也是执行器节点

`src/minipostgres/executor/operators.py` 中的 `InsertExecutor._open()`、
`UpdateExecutor._open()` 和 `DeleteExecutor._open()` 会消费子行，并通过
`ModificationExecutor._next()` 产出一个受影响行数。它们不会直接伸手修改
Python 列表，而是调用 `TableAccess` 边界；正常数据库执行会把这个调用路由到
持久化 MVCC 堆和索引维护。

更新会先对孩子产出的全部候选行进行表达式计算与模式验证。它保留每个来源
TID，在存储访问层获得所需并发保护，然后安装新版本。删除同样使用来源 TID。
正因如此，投影裁剪不能随意丢掉修改计划中的行身份。

这个实现仍远小于 PostgreSQL：没有触发器执行、`RETURNING`、分区路由、推测
插入或语句级过渡表。积极合同——通过执行器和访问方法边界完成修改——是真实
存在的；外围生产功能则没有实现。

## 不改变拉取合同的 `EXPLAIN ANALYZE`

`src/minipostgres/engine.py` 中的 `Database._explain()` 区分两类操作。
普通 `EXPLAIN` 调用 `explain_plan()`，既不构建也不运行执行器。
`EXPLAIN ANALYZE` 会创建 `InstrumentationSession`，传给
`build_executor()`，运行整棵树，再把收集到的度量与物理计划合并。

`src/minipostgres/executor/instrumentation.py` 中的
`InstrumentationSession.wrap()` 使用 `InstrumentedExecutor` 装饰每个节点。
它的 `_open()`、`_next()` 和 `_close()` 会给委托对象计时并统计输出行数。
包装器不会增加第二次遍历，也不会改变请求方向。度量以 `id(plan)` 为键，从而
把每个运行时包装器连回确切的不可变计划节点。

耗时毫秒数只是本地 Python 测量结果，不是 PostgreSQL 成本单位、基准测试级
延迟，也不是预测。估计行数与成本来自规划；实际行数与耗时来自这一次执行。
`InstrumentationTracker.record_open()` 和 `record_close()` 还提供全仓库生命
周期检查。即使表达式计算失败，嵌套的上下文管理器清理仍会关闭每个已打开的
委托节点。

## 与 PostgreSQL 18 对照

PostgreSQL 同样执行一棵计划状态节点树。最接近的源码锚点是
`src/backend/executor/execProcnode.c` 中的 `ExecInitNode`、`ExecProcNode`
和 `ExecEndNode`，`src/backend/executor/execExpr.c` 中的表达式步骤解释器，
以及 `nodeSeqscan.c`、`nodeHashjoin.c`、`nodeAgg.c`、`nodeSort.c` 等节点
文件。`EXPLAIN (ANALYZE)` 由 `src/backend/commands/explain.c` 编排，执行器
度量位于 `src/backend/executor/instrument.c`。

共同形态是需求驱动的节点执行和逐节点运行时证据。MiniPostgres 刻意用 Python
对象和内存状态替代 PostgreSQL 的生成式表达式步骤、内存上下文、元组槽、
并行、JIT 钩子、work-memory 溢写与丰富度量。它返回结构化
`PlanExplanation`，而不是兼容 PostgreSQL 的文本或 JSON。参见
[与 PostgreSQL 的差异](../DIFFERENCES_FROM_POSTGRESQL.md#查询引擎)中的查询
引擎限制、[行为矩阵](../BEHAVIOR_MATRIX.md)中的 `query_path` 行，以及
[PostgreSQL 映射](../postgresql-mapping.md)中的关系分级。

## 动手实验：拉取一棵带度量的树

在仓库根目录执行下列命令。该命令已在当前仓库中实测：

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres import Database

def walk(node, depth=0):
    print("  " * depth + f"{node.node_type}: actual_rows={node.actual_rows}")
    for child in node.children:
        walk(child, depth + 1)

with TemporaryDirectory() as root, Database.open(root) as db:
    db.execute("CREATE TABLE sales (dept TEXT, amount INT)")
    db.execute("INSERT INTO sales VALUES ('eng', 7), ('eng', 5), ('ops', 3)")
    result = db.execute(
        "EXPLAIN ANALYZE SELECT dept, SUM(amount) FROM sales "
        "GROUP BY dept ORDER BY dept"
    )
    print(result.rows)
    walk(result.plan)
    tracker = db.instrumentation_tracker
    print("balanced lifecycle:", tracker.open_count == tracker.close_count)
PY
```

实测输出：

```text
(('eng', 12), ('ops', 3))
Sort: actual_rows=2
  Project: actual_rows=2
    Aggregate: actual_rows=2
      SeqScan: actual_rows=3
balanced lifecycle: True
```

扫描产生三行，聚合把它们缩减为两个分组，上层节点各产生两行。生命周期计数
证明每次带度量的打开都有对应关闭。还实跑了聚焦回归检查：

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline pytest -q \
  tests/contract/test_explain_analyze.py::test_explain_analyze_reports_each_node_without_changing_rows
```

```text
.                                                                        [100%]
1 passed in 0.48s
```

## 练习

1. **理解题。** `SortExecutor` 在 `open()` 阶段消费整个子节点，为什么仍能
   遵守 Volcano？

    验收方式：答案必须区分父节点可见的拉取合同与节点内部的阻塞算法。

    ??? note "参考答案"
        Volcano 规定父节点如何与节点交互，并不要求每个节点内部都必须流式。
        Sort 可以在 `_open()` 中物化并排序全部输入，再通过每次 `_next()`
        返回一行。

2. **理解题。** 有符号 int64 溢出和 SQL 未知值过滤分别在哪里完成？为什么
   这两项不是规划器职责？

    验收方式：写出相对源码路径、函数名，并说明它们依赖的运行时输入。

    ??? note "参考答案"
        `src/minipostgres/executor/expressions.py` 的 `_binary()` 为整数结果
        调用 `validate_int64()`。`src/minipostgres/executor/operators.py`
        的 `FilterExecutor._next()` 仅保留
        `evaluate(predicate, row) is True` 的结果。二者都依赖运行时行值；
        规划器可以给表达式定型，却不知道这些值。

3. **动手题。** 在一次性 worktree 中添加 `PhysicalOffset` 和
   `OffsetExecutor`：丢弃子节点前 *n* 行，再产出剩余行。不要修改教程作者
   当前工作树中的 `src/`。

    验收方式：增加 offset 为零、小于输入和大于输入的单元测试；证明下游求值
    报错时子节点的 `close()` 仍会调用；运行新测试及
    `tests/unit/executor/`。

    ??? note "参考答案"
        最小补丁应添加带 `child` 和 `offset` 的不可变物理节点，在
        `executor/factory.py` 中映射它，并实现一元执行器。它的 `_open()`
        打开子节点并最多调用 *n* 次 `next()`，遇到 `None` 即停止；
        `_next()` 此后直接委托。正常的 `UnaryExecutor._close()` 提供生命
        周期清理。只有当练习还要求 SQL `OFFSET` 时才扩展解析器和规划器；
        否则单测可直接构造物理节点。

## 小结

MiniPostgres 把不可变物理计划变为遵守一个小型需求拉取合同的有状态算子。
流式与阻塞型算法之所以能够组合，是因为父节点看到相同生命周期；类型化表达式
求值维持 SQL `NULL` 与 int64 规则；修改算子把 TID 带入存储；度量通过包装而
不是重写执行来实现。下一章会引入让执行更困难的移动目标：并发事务可能改变
一次拉取允许看到或修改哪个元组版本。
