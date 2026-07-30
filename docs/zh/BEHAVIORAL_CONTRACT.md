# 行为约定

> **语言**: [English](../behavioral-contract.md) | 简体中文

## 值与谓词

- 整数为有符号 64 位值，溢出会引发错误；
- `INT64` 可拓宽为 `FLOAT64`；不存在其他隐式类型转换；
- 谓词使用 SQL 三值逻辑（three-valued logic）；
- `WHERE` 和连接条件只保留 `TRUE`；
- 除 `IS NULL`/`IS NOT NULL` 外，与 `NULL` 的比较均返回未知；
- 升序默认将空值置于末尾，降序默认将空值置于开头；
- 没有 `ORDER BY` 时不规定结果顺序。

## 名称与分组

- 关键字不区分大小写，并保留标识符的原始拼写；
- 拒绝未限定且存在歧义的列；
- 显式表别名会隐藏基础表名；
- `*` 按表/作用域顺序展开；
- `ORDER BY` 可以引用输出别名；
- 非聚合的选中列必须在结构上被 `GROUP BY` 覆盖；
- `WHERE`、连接谓词和 `GROUP BY` 中禁止使用聚合；
- 拒绝嵌套聚合。

## 聚合

- `COUNT(*)` 统计行数；
- `COUNT(expression)` 统计非空值；
- `SUM`、`AVG`、`MIN` 和 `MAX` 忽略空值；
- 空的全局聚合仍输出一行；
- 空输入上的 `COUNT` 返回零；
- 空输入上的其他聚合返回空值；
- `AVG` 返回 `FLOAT64`。

## 语句效果

- 一次 `parse()` 调用只接受一条完整语句；
- DDL 同步执行，并以原子方式持久化目录元数据；
- 插入和更新在变更前验证完整的候选集合；
- 多行插入发生唯一性失败时，会回滚该语句中更早的行；
- 更新/删除使用子执行器提供的源 TID；
- 运行时错误不会遗留处于打开状态的执行器树；
- `EXPLAIN` 不执行其子节点；
- `EXPLAIN ANALYZE` 会执行子节点、返回 SELECT 行，并报告每个物理节点的
  估算行数、实际行数和耗时。

## 统计信息与规划

- `ANALYZE` 发布一个完整且不可变的表统计信息快照；
- 统计信息在重启后保留，并在 DML 后保持不变，直至再次运行 `ANALYZE`；
- 最常见值（MCV）排序和等深直方图构造具有确定性；
- 每个选择率估算都是概率，缺少统计信息不会导致规划失败；
- 不支持的谓词形状使用选择率 `1/3`；
- 等值条件使用 MCV 频率，或按剩余不同值数均分剩余质量；
- 范围估算结合匹配的 MCV 与直方图插值；
- `NOT`、`AND` 和 `OR` 使用固定的补集/独立性公式；
- 成本值是相对单位，绝不预测挂钟时间；
- 确定性成本相同时选择顺序扫描；
- 确定性连接成本相同时选择嵌套循环连接；
- 索引扫描将索引条目视为候选，并对取回的堆元组重新检查完整谓词；
- 哈希连接保留重复项的重数和剩余 ON 谓词；
- 只对由两至四个关系组成的连通内连接重排；
- 具有五个或更多关系的计划保留源顺序；
- 统计信息与优化器改写不得改变查询结果。

## 持久化存储

- 每个关系页恰为 8192 字节，读取时校验校验和；
- 如果页中编码的关系、分支（fork）或页号与请求的 `PageKey` 不同，则拒绝该页；
- 活跃堆槽位 ID 在删除或压实期间绝不改变；
- 元组解码会验证模式指纹、长度、可空性、UTF-8、布尔值和载荷是否恰好耗尽；
- 空闲空间映射（free-space map）仅提供建议；使用前始终检查堆页；
- 只有未固定的缓冲帧可被淘汰；
- 页守卫至多释放一次固定；
- 脏页刷写会在写关系文件前调用 WAL 门控；
- 干净关闭会刷写所有已发布关系并执行 fsync；
- 干净重启会保留目录元数据、堆行、B+Tree 条目，以及插入、更新和删除执行的索引维护。

## B+Tree 索引

- 编码后的键字节顺序与已接受的标量/复合值顺序一致；
- 固定的 Phase B 子集拒绝空索引键；
- 重复插入 `(key, TID)` 是幂等的；
- 非唯一索引可让一个键对应多个 TID；
- 唯一索引拒绝已由另一 TID 占用的键；
- 已接受的单列 `PRIMARY KEY` 和 `UNIQUE` 声明会随表创建并发布持久唯一索引；
- 索引搜索结果只是候选，查询执行会使用堆重新检查；
- 叶节点链接在分裂、借位、合并和干净重启后仍保持有序；
- 范围边界为闭区间。

## 事务与恢复

- 读已提交（Read Committed）为每条语句取得新快照；
- 可重复读（Repeatable Read）复用事务的第一个数据快照；
- 当前事务可见自身插入，并隐藏自身删除；
- 已中止事务创建的元组绝不可见；
- 元组锁和唯一键锁按 FIFO 排队，并在提交或中止时释放；
- 检测到死锁时中止一个确定选出的受害者；
- 堆变更 WAL 先于携带相同 LSN 的脏页；
- 成功提交意味着其提交记录已经刷写；
- 最后一条不完整的 WAL 记录会被截断，更早的损坏则使恢复失败；
- 只有当已存储页缺失、损坏或更旧时才应用 REDO；
- 没有持久提交的事务在恢复后视为已中止；
- 非干净恢复依据已提交的堆事实重建派生 B+Tree 状态。

## Vacuum 与 HOT

- 仅当任何活跃的受支持快照都不可见某版本时，才回收该版本；
- 堆槽位变为可复用前，先移除完全匹配的失效索引条目；
- 压实不会重新编号幸存槽位；
- Vacuum 是幂等的，且不会缩小关系文件；
- 仅当所有索引键均未改变且替换版本能放入源页时，更新才属于仅堆元组
  （HOT）更新；
- HOT 保留被索引的根，并沿其链解析可见性。

## 证据

| 约定（Contract） | 直接证据 |
|---|---|
| 解析器语法与优先级 | `tests/unit/sql/test_parser_*.py` |
| 绑定与类型规则 | `tests/unit/sql/test_binder_*.py` |
| 三值求值 | `tests/property/test_expression_model.py` |
| 计划形状与连接降级 | `tests/unit/planner/` |
| 稳定的 MemoryTable TID | `tests/property/test_memory_table_model.py` |
| 带校验和的页与稳定槽位 | `tests/unit/storage/test_page_header.py`, `tests/property/test_slotted_page_model.py` |
| 元组格式 | `tests/unit/storage/test_tuple_codec.py`, `tests/property/test_tuple_codec_property.py` |
| 磁盘与缓冲区所有权 | `tests/unit/storage/test_disk_manager.py`, `tests/unit/storage/test_buffer_pool.py` |
| 持久堆 | `tests/integration/test_heap_table.py`, `tests/property/test_heap_table_model.py` |
| 有序键与持久 B+Tree | `tests/property/test_key_order.py`, `tests/unit/index/`, `tests/integration/test_btree_restart.py` |
| 引擎重启与唯一索引发布 | `tests/integration/test_engine_heap_restart.py`, `tests/integration/test_create_index.py`, `tests/contract/test_unique_index.py`, `tests/contract/test_schema_unique_constraints.py` |
| Volcano 算子行为 | `tests/unit/executor/test_query_operators.py` |
| 经过验证的变更 | `tests/unit/executor/test_modify_operators.py` |
| 公共 SQL 循环 | `tests/integration/test_query_loop.py` |
| 结构化 EXPLAIN 与清理 | `tests/contract/test_explain.py`, `tests/contract/test_explain_analyze.py`, `tests/integration/test_executor_cleanup.py`, `tests/integration/test_instrumentation_cleanup.py` |
| 统计信息与选择率 | `tests/contract/test_analyze.py`, `tests/unit/planner/test_selectivity.py`, `tests/property/test_selectivity_bounds.py` |
| 扫描与连接选择 | `tests/unit/planner/test_scan_choice.py`, `tests/unit/planner/test_join_choice.py`, `tests/unit/planner/test_join_order.py` |
| 优化后结果语义 | `tests/integration/test_optimizer_results.py`, `tests/property/test_join_order_equivalence.py` |
| Phase A 闭环 | `tests/acceptance/test_phase_a.py` |
| Phase B 闭环 | `tests/acceptance/test_phase_b.py` |
| Phase C 闭环 | `tests/acceptance/test_phase_c.py` |
| 事务/MVCC 闭环 | `tests/acceptance/test_phase_d.py`, `tests/concurrency/` |
| WAL/检查点/崩溃恢复 | `tests/reliability/`, `tests/crash/` |
| Vacuum/HOT 闭环 | `tests/integration/test_vacuum_reuse.py`, `tests/integration/test_hot_update.py`, `tests/acceptance/test_phase_e.py` |
