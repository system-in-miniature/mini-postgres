# 动手实验

> [English](../labs-guide.md) · 中文版

先在仓库根目录安装：

```bash
uv sync
```

## 1. 端到端数据库导览

```bash
uv run python examples/demo.py
```

预期关键输出：

```text
point lookup plan: Project -> IndexScan
repeatable-read snapshot: ((370,),) -> ((370,),) -> ((999,),)
vacuum: removed=1, hot_pruned=0
checkpoint LSN: <正整数>
restart result: ((37, ..., 999),)
```

重点观察一个功能如何跨越子系统：索引点查、快照隔离、只对新视图可见的更新、
死亡版本回收、checkpoint，以及重新打开后的恢复。具体 LSN 和长载荷展示是运行
数据，不是需要硬编码的断言。

## 2. 规划选择

```bash
uv run pytest -q \
  tests/unit/planner/test_scan_choice.py \
  tests/unit/planner/test_join_choice.py
```

预期两个文件都通过。查看断言与结构化计划，观察代价何时选择
SeqScan/IndexScan 与 NestedLoop/HashJoin。

## 3. 缓冲池与 WAL-before-data

```bash
uv run pytest -q \
  tests/unit/storage/test_buffer_pool.py \
  tests/reliability/test_wal_before_data.py
```

预期两个文件都通过。重点观察 pin 所有权、Clock 淘汰，以及阻止脏页先于 WAL
落盘的刷新闸门。

## 4. 隔离、写冲突与死锁

```bash
uv run pytest -q \
  tests/concurrency/test_read_phenomena.py \
  tests/concurrency/test_write_conflicts.py \
  tests/concurrency/test_deadlock.py
```

预期三个文件都通过。比较语句级快照和固定事务快照，再追踪锁等待与确定性受害者
选择。

## 5. 崩溃位置与 REDO

```bash
uv run pytest -q \
  tests/crash/test_commit_matrix.py \
  tests/crash/test_checkpoint_matrix.py \
  tests/reliability/test_engine_recovery.py \
  tests/reliability/test_index_rebuild.py
```

预期四个文件都通过。每个用例注入精确故障边界，检查已提交状态得到恢复、未完成
状态视为中止，并在需要时重建派生索引。

## 6. VACUUM 与 HOT

```bash
uv run pytest -q \
  tests/integration/test_vacuum_reuse.py \
  tests/integration/test_hot_update.py
```

预期两个文件都通过。观察长生命周期快照如何延迟槽位复用，以及索引键不变的更新
如何保留索引根。

已有[实验索引](LABS.md)提供同一组实验的紧凑列表；全部运行可用
`uv run pytest -q`。
