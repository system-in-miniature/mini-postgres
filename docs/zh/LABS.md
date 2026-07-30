# 可执行实验

> **语言**: [English](../labs-guide.md) | 简体中文

本仓库是已完成的参考项目，因此每个实验都是一项可执行测试，而不是教学章节。

| 机制（Mechanism） | 实验（Experiment） |
|---|---|
| 顺序扫描与索引扫描（SeqScan vs IndexScan） | `tests/unit/planner/test_scan_choice.py` |
| 嵌套循环与哈希连接（NestedLoop vs HashJoin） | `tests/unit/planner/test_join_choice.py` |
| 缓冲区固定（buffer pins）与 Clock 淘汰 | `tests/unit/storage/test_buffer_pool.py` |
| 读已提交与可重复读（Read Committed vs Repeatable Read） | `tests/concurrency/test_read_phenomena.py` |
| 写入者冲突与死锁 | `tests/concurrency/test_write_conflicts.py`, `tests/concurrency/test_deadlock.py` |
| 数据写入前先写预写式日志（WAL before data） | `tests/reliability/test_wal_before_data.py` |
| 提交/检查点的崩溃位置 | `tests/crash/test_commit_matrix.py`, `tests/crash/test_checkpoint_matrix.py` |
| REDO 与索引重建 | `tests/reliability/test_engine_recovery.py`, `tests/reliability/test_index_rebuild.py` |
| 长生命周期快照阻止清理（Vacuum） | `tests/integration/test_vacuum_reuse.py` |
| 仅堆元组（HOT）保留索引根 | `tests/integration/test_hot_update.py` |
| 阶段闭环 | `tests/acceptance/` |

使用 `uv run pytest -q` 运行所有实验。
