# MiniPostgres 行为证据

> **语言**: [English](../behavior-matrix.md) | 简体中文

此表特意采用机器可读格式。每一行都给出具体的源码归属方（source owner）和可直接
收集的 pytest 节点。

| 领域（Area） | 已实现约定 | 源码归属方 | 直接测试 | 有意保留的差异 |
|---|---|---|---|---|
| 查询路径（query_path） | SQL 经绑定、规划、优化后由 Volcano 算子执行。 | `src/minipostgres/engine.py` | `tests/integration/test_query_loop.py::test_insert_update_delete_and_expression_select` | 固定的 SQL 子集与直接 Python API。 |
| 分槽页（slotted_page） | 活跃槽位 ID 在压实后保持不变，已删除槽位可复用。 | `src/minipostgres/storage/slotted.py` | `tests/unit/storage/test_slotted_page.py::test_compaction_moves_bytes_without_renumbering_live_slots` | 自定义页体，而非 PostgreSQL 行指针（line pointers）。 |
| 缓冲池（buffer_pool） | 固定操作阻止淘汰，脏页刷写会先经过 WAL 门控。 | `src/minipostgres/storage/buffer.py` | `tests/reliability/test_wal_before_data.py::test_heap_change_is_logged_before_dirty_page_can_flush` | 进程内、确定性的 Clock 替换。 |
| B+Tree（btree） | 持久化有序键支持点访问、范围访问和结构变化。 | `src/minipostgres/index/btree.py` | `tests/integration/test_btree_restart.py::test_point_search_delete_and_range_survive_clean_restart` | 自定义 B+Tree 与键编码。 |
| 优化器（optimizer） | 统计信息、规则、成本与有界连接枚举保持结果不变。 | `src/minipostgres/planner/optimizer.py` | `tests/acceptance/test_phase_c.py::test_phase_c_scan_join_and_stale_statistics_crossovers` | 使用相对教学成本，不追求与 PostgreSQL 成本一致。 |
| 多版本并发控制（MVCC） | 读已提交刷新可见性快照，可重复读固定可见性快照。 | `src/minipostgres/transaction/visibility.py` | `tests/concurrency/test_read_phenomena.py::test_read_committed_refreshes_while_repeatable_read_keeps_snapshot` | 不支持可串行化快照隔离（Serializable Snapshot Isolation）。 |
| 锁（locks） | FIFO 元组锁/键锁串行化写入者；确定性死锁检测会中止 XID 最大的事务。 | `src/minipostgres/transaction/locks.py` | `tests/concurrency/test_deadlock.py::test_two_row_deadlock_aborts_highest_xid` | 仅支持进程内排他锁模式。 |
| 数据写入前先写 WAL（wal_before_data） | 完整堆页镜像在发布脏页前获得 LSN。 | `src/minipostgres/storage/heap.py` | `tests/reliability/test_page_lsn.py::test_committed_page_lsn_survives_restart` | 使用整页 REDO，而非 ARIES 生理日志记录。 |
| 持久提交（durable_commit） | 发布已提交状态并成功返回前，先刷写 COMMIT。 | `src/minipostgres/transaction/manager.py` | `tests/reliability/test_commit_protocol.py::test_commit_record_is_durable_before_transaction_is_published` | 同步 fsync；不支持组提交（group commit）。 |
| 重做（redo） | 启动时重放较新或损坏的页镜像，并重建派生索引。 | `src/minipostgres/wal/recovery.py` | `tests/reliability/test_engine_recovery.py::test_recovery_repairs_torn_post_checkpoint_heap_page` | 仅 REDO；未完成 XID 变为已中止，不执行物理 UNDO。 |
| 清理（vacuum） | 全局视界保护快照，同时回收失效版本和索引条目。 | `src/minipostgres/storage/indexed.py` | `tests/integration/test_vacuum_reuse.py::test_long_repeatable_snapshot_prevents_reclamation` | 手动同步 Vacuum；没有 autovacuum 或 XID 冻结。 |
| 仅堆元组（hot） | 同页且索引不变的更新保留一个索引根和快照可见链。 | `src/minipostgres/maintenance/hot.py`<br>`src/minipostgres/storage/indexed.py` | `tests/integration/test_hot_pruning.py::test_vacuum_prunes_dead_hot_intermediates_and_keeps_index_root` | 有界的教学型 HOT 链与剪枝。 |
