# Hands-on Labs

> English · [中文版](zh/labs-guide.md)

Install from the repository root:

```bash
uv sync
```

## 1. End-to-end database tour

```bash
uv run python examples/demo.py
```

Expected landmarks:

```text
point lookup plan: Project -> IndexScan
repeatable-read snapshot: ((370,),) -> ((370,),) -> ((999,),)
vacuum: removed=1, hot_pruned=0
checkpoint LSN: <positive integer>
restart result: ((37, ..., 999),)
```

Watch one feature cross subsystem boundaries: an index-backed point lookup,
snapshot isolation, an update visible only to a fresh view, dead-version
reclamation, checkpointing, and recovery after reopen. The exact checkpoint
LSN and long payload rendering are implementation data, not assertions to copy.

## 2. Planning choices

```bash
uv run pytest -q \
  tests/unit/planner/test_scan_choice.py \
  tests/unit/planner/test_join_choice.py
```

Expected result: both files pass. Inspect the assertions and structured plans
to see when cost chooses SeqScan versus IndexScan and NestedLoop versus
HashJoin.

## 3. Buffer pool and WAL-before-data

```bash
uv run pytest -q \
  tests/unit/storage/test_buffer_pool.py \
  tests/reliability/test_wal_before_data.py
```

Expected result: both files pass. Watch pin ownership, Clock eviction, and the
flush gate that prevents a dirty page from reaching storage before its WAL.

## 4. Isolation, writer conflicts, and deadlocks

```bash
uv run pytest -q \
  tests/concurrency/test_read_phenomena.py \
  tests/concurrency/test_write_conflicts.py \
  tests/concurrency/test_deadlock.py
```

Expected result: all three files pass. Compare statement snapshots with fixed
transaction snapshots, then follow lock waits and deterministic victim choice.

## 5. Crash positions and REDO

```bash
uv run pytest -q \
  tests/crash/test_commit_matrix.py \
  tests/crash/test_checkpoint_matrix.py \
  tests/reliability/test_engine_recovery.py \
  tests/reliability/test_index_rebuild.py
```

Expected result: all four files pass. Each case injects a precise failure
boundary and checks whether committed state is recovered, incomplete state is
aborted, and derived indexes are rebuilt when required.

## 6. VACUUM and HOT

```bash
uv run pytest -q \
  tests/integration/test_vacuum_reuse.py \
  tests/integration/test_hot_update.py
```

Expected result: both files pass. Watch a long-lived snapshot delay slot reuse,
then observe how an update that preserves indexed keys can keep the index root.

The existing [lab index](https://github.com/system-in-miniature/MiniPostgres/blob/main/LABS.md)
lists the same experiments compactly. Run the entire collection with
`uv run pytest -q`.
