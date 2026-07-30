# 可执行实验

> **Language**: [English](../../LABS.md) | 简体中文

本仓库是已完成的参考项目，因此每个实验都是一项可执行测试，而不是教学章节。

| Mechanism | Experiment |
|---|---|
| SeqScan vs IndexScan | `tests/unit/planner/test_scan_choice.py` |
| NestedLoop vs HashJoin | `tests/unit/planner/test_join_choice.py` |
| buffer pins and Clock eviction | `tests/unit/storage/test_buffer_pool.py` |
| Read Committed vs Repeatable Read | `tests/concurrency/test_read_phenomena.py` |
| writer conflicts and deadlocks | `tests/concurrency/test_write_conflicts.py`, `tests/concurrency/test_deadlock.py` |
| WAL before data | `tests/reliability/test_wal_before_data.py` |
| commit/checkpoint crash positions | `tests/crash/test_commit_matrix.py`, `tests/crash/test_checkpoint_matrix.py` |
| REDO and index rebuild | `tests/reliability/test_engine_recovery.py`, `tests/reliability/test_index_rebuild.py` |
| long snapshot blocks Vacuum | `tests/integration/test_vacuum_reuse.py` |
| HOT keeps the index root | `tests/integration/test_hot_update.py` |
| phase closure | `tests/acceptance/` |

使用 `uv run pytest -q` 运行所有实验。
