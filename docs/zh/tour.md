# 一条查询的内核漫游

> **Language**: [English](../tour.md) | 简体中文

这份导览从 `Database.execute()` 接到一条 SQL 开始，沿真实执行路径走到页面、
事务与 WAL，再回到维护机制。每一站都用以下三档说明它和 PostgreSQL 的关系：

- **等价**：保留同一个核心契约或算法形状；不表示接口、文件格式逐字兼容。
- **有意简化**：机制方向相同，但缩小了语法、并发、统计或持久化边界。
- **语义相反**：为了让教学证据更直接，采取了与 PostgreSQL 相反的策略。

## 0. 总路线

```text
SQL text
  -> sql/ lexer + parser + binder
  -> planner/ logical rules + cost optimizer
  -> executor/ Volcano tree
  -> storage/indexed.py
       -> storage/heap.py
       -> index/btree.py
       -> storage/buffer.py
  -> transaction visibility + locks
  -> wal/
  -> maintenance/ ANALYZE, VACUUM, HOT
```

普通查询按前三站向下拉取行。写查询还会进入 MVCC、锁、索引维护和 WAL；之后
显式 `ANALYZE`/`VACUUM` 更新统计或回收旧版本。

## 1. SQL 文本成为已绑定语义

**本项目：** `src/minipostgres/sql/lexer.py`、`parser.py`、`binder.py`  
**PostgreSQL：** `src/backend/parser/scan.l`、`gram.y`、`analyze.c` 以及
`parse_*.c`  
**标注：有意简化**

Lexer 和递归下降 Parser 只生成语法 AST；Binder 才读取 catalog，解析表/列
身份、类型、别名、聚合合法性和上下文中的 `NULL`。这个“parse 后再
analyze/bind”的边界对应 PostgreSQL 的 raw parse tree 到 analyzed `Query`。
区别是 MiniPostgres 使用冻结的小语法和 JSON catalog，不承担 PostgreSQL 的
完整类型转换、命名空间、权限与系统 catalog 语义。

## 2. 逻辑计划成为物理计划

**本项目：** `src/minipostgres/planner/`、`catalog/statistics.py`、
`maintenance/analyze.py`  
**PostgreSQL：** `src/backend/optimizer/`、`src/backend/statistics/`，
以及系统 catalog `pg_statistic`  
**标注：有意简化**

`planner.py` 构造不可变逻辑计划，`rules.py` 做常量折叠、谓词下推和列裁剪，
`optimizer.py` 再比较 SeqScan/IndexScan、NestedLoop/HashJoin，并对 2–4
张表做有界动态规划（dynamic programming, DP）连接排序。

`ANALYZE` 产生行数、页数、空值比例（null fraction）、不同值数量
（distinct count）、最常见值（most common values, MCV）和等深直方图。
选择率估计先使用 MCV；非 MCV 的等值质量按剩余 distinct 分摊，范围条件再用
直方图插值。这对应 PostgreSQL 从 `pg_statistic` 的 MCV/直方图推导选择率，
但本项目做精确全表扫描、统计类型更少、代价常量固定，也没有扩展统计和大量
PostgreSQL 扫描/连接路径。

## 3. Volcano 执行树拉取行

**本项目：** `src/minipostgres/executor/base.py`、`factory.py`、
`operators.py`  
**PostgreSQL：** `src/backend/executor/execMain.c` 与 `node*.c`  
**标注：等价**

物理节点经 factory 变成执行器树。每个节点遵守
`open()` / `next()` / `close()`，父节点通过 `next()` 从子节点逐行拉取，
这就是 Volcano/迭代器（iterator）模型。`EXPLAIN ANALYZE` 的包装器仍保持
相同拉取契约，只累计每个节点的实际行数和耗时。

这里的“等价”是执行模型等价：PostgreSQL 的执行器以 `ExecProcNode`
驱动计划状态树；MiniPostgres 则使用 Python 对象和更少的节点类型。

## 4. DML、等待后的 EPQ 与索引协调

**本项目：** `executor/operators.py`、
`storage/indexed.py::replace_mvcc/delete_mvcc`  
**PostgreSQL：** `src/backend/executor/execMain.c`、
`nodeModifyTable.c` 中的 EvalPlanQual（EPQ）路径  
**标注：等价（简化版）**

UPDATE/DELETE 先从执行树收集候选 TID。写者取得元组锁后，可能发现另一事务已经
提交了更新；读已提交（Read Committed）此时对最新行重新计算原 WHERE 谓词。
谓词不再成立就跳过修改。这是工作树中新实现的 EPQ 谓词重查，保留了
PostgreSQL“等待后不能盲改旧候选”的关键语义。

简化之处是它只重查冻结表达式子集和单行最新版本，不重跑 PostgreSQL 完整的
EPQ 计划、触发器、分区路由等路径。可重复读（Repeatable Read）若快照版本与
锁后最新版本不同，则抛出序列化冲突。

## 5. 堆页面与 MVCC 可见性

**本项目：** `src/minipostgres/storage/heap.py`、
`storage/slotted.py`、`transaction/visibility.py`  
**PostgreSQL：** `src/backend/access/heap/heapam.c`、
`heapam_visibility.c` 中的 `HeapTupleSatisfiesMVCC`  
**标注：等价（有意简化的布局）**

堆由带校验和的 8192 字节分槽页面组成，TID 是稳定的
`(page_id, slot_id)`。版本头保存 `xmin`、`xmax` 和链后继；可见性判断先检查
创建者，再检查删除者是否在当前快照中可见。这保留了
`HeapTupleSatisfiesMVCC` 的核心判断顺序。

本项目的元组头、槽位格式和版本链不是 PostgreSQL 磁盘格式。尤其
`root_tid()` 为展示前驱关系会扫描所有版本，复杂度 O(N)；真实 PostgreSQL
依靠行指针重定向和 HOT 标志位直接定位，不应把这里的扫描当成生产实现方式。

## 6. 缓冲池与时钟扫描

**本项目：** `src/minipostgres/storage/buffer.py`、
`storage/replacer.py`  
**PostgreSQL：** `src/backend/storage/buffer/bufmgr.c`、
`freelist.c` 的时钟扫描（clock sweep）  
**标注：等价（简化版）**

PageGuard 拥有一个固定（pin）；被固定的帧不能淘汰。时钟指针扫过帧，有引用位
的先清位并获得第二次机会（second chance），没有引用且可淘汰的成为受害者。
脏页写出前必须先通过 WAL 刷新闸门。

PostgreSQL 使用共享缓冲区、使用计数、并发原子状态、后台写入器等生产设施；
这里是进程内、固定帧数、确定性策略，但固定、第二次机会和 WAL-before-data
三个契约方向一致。

## 7. B+Tree 查找、分裂与合并

**本项目：** `src/minipostgres/index/`  
**PostgreSQL：** `src/backend/access/nbtree/`  
**标注：有意简化**

第零页是元页面（metapage）；内部页保存分隔键/子节点，叶页保存编码后的
键/TID 和兄弟链。插入溢出时分裂并向上提升分隔键；删除不足时先向兄弟借，
再合并，必要时收缩根。点查和范围查最后返回堆 TID 候选，执行器仍会回堆重查。

这些结构对应 `nbtree`，但没有 PostgreSQL 的并发页面锁协议、高键
（high key）、右链接并发遍历、去重、后缀截断、清理周期等细节，键编码也只
覆盖本项目的有界标量集合。

## 8. 事务状态与快照

**本项目：** `transaction/status.py`、`snapshot.py`、`manager.py`  
**PostgreSQL：** `src/backend/access/transam/clog.c`（CLOG/`pg_xact`）与
`src/backend/utils/time/snapmgr.c`  
**标注：等价（简化版）**

状态表回答 XID 是进行中、已提交还是已中止，对应 CLOG 的事务提交状态职责。
快照保存 `xmax` 和活动 XID 集合：读已提交每条语句刷新，可重复读从首个数据
语句起固定，对应 snapmgr 的隔离级别快照生命周期。

状态表是内存/教学持久化模型，快照也没有子事务、命令 ID、快照导出/导入、
SSI 谓词锁等完整 PostgreSQL 内容。

## 9. 写者锁与死锁检测

**本项目：** `transaction/locks.py`、`deadlock.py`  
**PostgreSQL：** `src/backend/storage/lmgr/lock.c`、`proc.c`、
`deadlock.c`  
**标注：有意简化**

元组键和唯一键使用先进先出（first in, first out, FIFO）排他锁。队列中每个
等待者指向所有者和更早的等待者，形成等待图（wait-for graph）；检测到环时
选择最高 XID 作为确定性受害者。这对应 PostgreSQL 从锁等待关系检测死锁的
机制，但 PostgreSQL 有完整的锁模式/冲突矩阵、软边重排和不同的受害者处理。
本项目没有共享锁或 `SELECT FOR UPDATE`。

## 10. WAL、检查点与恢复

**本项目：** `src/minipostgres/wal/`、堆页面 LSN、缓冲区 WAL 闸门  
**PostgreSQL：** `src/backend/access/transam/xlog.c`、
`xloginsert.c` 与 `full_page_writes`  
**标注：语义相反（全页镜像策略）**

MiniPostgres 每次堆页面变更都记录完整的变更后镜像；提交记录 fsync 后才发布
提交，恢复以页面日志序列号（log sequence number, LSN）判断是否执行 REDO，
并在非干净恢复后重建派生索引。

PostgreSQL 在检查点后对某页的首次修改附带全页镜像（full-page image, FPI），
用它修复撕裂页面；同一检查点周期内后续修改通常只需更紧凑的生理式
（physiological）WAL 记录。PostgreSQL 这样设计是因为一次 FPI 已建立该页的
检查点后基线，后续记录操作/块内变化即可重放，可显著降低 WAL、复制和恢复
I/O。MiniPostgres“每次都整页”恰好相反：更浪费空间，但让 WAL-before-data
和幂等 REDO 很容易观察。它仅执行 REDO，也没有 PostgreSQL 的完整 WAL 记录
生态。

## 11. VACUUM、HOT 与统计维护

**本项目：** `src/minipostgres/maintenance/`、
`storage/indexed.py::vacuum`  
**PostgreSQL：** `src/backend/access/heap/vacuumlazy.c`、`heapam.c`
中的 HOT 路径，以及 `src/backend/commands/analyze.c`  
**标注：有意简化**

显式 VACUUM 从活动快照计算清理水位（cleanup horizon），先删除精确索引项，
再回收稳定槽位，并可剪掉 HOT 链中的死亡中间版本。HOT 更新要求替换版本实际
落在同一堆页面且编码后的所有索引键不变，因此索引继续指向根 TID。

PostgreSQL 的惰性清理（lazy vacuum）、HOT 重定向/死亡行指针、剪枝、可见性
映射、冻结、自动清理和统计采样要丰富得多。本项目采用同步显式维护，是为了让
“何时可回收、为何无需新增索引项”能由测试直接观察。

## 建议的阅读顺序

先用 `examples/demo.py` 跑一条带 WHERE 的 SELECT 和一条 UPDATE，再按
`engine.py -> sql/ -> planner/ -> executor/ -> storage/indexed.py` 追调用。
随后分别阅读 `transaction/visibility.py`、`storage/replacer.py` 和
`wal/recovery.py`，最后用 `LABS.md` 中的并发、淘汰和崩溃实验验证上述契约。
