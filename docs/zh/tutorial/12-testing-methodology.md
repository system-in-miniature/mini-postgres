# 12. 测试方法论：从局部规则到 PostgreSQL 18

MiniPostgres 只有把机制变成可执行声明，而不只是看起来像某种架构，才能成为
可信的教学内核。解析器冒烟测试不能证明崩溃持久性；成功重启不能证明快照隔离；
与 PostgreSQL 匹配一条查询也不能证明内部页安全。因此，本仓库分层使用聚焦
测试、可执行合同、属性模型、集成/重启场景、对抗性并发与崩溃实验、最终验收，
以及必须显式配置的 PostgreSQL 18 差分配置。

本章把这些目录组织为五层证据。各层刻意重叠：高风险机制应从不止一个角度被
观察。

## 学习目标

完成本章后，你将能够：

- 选择能够证伪某项机制的最小测试层；
- 解释属性、集成、并发、崩溃与验收测试分别能证明和不能证明什么；
- 从行为矩阵声明追踪到源码所有者和可直接收集的 pytest 节点；
- 运行本地五层置信切片并解读结果；
- 配置 PostgreSQL 18 差分运行，而不把跳过的外部配置误当成兼容性通过。

## 第 1 层：局部规则与公开合同

单元测试隔离算法和状态转换，例如 lexer token、binder 名称解析、表达式算术、
分槽页压实、Clock 替换、B+Tree 分裂/合并、快照可见性、等待图环、WAL
分帧以及清理视界。失败会指向狭窄所有者，因此它是测试边界情况最便宜的一层。

合同测试位于相邻层级，但聚焦稳定的可观察行为：`QueryResult`、事务命令、
`EXPLAIN`、唯一性和公开模式约束。它们可以穿过多个类，但仍局限于一个 API
承诺。例如 `tests/contract/test_explain_analyze.py` 证明每个计划节点都有
估计和实际字段，并且分析不会改变选择行。

源码所有者正是本教程一直使用的函数：
`src/minipostgres/executor/expressions.py` 的 `evaluate()`、
`src/minipostgres/transaction/visibility.py` 的 `is_visible()`、
`src/minipostgres/wal/records.py` 的 `encode_record()` 与
`decode_record()`，以及 `src/minipostgres/maintenance/horizon.py` 的
`classify_version()`。

局部测试必要但不充分。正确的 `decode_record()` 测试无法证明引擎启动在正确
边界调用恢复。

## 第 2 层：属性与参考模型检查

示例测试枚举作者记得的情况。属性测试生成许多有效动作序列或值，并把实现与
更简单的模型比较。仓库使用 Hypothesis 检查：

- SQL 表达式求值与三值参考求值器；
- 分槽页与抽象稳定槽位模型；
- B+Tree 内容与有序 multimap；
- 堆行为与逻辑表模型；
- 编码键顺序与受支持标量顺序；
- 不同连接顺序保持相同结果；
- 选择率始终在概率边界内；
- VACUUM 幂等性。

例如 `tests/property/test_expression_model.py` 不是基准测试。它在 SQL
布尔值和运算符组合中寻找语义反例。
`tests/property/test_btree_multimap.py` 可以发现几个手写示例遗漏的结构序列：
插入、重复、删除、范围。

属性的质量取决于 oracle 与策略。比较两个共享同一错误辅助函数的路径，可能
制造虚假信心。参考模型应更小且结构独立，生成状态应覆盖 `NULL`、最小/最大
int64、页将满、重复键和重复清理等边界。

## 第 3 层：集成所有权与重启

集成测试会穿过单元测试刻意替换的边界：引擎到目录、执行器到堆、堆到缓冲区、
缓冲区到磁盘、B+Tree 发布以及干净重启。它们检查各自正确的组件是否以正确
顺序接线。

代表性测试创建数据库目录，通过 `src/minipostgres/engine.py` 的
`Database.execute_for_session()` 执行 SQL，关闭或重新打开，再断言目录、
行、索引、统计或度量。这会发现执行器绕过 `TableAccess`、干净关闭未刷脏页，
或索引关系持久化前就发布索引等问题。

重启十分关键，因为内存断言可以在持久状态错误时仍通过。
`tests/integration/test_btree_restart.py` 验证干净重启后的点/范围行为。HOT 与
VACUUM 集成节点会同时检查逻辑查询结果和物理/索引后果。
[架构参考](../ARCHITECTURE.md)描述了这些测试穿过的所有权边界。

## 第 4 层：对抗性调度与故障位置

并发测试使用独立 `DatabaseSession`、Python 线程和
`LockManager.waiting_xids()` 等可观察同步，构造不可重复读、固定 RR 快照、
写者等待、唯一性竞态和两行死锁。确定性屏障或队列观察比“sleep 然后希望竞态
已经发生”更强。

可靠性测试检查 WAL/页顺序和重启恢复。崩溃测试更进一步：子进程到达命名
failpoint 后终止，不执行正常清理。矩阵包含 WAL 追加/刷写前后、页写期间、
COMMIT 周围和检查点发布期间的位置。重启后，所有已经确认成功的持久事务必须
可见，不完整事务必须不可见，派生索引必须与堆事实一致。

`src/minipostgres/testing/failpoints.py` 的 `hit()` 是提交和存储路径使用的
狭窄注入边界。Failpoint 不是模拟持久化结果，而是创建精确中断位置，从而观察
真实磁盘恢复代码。

这些测试仍局限于一个进程的文件和 Python 并发。它们不能证明网络分区、复制、
每个平台的内核/文件系统行为，或 PostgreSQL 多进程共享内存交互。

## 第 5 层：验收、可追踪性与差分行为

验收测试把已完成机制组合为阶段与最终故事。
`tests/acceptance/test_final_acceptance.py` 创建 300 个带索引账户，分析统计，
观察 `IndexScan`，检查写者提交前后的 RR 可见性，执行 VACUUM、检查点和重开，
再验证数据与临时索引构建产物清理。正因为低层测试已经能定位失败，这种闭环
测试才有价值。

可追踪性防止宽泛验收变得含糊。
`src/minipostgres/acceptance.py` 中的 `load_behavior_matrix()` 把
`BEHAVIOR_MATRIX.md` 解析成 `BehaviorEvidence`：领域、合同、源码路径、测试
节点 ID 和刻意差异。它拒绝重复领域、缺失源码证据和缺失测试。因此每一行都是
机器可检查的“声明—所有者—测试”链接，而不是装饰性覆盖率表。

最后，`src/minipostgres/differential/postgres.py` 中的
`Postgres18.connect()` 导入 psycopg，连接显式提供的 DSN，并验证
`server_version_num` 位于 PostgreSQL 18 范围。
`Postgres18.execute()` 执行 SQL，并把获取的行规范化为元组。当前差分测试
证明配置的服务确实是 PostgreSQL 18，并返回预期的确定性字面量语义。该测试
尚未把同一条 SQL 交给 MiniPostgres，所以它是外部配置探针和适配器基础，
不是已经完成的双引擎差分比较。

预期的差分交集刻意很窄。真正的成对比较必须排除不支持 SQL、规划器文本、
成本/时序、错误字符串、区域排序规则和无序结果顺序。只有实际运行两个引擎后，
匹配才表示选定的可观察语义一致；它仍不会让 MiniPostgres 变成 PostgreSQL
兼容产品。

## 与 PostgreSQL 自身测试生态对照

PostgreSQL 使用大量回归、隔离、TAP、恢复、升级和平台/buildfarm 测试。
其源码树包含 expected-output 回归测试，以及用于受控并发排列的
`src/test/isolation` 调度器。MiniPostgres 借鉴“不同风险需要不同 harness”
的方法思想，而不是这些 harness 的格式。

MiniPostgres 的 `tests/differential/` 提供带版本门控的适配器，使真实
PostgreSQL 18 服务能够作为外部语义 oracle。当前测试验证这项配置；真正的
差分用例还必须运行 MiniPostgres 并比较规范化结果。PostgreSQL 不能作为
MiniPostgres 私有页字节、结构化计划对象、类型化 Python 异常或确定性最大
XID 受害者策略的 oracle。这些刻意差异列在
[与 PostgreSQL 的差异](../DIFFERENCES_FROM_POSTGRESQL.md)中，
[行为矩阵](../BEHAVIOR_MATRIX.md)把积极声明连到本地证据，
[PostgreSQL 映射](../postgresql-mapping.md)则给出概念对应分类。

## 动手实验：穿过五层的一条切片

该命令选择一个局部规则、一个属性模型、一条集成 SQL 循环、一项并发行为和
最终验收：

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline pytest -q \
  tests/unit/test_types.py \
  tests/property/test_expression_model.py \
  tests/integration/test_query_loop.py \
  tests/concurrency/test_read_phenomena.py \
  tests/acceptance/test_final_acceptance.py
```

实测输出：

```text
..........                                                               [100%]
10 passed in 7.55s
```

收集到的十个测试均通过。这是一条教学切片，不替代完整测试套件。

## PostgreSQL 18 差分配置——需运行时验证

该配置需要通过 DSN 访问 PostgreSQL 18 服务，因此需要 socket 访问，在当前
环境中标记为**需运行时验证**。本地仍在未提供 DSN 时收集了命令：

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline pytest -q \
  tests/differential/test_postgres18.py
```

本地实测输出：

```text
s                                                                        [100%]
=========================== short test summary info ============================
SKIPPED [1] tests/differential/test_postgres18.py:13: MINIPOSTGRES_PG18_DSN is not configured
1 skipped in 0.29s
```

这是跳过，不是通过。若某环境中可使用 PostgreSQL 18，可安装可选依赖组，创建
隔离测试数据库并提供 DSN 来完成运行时验证：

```bash
uv sync --group postgres18
MINIPOSTGRES_PG18_DSN='postgresql://USER:PASSWORD@HOST:5432/TEST_DB' \
  uv run pytest -q tests/differential/test_postgres18.py
```

未来差分用例可能包含修改操作，不要把它指向有价值数据。
`Postgres18.connect()` 即使能连接 PostgreSQL 17 或 19，也会拒绝版本。

## 练习

1. **理解题。** “活跃元组区间绝不重叠”应由哪一层负责？还需要哪一层证明
   这些页能跨重启保留？

    验收方式：选择两个不同层次，并解释它们不同的失败定位能力。

    ??? note "参考答案"
        分槽页的单元/属性测试应生成布局并在局部断言不重叠。集成/重启测试应
        通过缓冲/磁盘边界写出这些页，重开后再解码。前者隔离布局逻辑，后者
        验证接线与持久性。

2. **理解题。** 为什么上面的无 DSN 差分结果不算 PostgreSQL 一致性证据？

    验收方式：引用观察到的 pytest 状态和导致它的代码守卫。

    ??? note "参考答案"
        Pytest 报告 `SKIPPED`，不是 passed。测试检查
        `MINIPOSTGRES_PG18_DSN`，缺失时调用 `pytest.skip()`，所以没有 socket
        连接，也没有通过 `Postgres18.execute()` 完成比较。

3. **动手题。** 在一次性 worktree 中，为一个真实存在且尚未列出的合同增加
   行为矩阵行，并增加证明畸形行会被拒绝的解析器测试。不要修改教程作者工作树
   中的 `src/`。

    验收方式：矩阵行至少写一个源码路径、一个可收集的精确 pytest 节点 ID 和
    一项刻意差异；积极解析测试和畸形行测试都必须通过。

    ??? note "参考答案"
        选择一个已实现但尚未列出的行为，把准确源码所有者与节点 ID 加入
        `BEHAVIOR_MATRIX.md`。在
        `tests/acceptance/test_behavior_matrix.py` 中构造一个临时畸形表，
        例如列数错误或测试项缺失，断言 `load_behavior_matrix()` 抛出
        `ValueError`。不要为了满足格式虚构源码或测试。

4. **动手题。** 为 PostgreSQL 18 差分配置增加一个双方都支持的冻结只读
   表达式。

    验收方式：先增加本地 MiniPostgres 断言，再把规范化有序行与
    `Postgres18.execute()` 比较；说明为什么排除排序规则、规划器文本、时序
    和错误文本。在 PostgreSQL 18 上实跑前，结果仍标记为**需运行时验证**。

    ??? note "参考答案"
        有界候选可以是算术加显式 `NULL` 谓词；返回多行时必须使用
        `ORDER BY`。在隔离测试数据库中设置环境。检查服务版本守卫，用
        `MINIPOSTGRES_PG18_DSN` 运行精确差分节点并记录实时输出；本地跳过
        不算验收。

## 小结

可信度来自匹配的证据，而不只是测试数量。局部与合同测试隔离规则，属性模型
搜索状态空间，集成测试穿过所有权与重启边界，对抗性测试强制调度与崩溃位置，
验收加 PostgreSQL 18 适配器/配置为外部比较建立路径，但不会把当前跳过或
探针冒充成成对结果。行为矩阵让每个积极声明都附着于
源码、证据和一项刻意 PostgreSQL 差异。凭借这种方法，前面各章共同构成一套
可检查的数据库内核，而不是一组看似合理的图。
