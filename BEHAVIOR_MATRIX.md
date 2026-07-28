# MiniPostgres Behavior Evidence

This table is intentionally machine-readable. Every row names a concrete
source owner and a directly collectable pytest node.

| Area | Implemented contract | Source owner | Direct tests | Deliberate difference |
|---|---|---|---|---|
| query_path | SQL is bound, planned, optimized, and executed through Volcano operators. | `src/minipostgres/engine.py` | `tests/integration/test_query_loop.py::test_insert_update_delete_and_expression_select` | Frozen SQL subset and direct Python API. |
| slotted_page | Live slot IDs survive compaction and deleted slots are reusable. | `src/minipostgres/storage/slotted.py` | `tests/unit/storage/test_slotted_page.py::test_compaction_moves_bytes_without_renumbering_live_slots` | Custom page body, not PostgreSQL line pointers. |
| buffer_pool | Pins prevent eviction and dirty flush crosses the WAL gate first. | `src/minipostgres/storage/buffer.py` | `tests/reliability/test_wal_before_data.py::test_heap_change_is_logged_before_dirty_page_can_flush` | Process-local deterministic Clock replacement. |
| btree | Persistent ordered keys support point/range access and structural changes. | `src/minipostgres/index/btree.py` | `tests/integration/test_btree_restart.py::test_point_search_delete_and_range_survive_clean_restart` | Custom B+Tree and key encoding. |
| optimizer | Statistics, rules, costs, and bounded join enumeration preserve results. | `src/minipostgres/planner/optimizer.py` | `tests/acceptance/test_phase_c.py::test_phase_c_scan_join_and_stale_statistics_crossovers` | Relative teaching costs, not PostgreSQL cost parity. |
| mvcc | Read Committed refreshes and Repeatable Read pins visibility snapshots. | `src/minipostgres/transaction/visibility.py` | `tests/concurrency/test_read_phenomena.py::test_read_committed_refreshes_while_repeatable_read_keeps_snapshot` | No Serializable Snapshot Isolation. |
| locks | FIFO tuple/key locks serialize writers and deterministic deadlock detection aborts highest XID. | `src/minipostgres/transaction/locks.py` | `tests/concurrency/test_deadlock.py::test_two_row_deadlock_aborts_highest_xid` | Exclusive process-local lock modes only. |
| wal_before_data | Full heap page images receive an LSN before dirty page publication. | `src/minipostgres/storage/heap.py` | `tests/reliability/test_page_lsn.py::test_committed_page_lsn_survives_restart` | Full-page REDO rather than ARIES physiological records. |
| durable_commit | COMMIT is flushed before committed status and successful return. | `src/minipostgres/transaction/manager.py` | `tests/reliability/test_commit_protocol.py::test_commit_record_is_durable_before_transaction_is_published` | Synchronous fsync; no group commit. |
| redo | Startup replays newer/corrupt page images and rebuilds derived indexes. | `src/minipostgres/wal/recovery.py` | `tests/reliability/test_engine_recovery.py::test_recovery_repairs_torn_post_checkpoint_heap_page` | REDO only; incomplete XIDs become aborted without physical UNDO. |
| vacuum | A global horizon protects snapshots while dead versions and index entries are reclaimed. | `src/minipostgres/storage/indexed.py` | `tests/integration/test_vacuum_reuse.py::test_long_repeatable_snapshot_prevents_reclamation` | Manual synchronous Vacuum; no autovacuum or XID freeze. |
| hot | Same-page unchanged-index updates retain one index root and snapshot-visible chains. | `src/minipostgres/maintenance/hot.py` | `tests/integration/test_hot_pruning.py::test_vacuum_prunes_dead_hot_intermediates_and_keeps_index_root` | Bounded teaching HOT chains and pruning. |
