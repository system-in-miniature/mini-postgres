# 第 6 章：代价规划

多个物理计划可以返回相同行。Planner 根据不完整证据选择：表大小、值分布、selectivity 公式和相对 cost model。MiniPostgres 把这些输入显式化，让计划选择可以解释，而不是神秘结论。

## 学习目标

完成本章后，你能够：

1. 描述 `analyze_table()` 产生的统计；
2. 用 MCV 与 histogram 估计 equality/range selectivity；
3. 比较 `CostModel.seq_scan()` 与 `index_scan()`；
4. 解释有界动态规划 join order；
5. 区分 EXPLAIN 估计与 EXPLAIN ANALYZE 测量。

## 从绑定语句到候选

`src/minipostgres/planner/planner.py::Planner.logical()` 把 bound statement 转为 `planner/logical.py` 的不可变 scan、filter、project、join、aggregate、sort、limit、modify 节点。`planner/rules.py::RuleOptimizer.rewrite()` 反复应用局部规则到稳定：常量折叠、把单侧谓词推到 inner join 下方，并标注 scan 所需最少列。

Logical plan 说明需要什么关系工作；`planner/optimizer.py::CostBasedOptimizer` 从 `planner/physical.py` 选择 `PhysicalSeqScan`、`PhysicalIndexScan`、`PhysicalNestedLoopJoin`、`PhysicalHashJoin` 等具体节点，并为每个节点填 estimated rows/cost。

`Database._optimize()` 用当前 catalog、statistics store 和 table access map 新建 optimizer，所以规划明确看到最近一次 ANALYZE 与已发布索引。

## ANALYZE 构造统计快照

`src/minipostgres/engine.py::Database._analyze()` 选定一张或全部表，调用 `src/minipostgres/maintenance/analyze.py::analyze_table()`。它扫描每个当前行；对教学数据规模，ANALYZE 是 exact full scan，而非采样。

`TableStatistics` 保存 row count、physical page count 和 column mapping；每个 `ColumnStatistics` 保存：

- null fraction；
- 精确 distinct count；
- 非 NULL min/max；
- 最多 10 个 MCV 及其占总行数比例；
- 非 MCV 值最多 11 个 equi-depth histogram bound。

MCV 按 count 降序，以 `KeyCodec` 字节作确定性 tie-breaker。构造 histogram 前先移除 MCV，避免重值占据大量 quantile 位置、遮蔽 residual distribution。`equi_depth_bounds()` 排序 residual values 并选等距 quantile position。

`src/minipostgres/catalog/statistics.py::StatisticsStore.replace()` 通过临时写、file fsync、rename、directory fsync 原子发布完整不可变快照。DML 调用 `mark_stale()`，不会静默重算。Stale estimate 可选择更慢计划，却不改变执行语义。

## Selectivity：有多少行存活

`src/minipostgres/planner/selectivity.py::SelectivityEstimator` 返回 clamp 到 `[0,1]` 的比例。Unsupported shape 与可恢复算术问题使用稳定默认 `1/3`。

Literal TRUE 估 1，FALSE/NULL 估 0；`NOT p` 用 `1-s(p)`；假设独立时 AND 相乘，OR 用 `a+b-ab`；`IS NULL` 读取 null fraction。

对 `column = constant`，`_equality()` 先查 MCV，命中即使用实测 fraction；否则把 residual non-null/non-MCV mass 均分给 residual distinct values。常量落在 min/max 外时可估为 0。

Range 估计把匹配 MCV mass 与 histogram interpolation 合并；`_histogram_less_fraction()` 找 bucket，`_interpolate()` 估算 bucket 内位置。它是估计，不承诺实际行数。Column-to-column 或无统计表达式回退到有界公式，所有结果保持合法概率，避免 NaN/负数污染 cost。

## 相对 Cost

`src/minipostgres/planner/cost.py` 冻结四个常量：

```text
sequential page = 1.0
random page     = 4.0
CPU tuple       = 0.01
CPU operator    = 0.0025
```

`Cost(startup, total)` 是相对工作单位，不是毫秒。`seq_scan(pages, rows)` 计顺序 page 与 per-row CPU；`index_scan(height, matching_rows, heap_pages)` 计树下降、随机 heap access 和候选 CPU。选择性高时索引便宜，dense range 的反复随机访问常比一次顺序扫描贵。

模型还计算 filter、projection、nested-loop comparison、hash build/probe、aggregate、sort、limit。Cost 可相加，排序先 total 后 startup；tie 通过构造顺序与显式比较确定性偏好 SeqScan/NestedLoop。

无统计时 `_table_size()` 使用 1000 rows/10 pages，但 `CostBasedOptimizer._scan()` 刻意不选 index path，避免基于虚构分布作看似精确的决定。

## Scan 选择

`CostBasedOptimizer._scan()` 读取表统计、估谓词 selectivity，并构造 SeqScan 加可选 Filter，再检查 published index。`_index_bounds()` 只接受单 indexed column 上的有限谓词，推导闭区间 encoded bound，拒绝 unsupported shape 或 NULL。

候选 index 使用 matching rows、heap pages 与 tree height 计算代价，与 sequential alternative 比较。`PhysicalIndexScan` 仍保留完整 predicate 供 heap recheck，以保护近似 bound 或 MVCC 版本变化下的正确性。

## Join 选择与动态规划

单个 join 由 `_join_alternatives()` 估输出行并比较 nested loop 与 hash join。只有 `_hash_join_keys()` 能提取跨输入 equality key 时才有 hash path；它 build 估计更小的一侧，并保留完整 ON condition 作 residual。

对 2–4 个 distinct relation 的 connected inner-join tree，`_join_dp()` 展平 leaves/predicates。它以单 relation 最优计划初始化 `JoinMemo`，再按集合大小枚举 bitmask；`_consider_partition()` 要求存在连接左右的 predicate，不凭空构造 Cartesian product。每个 relation set 保存按 cost 与确定性 tie-breaker 选出的最佳计划。最终 memo entry 是当前 path space 内全 relation 的最低代价 connected plan。五张及以上保留 source order；self-join 更早因 runtime relation ID 问题被拒绝。

## EXPLAIN 是结构化证据

`src/minipostgres/planner/physical.py::explain_plan()` 把物理树转换为不可变 `PlanExplanation`：node type、details、estimated rows/cost、可选 actual rows/elapsed ms、children。

`Database._explain()` 对普通 EXPLAIN 不执行 child；EXPLAIN ANALYZE 用 instrumentation wrapper 真正执行，并报告 per-node actual rows 与 monotonic elapsed milliseconds。这些时间描述本次 Python 执行，不是 PostgreSQL cost unit，也不是生产延迟预测。

## 实验：统计改变访问路径

运行：

```bash
uv run python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres import Database

def nodes(plan):
    return (plan.node_type,) + tuple(
        kind for child in plan.children for kind in nodes(child)
    )

with TemporaryDirectory() as root, Database.open(root) as db:
    db.execute(
        "CREATE TABLE users (id INT PRIMARY KEY, age INT, payload TEXT)"
    )
    for start in range(0, 300, 50):
        values = ", ".join(
            f"({n}, {n % 100}, '{'x' * 200}')"
            for n in range(start, start + 50)
        )
        db.execute(f"INSERT INTO users VALUES {values}")
    before = db.execute(
        "EXPLAIN SELECT * FROM users WHERE id = 7"
    ).plan
    db.execute("ANALYZE users")
    stats = db.statistics.table(db.catalog.table("users").table_id)
    sparse = db.execute(
        "EXPLAIN SELECT * FROM users WHERE id = 7"
    ).plan
    dense = db.execute(
        "EXPLAIN SELECT * FROM users WHERE age >= 0"
    ).plan
    assert before and stats and sparse and dense
    print("before-analyze", nodes(before))
    print("statistics", stats.row_count, stats.page_count,
          stats.columns[0].distinct_count)
    print("sparse", nodes(sparse))
    print("dense ", nodes(dense))
PY
```

实测输出：

```text
before-analyze ('Project', 'Filter', 'SeqScan')
statistics 300 11 300
sparse ('Project', 'IndexScan')
dense  ('Project', 'Filter', 'SeqScan')
```

ANALYZE 前安全回退为 SeqScan；精确统计记录 300 行、11 个 heap page、300 个 distinct ID，随后 sparse primary-key equality 选择 IndexScan，而 dense 且无索引的 age range 保持顺序扫描。

运行 join order 与 instrumentation 证据：

```bash
uv run pytest -q tests/unit/planner/test_join_order.py \
  tests/contract/test_explain_analyze.py
```

实测输出：

```text
...                                                                      [100%]
3 passed in 4.11s
```

两项均为 direct、无 socket 实验，已运行时验证。

## 与真实 PostgreSQL 对照

PostgreSQL 同样使用 MCV、histogram、selectivity function、相对 cost unit、scan/join alternative 与动态规划技术，相近代码跨 `src/backend/optimizer/`、`src/backend/statistics/`、ANALYZE 与 `pg_statistic`。

MiniPostgres 使用 exact full scan、很小的统计 schema 和固定常量，只支持 sequential/single-column B+Tree scan，connected join 只枚举到四张表；没有 extended statistics、bitmap/index-only/parallel/parameterized path、GEQO、planner GUC 或 PostgreSQL EXPLAIN 文本兼容。统计只由显式 ANALYZE 刷新。详见[差异页](../DIFFERENCES_FROM_POSTGRESQL.md)、[映射页](../postgresql-mapping.md)第 2 站和[行为矩阵](../BEHAVIOR_MATRIX.md) `optimizer` 行。

## 练习

### 1. 理解题：陈旧统计

为什么 stale statistics 可能改变 plan，却不能改变 query rows？

??? note "参考答案"

    统计只影响 cardinality/cost 估计和物理 path；所有 path 仍执行同一 bound predicate 并读取 authoritative heap row。坏估计浪费工作，不会重定义 SQL truth。

### 2. 理解题：移除 MCV

为何 histogram 构造前要移除 MCV occurrence？

??? note "参考答案"

    重值会占据许多 quantile position，降低剩余分布分辨率；其 mass 已在 MCV 中精确建模，histogram 应描述 residual values。

### 3. 动手题：观察 stale

建一行表并 ANALYZE，再插第二行，检查 `database.statistics.table(...)`，最后再次 ANALYZE。

验收方式：

- 首个 snapshot `row_count == 1`；
- DML 后 store 中仍 row count 1 且 `stale is True`；
- 刷新后 row count 2 且 `stale is False`。

??? note "参考答案"

    用 catalog table ID 每步重新从 store 取 snapshot。`mark_stale()` 会替换不可变对象，不能只拿着旧 Python 引用检查。

### 4. 动手设计题：index cost multiplier

提出可配置 random-page-cost 参数，但不改 `src/`。

验收方式：

- 默认行为兼容；
- 验证输入 finite 且 nonnegative；
- 参数进入 `CostModel`，而非在 optimizer 分支特判；
- 测试同一数据集在两个参数下发生 plan crossover。

??? note "参考答案"

    给 `CostModel` 增加默认 `random_page_cost=RANDOM_PAGE_COST` 构造参数并校验，在 `index_scan()` 使用实例值，再把配置模型传给 `CostBasedOptimizer`。单测固定统计与 index height，低值选 IndexScan、高值选 SeqScan，默认仍通过现有测试。

## 小结

ANALYZE 把当前行转换为不可变 MCV/histogram 证据；selectivity 把分布变成比例；cost model 把 cardinality 变成相对工作；optimizer 比较 scan、join 与有界 join order。EXPLAIN 暴露估计，EXPLAIN ANALYZE 加入执行测量。下一章将从选定的物理树进入真正 pull rows 的 Volcano executor。
