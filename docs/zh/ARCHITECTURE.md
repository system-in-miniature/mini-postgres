# 架构

> **Language**: [English](../architecture-reference.md) | 简体中文

## 查询流

```text
SQL text
   ↓
Lexer → Parser → syntax AST
                    ↓
                 Binder ← Catalog
                    ↓
              Logical Plan
                    ↓
          Fixed-point Rule Rewriter
                    ↓
      Statistics + Selectivity + Cost Model
                    ↓
              Physical Plan
                    ↓
              Volcano Executor
                    ↓
                TableAccess
                    ↓
           IndexedTableAccess
              ↙           ↘
         HeapTable        B+Tree
              ↘           ↙
               Buffer Pool
                    ↓
               DiskManager
```

解析器只负责语法。绑定器（Binder）是首个可解析表别名、列名、目录 ID、类型、
输出别名、聚合合法性和上下文 `NULL` 类型的层。

逻辑节点和物理节点都不可变。规则会折叠字面量表达式，将单侧谓词下推到内连接
下方，并标注最小扫描列集合。`CostBasedOptimizer` 随后比较顺序访问与 B+Tree
访问、嵌套循环连接与哈希连接，以及二至四个关系的连通连接顺序。更大的连接会
刻意保留源顺序。

`ANALYZE` 执行一次教育规模的精确堆扫描，并原子发布行数/页数、空值比例
（null fraction）、不同值数量（distinct count）、确定性的最常见值
（most common values, MCV）和等深直方图边界。选择率始终被限制在 `[0, 1]`；
缺失统计信息时使用稳定默认值。代价是相对工作单位，而不是毫秒。陈旧统计信息
可能产生较差计划，但不能改变结果行。

表缺失统计信息时默认使用 1,000 行和 10 页；这些默认值允许规划，但不允许选择
索引。不支持的谓词形状使用 `1/3` 选择率。等值条件先检查 MCV，再用剩余的非空
质量除以剩余不同值数量。范围条件将匹配的 MCV 质量与直方图插值结合；
`NOT`、`AND` 和 `OR` 使用补集与独立性公式。

冻结的相对常量为：

```text
sequential page = 1.0
random page     = 4.0
CPU tuple       = 0.01
CPU operator    = 0.0025
```

出现平局时优先选择 SeqScan 和 NestedLoop。HashJoin 提取一个跨输入等值键，
在估计较小的一侧构建哈希表，并将完整的 ON 谓词作为残余条件求值。连接记忆化
（join memo）再使用稳定关系 ID 和节点种类打破平局。

## 执行器所有权

每个执行器都遵循：

```python
open()
next() -> ExecutionRow | None
close()
```

`collect()` 保证成功和失败后都会关闭。行携带目录稳定的 `ColumnBinding` 键、
供修改算子使用的源 TID，以及投影和聚合产生的计算值。

`EXPLAIN ANALYZE` 在不改变拉取契约的情况下包装每个执行器。每个包装器统计
`open/next/close` 期间发出的行数和单调递增的耗时；即使失败，也会关闭每个
已打开的委托执行器。索引扫描遍历候选 TID，获取当前堆元组，并重新检查完整谓词。

修改执行器在调用 `TableAccess` 前，会完整求值并验证所有候选行。它们绝不直接
修改 Python 表容器。

## 稳定存储边界

`TableAccess` 拥有：

```text
insert
fetch
scan
replace
delete
```

`MemoryTable` 仍是可测试的参考实现。常规执行使用 `IndexedTableAccess`，它包装
一个 `HeapTable` 并同步维护每个已发布的 B+Tree。执行器不导入磁盘管理器、不
获取页面，也不直接修改存储容器。

## 页面与缓冲区所有权

堆和索引关系文件是带校验和的 8192 字节页面数组。通用封装绑定页面种类、关系
标识、页号、页面日志序列号（log sequence number, LSN）、边界和校验和。堆主体
使用稳定槽位：

```text
common page header
→ slotted-page header
→ slot directory growing right
→ free space
← tuple extents growing left
```

删除会将槽位标记为死亡。压缩会移动元组字节并更新范围，但绝不重编号活动槽位，
因此 `TID(page_id, slot_id)` 保持稳定。元组载荷包含模式指纹、`xmin`、
`xmax`、可选链 TID、空值位图和由模式指导的值。

所有常规页面 I/O 都经过固定帧缓冲池（buffer pool）。一个 `PageGuard` 拥有
一个固定（pin），且只释放一次。Clock 淘汰只能选择未固定帧。脏页刷新会在
`DiskManager.write_page` 前调用 WAL 闸门；堆变更先追加完整的页面后镜像，
再将其 WAL 位置安装为页面 LSN。

## 堆与索引持久化

近似空闲空间映射（free-space map）是原子替换的旁路文件。它可能返回假阳性
候选页面，但堆插入始终检查真实页面、修复陈旧估计、压缩一次，然后才分配新页。

B+Tree 的第零页是元页面（metapage）。内部页包含分隔键和子节点 ID；叶页包含
排序后的 `(encoded_key, TID)` 对和兄弟链接。分裂会向上传播分隔键，删除会
借用或合并，并可能折叠根；范围迭代只固定当前叶页。

DDL 发布遵循：

```text
prepare stable catalog identity
→ create/build and fsync physical relation
→ atomic rename when building an index
→ parent-directory fsync
→ publish catalog metadata
```

## 事务与持久性

目录通过以下过程写入确定性的版本化 JSON：

```text
temporary file
→ fsync
→ atomic replace
→ parent-directory fsync
```

每个会话最多拥有一个显式事务。读已提交（Read Committed）为每条语句获取新
快照；可重复读（Repeatable Read）保留第一个数据快照。元组版本携带创建者/
删除者 XID。元组锁和唯一键锁会串行化冲突写者，而等待图（wait-for graph）
选择确定性的死锁受害者。

提交会先追加并 fsync 其 WAL 记录，然后才发布已提交状态或返回成功。尖锐
检查点（sharp checkpoint）的顺序是：

```text
flush WAL
→ flush dirty frames
→ fsync relation files
→ append/fsync CHECKPOINT
→ atomic checksummed control-file replace
```

恢复会修复被撕裂的最终 WAL 记录、重建事务结果、将未完成事务标记为已中止，
并对缺失、损坏或较旧的堆页面执行 REDO。索引是派生状态，会在非干净恢复后重建。

清理（Vacuum）根据活动快照计算水位，在使稳定槽位可复用之前删除精确的陈旧
索引项，压缩页面字节并记录后镜像。当索引键不变且替换版本可放入源页面时，
仅堆元组更新（heap-only tuple, HOT）会保留被索引的根 TID。
