# Phase E Vacuum, HOT, and Final Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reclaim globally dead tuple versions and stale index entries, reuse stable slots safely, implement same-page heap-only update chains, and produce requirement-by-requirement final acceptance evidence for the completed reference project.

**Architecture:** Vacuum computes one horizon from active snapshots and classifies physical versions without changing logical visibility. Under a table maintenance lock it removes index entries before making slots reusable, compacts bytes without renumbering live slots, and repairs free-space/statistics metadata. HOT updates retain one indexed root TID and link same-page non-indexed versions; heap fetch follows and visibility-checks the chain, while Vacuum prunes only globally dead intermediates.

**Tech Stack:** Python 3.12, standard library, uv, pytest, Hypothesis, optional PostgreSQL 18 DSN profile, Ruff, Pyright.

---

## File map

```text
src/minipostgres/maintenance/horizon.py     global cleanup horizon
src/minipostgres/maintenance/vacuum.py      dead-version/index reclamation
src/minipostgres/maintenance/hot.py         HOT eligibility and chain helpers
src/minipostgres/maintenance/coordinator.py table maintenance locks
src/minipostgres/differential/postgres.py   optional PG18 comparison adapter
src/minipostgres/acceptance.py              structured evidence matrix
tests/unit/maintenance/
tests/concurrency/test_vacuum_snapshots.py
tests/integration/test_vacuum_reuse.py
tests/integration/test_hot_update.py
tests/reliability/test_vacuum_recovery.py
tests/differential/test_postgres18.py
tests/acceptance/test_final_acceptance.py
```

### Task 1: Cleanup horizon and dead-version classification

**Files:**
- Create: `src/minipostgres/maintenance/__init__.py`
- Create: `src/minipostgres/maintenance/horizon.py`
- Create: `tests/unit/maintenance/test_horizon.py`
- Create: `tests/property/test_dead_version_classifier.py`

- [ ] **Step 1: Write failing horizon/classification tests**

```python
def test_horizon_is_oldest_snapshot_or_next_xid(manager) -> None:
    first = active_transaction_with_snapshot(xmax=20, active={7, 11})
    second = active_transaction_with_snapshot(xmax=30, active={17})
    assert cleanup_horizon((first, second), next_xid=40) == 7
    assert cleanup_horizon((), next_xid=40) == 40


def test_aborted_creator_and_old_committed_delete_are_globally_dead(statuses) -> None:
    assert classify_version(
        TupleVersion(xmin=7, xmax=0, next_tid=None, values=(1,)),
        horizon=20,
        statuses=statuses.with_status(7, ABORTED),
    ) is VersionDisposition.DEAD
    assert classify_version(
        TupleVersion(xmin=5, xmax=9, next_tid=None, values=(1,)),
        horizon=20,
        statuses=statuses.with_committed(5, 9),
    ) is VersionDisposition.DEAD
```

Property tests prove that a version classified DEAD is invisible to every
supported snapshot whose horizon is at or above the cleanup horizon.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/maintenance/test_horizon.py \
  tests/property/test_dead_version_classifier.py
```

Expected: maintenance horizon components do not exist.

- [ ] **Step 3: Implement conservative global classification**

`cleanup_horizon` considers every active transaction's snapshot xmax and
active XIDs; a transaction that has not acquired a snapshot contributes its
own XID. Classify:

- aborted creator older than horizon as DEAD;
- committed creator plus committed deleter both older than horizon as DEAD;
- every in-progress/new creator/deleter or linked version as KEEP unless the
  above proof is complete.

No XID wraparound/freeze logic is added.

- [ ] **Step 4: Run horizon tests**

```bash
uv run pytest -q tests/unit/maintenance/test_horizon.py \
  tests/property/test_dead_version_classifier.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/maintenance tests/unit/maintenance \
  tests/property/test_dead_version_classifier.py
git commit -m "feat: prove the Vacuum cleanup horizon"
```

### Task 2: Table maintenance coordination

**Files:**
- Create: `src/minipostgres/maintenance/coordinator.py`
- Modify: `src/minipostgres/storage/heap.py`
- Create: `tests/unit/maintenance/test_coordinator.py`
- Create: `tests/concurrency/test_vacuum_writers.py`

- [ ] **Step 1: Write failing reader/writer maintenance tests**

```python
def test_maintenance_waits_for_active_table_writer(coordinator) -> None:
    with coordinator.writer(table_id=1):
        pending = run_async(coordinator.acquire_maintenance, table_id=1)
        assert not pending.done()
    lease = pending.result(timeout=1)
    lease.release()


def test_new_writer_waits_behind_queued_maintenance(coordinator) -> None:
    writer = coordinator.acquire_writer(table_id=1)
    maintenance = run_async(coordinator.acquire_maintenance, table_id=1)
    next_writer = run_async(coordinator.acquire_writer, table_id=1)
    writer.release()
    lease = maintenance.result(timeout=1)
    assert not next_writer.done()
    lease.release()
    next_writer.result(timeout=1).release()
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/maintenance/test_coordinator.py \
  tests/concurrency/test_vacuum_writers.py
```

Expected: no maintenance coordination exists.

- [ ] **Step 3: Implement fair per-table maintenance leases**

Normal readers require no maintenance lease because MVCC protects visibility.
Heap/index writers acquire shared writer leases. Vacuum and index rebuild
acquire an exclusive maintenance lease. Once maintenance queues, new writers
wait behind it to prevent starvation. Leases are context managers and release
exactly once on every exception path.

- [ ] **Step 4: Run coordination tests**

```bash
uv run pytest -q tests/unit/maintenance/test_coordinator.py \
  tests/concurrency/test_vacuum_writers.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands terminate and pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/maintenance/coordinator.py \
  src/minipostgres/storage/heap.py tests/unit/maintenance \
  tests/concurrency/test_vacuum_writers.py
git commit -m "feat: coordinate table maintenance and writers"
```

### Task 3: Vacuum index cleanup before slot reuse

**Files:**
- Create: `src/minipostgres/maintenance/vacuum.py`
- Modify: `src/minipostgres/engine.py`
- Create: `tests/integration/test_vacuum_reuse.py`
- Create: `tests/integration/test_vacuum_indexes.py`
- Create: `tests/concurrency/test_vacuum_snapshots.py`

- [ ] **Step 1: Write failing reclaim/snapshot tests**

```python
def test_vacuum_removes_index_entry_before_reusing_slot(engine) -> None:
    old_tid = insert_commit_delete_commit(engine, key=7)
    events = record_maintenance_events(engine)
    engine.execute("VACUUM users")
    new_tid = engine.execute("INSERT INTO users VALUES (8, 'new')").inserted_tids[0]
    assert new_tid == old_tid
    assert events.index(("index_delete", old_tid)) < events.index(
        ("slot_reusable", old_tid)
    )
    assert engine.execute("SELECT * FROM users WHERE id = 7").rows == ()


def test_long_snapshot_prevents_old_version_reclamation(engine) -> None:
    reader = begin_repeatable_reader_of_age_20(engine)
    engine.execute("UPDATE users SET age = 21")
    first = engine.execute("VACUUM users").maintenance
    assert first.dead_versions_removed == 0
    reader.execute("COMMIT")
    second = engine.execute("VACUUM users").maintenance
    assert second.dead_versions_removed == 1
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/integration/test_vacuum_reuse.py \
  tests/integration/test_vacuum_indexes.py \
  tests/concurrency/test_vacuum_snapshots.py
```

Expected: VACUUM is bound but not implemented.

- [ ] **Step 3: Implement ordered physical reclamation**

Under maintenance lease:

1. capture one cleanup horizon;
2. scan every physical heap slot and classify versions;
3. for each DEAD version, derive every indexed key from its values;
4. WAL-log and remove exact `(key, TID)` index entries;
5. WAL-log a heap page image marking the slot dead/reusable;
6. compact page tuple bytes without changing live slot IDs;
7. update free-space category and counters.

If index deletion fails, do not free the slot. VACUUM returns immutable counts
for scanned pages, removed versions/index entries, compacted pages, and
reclaimed bytes. Relation files do not shrink.

- [ ] **Step 4: Run Vacuum tests**

```bash
uv run pytest -q tests/integration/test_vacuum_reuse.py \
  tests/integration/test_vacuum_indexes.py \
  tests/concurrency/test_vacuum_snapshots.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/maintenance/vacuum.py src/minipostgres/engine.py \
  tests/integration tests/concurrency/test_vacuum_snapshots.py
git commit -m "feat: vacuum dead tuple versions"
```

### Task 4: Vacuum WAL/recovery idempotence

**Files:**
- Modify: `src/minipostgres/maintenance/vacuum.py`
- Modify: `src/minipostgres/wal/recovery.py`
- Create: `tests/reliability/test_vacuum_recovery.py`
- Create: `tests/property/test_vacuum_idempotence.py`

- [ ] **Step 1: Write failing crash/idempotence tests**

```python
@pytest.mark.parametrize(
    "failpoint",
    [
        "vacuum_after_index_delete",
        "vacuum_after_heap_wal_flush",
        "vacuum_after_heap_page_write",
    ],
)
def test_vacuum_crash_rebuilds_equivalent_index_and_heap(tmp_path, failpoint) -> None:
    run_vacuum_worker_until_crash(tmp_path, failpoint)
    db = Database.open(tmp_path)
    assert index_scan_rows(db, "users_id") == seq_scan_rows(db, "users")
    assert_no_live_tid_aliases(db)


@given(reclaimable_heap_states())
def test_vacuum_twice_has_same_physical_state_as_once(state) -> None:
    once = vacuum(state)
    twice = vacuum(once)
    assert physical_heap_digest(twice) == physical_heap_digest(once)
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/reliability/test_vacuum_recovery.py \
  tests/property/test_vacuum_idempotence.py
```

Expected: maintenance mutations are not fully crash-tested.

- [ ] **Step 3: Make each cleanup action replay-safe**

Exact index deletion is idempotent. Heap slot removal is one
HEAP_PAGE_IMAGES record with a complete post-image and normal page-LSN gate.
Crash before heap image may leave an index missing, but unclean recovery
rebuilds indexes before open. Crash after heap image cannot expose stale TID
because recovery also rebuilds indexes. A second Vacuum sees no live/dead
version in an already free slot.

- [ ] **Step 4: Run reliability tests**

```bash
uv run pytest -q tests/reliability/test_vacuum_recovery.py \
  tests/property/test_vacuum_idempotence.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/maintenance/vacuum.py \
  src/minipostgres/wal/recovery.py tests/reliability \
  tests/property/test_vacuum_idempotence.py
git commit -m "feat: recover Vacuum maintenance safely"
```

### Task 5: HOT eligibility and same-page insertion

**Files:**
- Create: `src/minipostgres/maintenance/hot.py`
- Modify: `src/minipostgres/storage/heap.py`
- Modify: `src/minipostgres/executor/operators.py`
- Create: `tests/unit/maintenance/test_hot_eligibility.py`
- Create: `tests/integration/test_hot_update.py`

- [ ] **Step 1: Write failing HOT decision/update tests**

```python
def test_hot_requires_unchanged_index_columns_and_same_page_space(table_meta) -> None:
    assert hot_eligible(
        changed_column_ids={2},
        indexed_column_ids={0},
        source_free_bytes=500,
        encoded_tuple_bytes=200,
    )
    assert not hot_eligible({0}, {0}, 500, 200)
    assert not hot_eligible({2}, {0}, 100, 200)


def test_hot_update_keeps_one_index_entry_and_links_versions(engine) -> None:
    root_tid = insert_indexed_user(engine, age=20)
    before = index_entries(engine, "users_id", key=1)
    engine.execute("UPDATE users SET age = 21 WHERE id = 1")
    after = index_entries(engine, "users_id", key=1)
    assert before == after == (root_tid,)
    root = physical_version(engine, root_tid)
    assert root.next_tid is not None
    assert root.next_tid.page_id == root_tid.page_id
    assert engine.execute("SELECT age FROM users WHERE id = 1").rows == ((21,),)
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/maintenance/test_hot_eligibility.py \
  tests/integration/test_hot_update.py
```

Expected: ordinary update adds a new index entry.

- [ ] **Step 3: Implement HOT as an update optimization**

Compute changed target column IDs from bound assignments and indexed column
IDs from catalog. Under tuple lock/page guard, pre-encode the new version and
check contiguous/compactable source-page space. If eligible:

1. insert new version on source page;
2. set old version `xmax=current_xid` and `next_tid=new_tid`;
3. WAL-log one post-image for the page;
4. retain all original index entries.

If any condition fails, use ordinary cross-page update/index maintenance.
Index candidates identify HOT roots; heap fetch follows `next_tid` with a
visited-set and maximum chain length equal to live slots on that page, raising
`CorruptPage` on cycles/off-page links.

- [ ] **Step 4: Run HOT tests**

```bash
uv run pytest -q tests/unit/maintenance/test_hot_eligibility.py \
  tests/integration/test_hot_update.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/maintenance/hot.py src/minipostgres/storage/heap.py \
  src/minipostgres/executor/operators.py tests
git commit -m "feat: update nonindexed columns with HOT"
```

### Task 6: HOT chain visibility and fallback

**Files:**
- Modify: `src/minipostgres/storage/heap.py`
- Create: `tests/concurrency/test_hot_visibility.py`
- Create: `tests/integration/test_hot_fallback.py`
- Create: `tests/property/test_hot_chain.py`

- [ ] **Step 1: Write failing snapshot/fallback tests**

```python
def test_hot_chain_returns_version_for_each_snapshot(engine) -> None:
    old_reader = begin_repeatable_reader(engine)
    engine.execute("UPDATE users SET age = 21 WHERE id = 1")
    new_reader = begin_repeatable_reader(engine)
    engine.execute("UPDATE users SET age = 22 WHERE id = 1")
    assert old_reader.execute("SELECT age FROM users WHERE id = 1").rows == ((20,),)
    assert new_reader.execute("SELECT age FROM users WHERE id = 1").rows == ((21,),)
    assert engine.execute("SELECT age FROM users WHERE id = 1").rows == ((22,),)


def test_indexed_column_or_full_page_falls_back_to_normal_update(engine) -> None:
    root = insert_user_on_nearly_full_page(engine)
    engine.execute("UPDATE users SET id = 2 WHERE id = 1")
    assert index_entries(engine, "users_id", 1) == (root,)
    assert len(index_entries(engine, "users_id", 2)) == 1
    fill_source_page(engine)
    engine.execute("UPDATE users SET age = 99 WHERE id = 2")
    assert latest_version(engine, 2).page_id != root.page_id
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/concurrency/test_hot_visibility.py \
  tests/integration/test_hot_fallback.py tests/property/test_hot_chain.py
```

Expected: chain traversal/fallback edge cases fail.

- [ ] **Step 3: Select the first visible chain member**

Starting from the indexed root, decode each same-page linked version in order
and return the newest member visible to the supplied snapshot/current XID.
Sequential scans skip HOT continuation slots as roots and yield a chain at
most once. Ordinary update breaks no existing chain: it adds a normal index
entry for the new key/version and leaves old root candidates for old snapshots.

- [ ] **Step 4: Run HOT visibility/fallback tests**

```bash
uv run pytest -q tests/concurrency/test_hot_visibility.py \
  tests/integration/test_hot_fallback.py tests/property/test_hot_chain.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/storage/heap.py tests/concurrency \
  tests/integration/test_hot_fallback.py tests/property/test_hot_chain.py
git commit -m "feat: resolve HOT chains per snapshot"
```

### Task 7: HOT pruning during Vacuum

**Files:**
- Modify: `src/minipostgres/maintenance/vacuum.py`
- Modify: `src/minipostgres/maintenance/hot.py`
- Create: `tests/integration/test_hot_pruning.py`
- Create: `tests/reliability/test_hot_recovery.py`

- [ ] **Step 1: Write failing chain-pruning tests**

```python
def test_vacuum_prunes_dead_middle_versions_and_preserves_root_tid(engine) -> None:
    root = build_committed_hot_chain(engine, ages=(20, 21, 22, 23))
    report = engine.execute("VACUUM users").maintenance
    assert report.hot_versions_pruned == 3
    assert index_entries(engine, "users_id", 1) == (root,)
    assert physical_version(engine, root).next_tid == latest_tid(engine, 1)
    assert engine.execute("SELECT age FROM users WHERE id = 1").rows == ((23,),)


def test_active_snapshot_keeps_needed_hot_intermediate(engine) -> None:
    reader = snapshot_at_hot_age(engine, 21)
    extend_hot_chain(engine, ages=(22, 23))
    engine.execute("VACUUM users")
    assert reader.execute("SELECT age FROM users WHERE id = 1").rows == ((21,),)
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/integration/test_hot_pruning.py \
  tests/reliability/test_hot_recovery.py
```

Expected: Vacuum treats versions independently and cannot rewrite chains.

- [ ] **Step 3: Prune only globally dead intermediates**

Walk each HOT root under maintenance lease. Keep root slot while an index
points to it. For each DEAD intermediate, link its predecessor directly to its
successor, then free the intermediate slot in the same WAL page image. If the
root's own tuple version is dead but a live successor exists, retain the root
slot as a redirect containing only `next_tid`; it remains the index target.
Detect corrupt cycles/off-page links before mutation. Recovery uses the page
post-image and index rebuild, making pruning idempotent.

- [ ] **Step 4: Run pruning/recovery tests**

```bash
uv run pytest -q tests/integration/test_hot_pruning.py \
  tests/reliability/test_hot_recovery.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/maintenance tests/integration/test_hot_pruning.py \
  tests/reliability/test_hot_recovery.py
git commit -m "feat: prune globally dead HOT versions"
```

### Task 8: Vacuum refreshes physical statistics and free space

**Files:**
- Modify: `src/minipostgres/maintenance/vacuum.py`
- Modify: `src/minipostgres/catalog/statistics.py`
- Modify: `src/minipostgres/storage/free_space.py`
- Create: `tests/integration/test_vacuum_metadata.py`

- [ ] **Step 1: Write failing metadata repair tests**

```python
def test_vacuum_repairs_fsm_and_invalidates_stale_logical_stats(engine) -> None:
    seed_update_bloat(engine)
    engine.execute("ANALYZE users")
    old_stats = engine.statistics.table(users_id)
    report = engine.execute("VACUUM users").maintenance
    assert report.reclaimed_bytes > 0
    assert engine.heap("users").free_space.matches_physical_pages()
    assert engine.statistics.table(users_id).stale
    engine.execute("ANALYZE users")
    assert not engine.statistics.table(users_id).stale
    assert engine.statistics.table(users_id).row_count < old_stats.row_count
```

- [ ] **Step 2: Run test and verify RED**

```bash
uv run pytest -q tests/integration/test_vacuum_metadata.py
```

Expected: Vacuum does not coordinate all metadata.

- [ ] **Step 3: Publish post-maintenance metadata**

After all page changes are durable in buffer/WAL order, write the complete FSM
sidecar by atomic replace and mark table statistics stale without changing
their prior values. Optimizer uses stale stats but exposes the stale flag in
EXPLAIN. Vacuum never runs ANALYZE implicitly.

- [ ] **Step 4: Run metadata tests**

```bash
uv run pytest -q tests/integration/test_vacuum_metadata.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/maintenance/vacuum.py \
  src/minipostgres/catalog/statistics.py \
  src/minipostgres/storage/free_space.py tests/integration/test_vacuum_metadata.py
git commit -m "feat: repair storage metadata after Vacuum"
```

### Task 9: Optional PostgreSQL 18 differential profile

**Files:**
- Create: `src/minipostgres/differential/__init__.py`
- Create: `src/minipostgres/differential/postgres.py`
- Create: `tests/differential/test_postgres18.py`
- Create: `tests/differential/cases.py`

- [ ] **Step 1: Write profile-gated comparison tests**

```python
@pytest.mark.parametrize("case", frozen_differential_cases())
def test_frozen_sql_subset_matches_postgres18(case, minipg, postgres18) -> None:
    case.setup(minipg, postgres18)
    assert normalize(case.run(minipg)) == normalize(case.run(postgres18))


def test_differential_profile_is_explicitly_skipped_without_dsn() -> None:
    result = run_pytest_without_env("tests/differential/test_postgres18.py")
    assert "skipped" in result.stdout
    assert result.returncode == 0
```

- [ ] **Step 2: Run default profile and verify RED**

```bash
uv run pytest -q tests/differential/test_postgres18.py
```

Expected: adapter/profile gate is absent.

- [ ] **Step 3: Implement an optional psycopg profile**

Add `psycopg[binary]` to a named `postgres18` dependency group, not default
runtime dependencies. Activate only when `MINIPOSTGRES_PG18_DSN` is set.
Verify `SHOW server_version_num` is between `180000` and `189999`; otherwise
skip with a precise reason.

Compare only frozen deterministic cases covering literals/null logic, DML,
inner join, aggregates, explicit ordering, Read Committed, and Repeatable Read.
Normalize result values and command effects. Do not compare errors, planner
text, timing, locale collation, FLOAT NaN behavior, or unordered rows.

- [ ] **Step 4: Run default and configured commands**

```bash
uv run pytest -q
uv sync --group postgres18
MINIPOSTGRES_PG18_DSN="$MINIPOSTGRES_PG18_DSN" \
  uv run --group postgres18 pytest -q tests/differential
```

Expected: default suite skips external cases cleanly; configured command passes
when a PostgreSQL 18 service is available. Absence of a configured service is
not presented as live differential proof.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/minipostgres/differential tests/differential
git commit -m "test: compare the frozen subset with PostgreSQL 18"
```

### Task 10: Structured final evidence matrix

**Files:**
- Create: `src/minipostgres/acceptance.py`
- Create: `BEHAVIOR_MATRIX.md`
- Create: `tests/acceptance/test_behavior_matrix.py`

- [ ] **Step 1: Write failing evidence-coverage test**

```python
def test_every_graduation_requirement_has_direct_evidence() -> None:
    matrix = load_behavior_matrix(Path("BEHAVIOR_MATRIX.md"))
    required = {
        "query_path", "slotted_page", "buffer_pool", "btree",
        "optimizer", "mvcc", "locks", "wal_before_data",
        "durable_commit", "redo", "vacuum", "hot",
    }
    assert matrix.keys() >= required
    for entry in matrix.values():
        assert entry.source_paths
        assert entry.test_nodeids
        assert all(pytest_node_exists(nodeid) for nodeid in entry.test_nodeids)
```

- [ ] **Step 2: Run coverage test and verify RED**

```bash
uv run pytest -q tests/acceptance/test_behavior_matrix.py
```

Expected: matrix/parser does not exist.

- [ ] **Step 3: Implement machine-readable Markdown evidence**

Use one Markdown table row per behavior with columns:

```text
Area | Implemented contract | Source owner | Direct tests | Deliberate difference
```

`load_behavior_matrix` parses only that table, rejects duplicate/missing areas,
and checks paths/node IDs. Link interfaces to unit tests, semantics to contract/
integration tests, and failure properties to concurrency/crash tests. Do not
use README claims or a broad test command as substitute evidence.

- [ ] **Step 4: Run matrix validation**

```bash
uv run pytest -q tests/acceptance/test_behavior_matrix.py
uv run ruff check src tests
uv run pyright src
```

Expected: all entries resolve and pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/acceptance.py BEHAVIOR_MATRIX.md \
  tests/acceptance/test_behavior_matrix.py
git commit -m "docs: map MiniPostgres behavior to direct evidence"
```

### Task 11: End-to-end final acceptance

**Files:**
- Create: `tests/acceptance/test_final_acceptance.py`
- Create: `examples/demo.py`
- Modify: `README.md`
- Modify: `SCOPE.md`
- Modify: `ARCHITECTURE.md`
- Modify: `BEHAVIORAL_CONTRACT.md`
- Modify: `DIFFERENCES_FROM_POSTGRESQL.md`

- [ ] **Step 1: Write failing final lifecycle test**

```python
def test_final_acceptance_crosses_query_restart_crash_and_maintenance(
    tmp_path: Path,
) -> None:
    create_load_analyze_query_update_and_checkpoint(tmp_path)
    assert clean_restart_queries(tmp_path) == expected_rows
    crash_after_durable_commit_before_response(tmp_path)
    with Database.open(tmp_path) as recovered:
        assert_committed_history_visible(recovered)
        assert_index_and_seqscan_parity(recovered)
        assert_read_committed_and_repeatable_read(recovered)
        assert_write_unique_and_deadlock_behavior(recovered)
        create_bloat_and_hot_chain(recovered)
        report = recovered.execute("VACUUM users").maintenance
        assert report.dead_versions_removed > 0
        assert report.hot_versions_pruned > 0
        recovered.checkpoint()
    assert_no_owned_frames_locks_transactions_or_temp_files(tmp_path)
```

- [ ] **Step 2: Run final test and verify RED**

```bash
uv run pytest -q tests/acceptance/test_final_acceptance.py
```

Expected: at least one final contract/helper/document is incomplete.

- [ ] **Step 3: Finish public documentation and executable demo**

README leads with project identity, direct API, mechanism list, install/demo,
verification, and non-compatibility. SCOPE freezes SQL/types/exclusions.
ARCHITECTURE owns boundaries/data flow. BEHAVIORAL_CONTRACT owns exact
semantics/invariants. DIFFERENCES owns every deliberate PostgreSQL divergence.
`examples/demo.py` creates a temporary database and visibly exercises DDL,
DML, join/aggregate, index/EXPLAIN, transaction, restart, and Vacuum without
external services.

- [ ] **Step 4: Run final project verification**

```bash
uv sync
uv run ruff check .
uv run pyright src
uv run pytest -q
uv run python examples/demo.py
git diff --check
git status --short --branch
```

Expected: static checks and all default tests pass, demo exits zero with the
documented output, diff check is silent, and only intended final changes exist.

- [ ] **Step 5: Commit final reference-project acceptance**

```bash
git add README.md SCOPE.md ARCHITECTURE.md BEHAVIORAL_CONTRACT.md \
  DIFFERENCES_FROM_POSTGRESQL.md examples tests/acceptance
git commit -m "docs: accept the MiniPostgres reference project"
```

### Task 12: Completion audit and clean shutdown evidence

**Files:**
- Modify: `tests/acceptance/test_final_acceptance.py`
- Modify: `BEHAVIOR_MATRIX.md`
- Modify: `README.md`

- [ ] **Step 1: Audit every explicit specification requirement**

Create a local audit table from all numbered requirements in:

```text
docs/superpowers/specs/2026-07-27-minipostgres-reference-project-design.md
docs/superpowers/plans/2026-07-27-phase-a-query-loop.md
docs/superpowers/plans/2026-07-27-phase-b-persistent-storage.md
docs/superpowers/plans/2026-07-27-phase-c-optimizer.md
docs/superpowers/plans/2026-07-27-phase-d-transactions-recovery.md
docs/superpowers/plans/2026-07-27-phase-e-vacuum-hot-acceptance.md
```

For each item record direct source, exact test node ID, and latest command
evidence. Treat missing, indirect, or merely plausible evidence as incomplete
and add/fix implementation tests before proceeding.

- [ ] **Step 2: Verify clean lifecycle ownership**

Run:

```bash
uv run pytest -q \
  tests/acceptance/test_final_acceptance.py \
  tests/acceptance/test_behavior_matrix.py \
  tests/crash
```

Expected: pass with no thread warnings, leaked locks/pins/transactions, open
temporary files, or unhandled background exceptions.

- [ ] **Step 3: Re-run static and full dynamic evidence fresh**

Run:

```bash
uv run ruff check .
uv run pyright src
uv run pytest -q
git diff --check
```

Expected: all commands pass from the current HEAD.

- [ ] **Step 4: Confirm clean repository**

Run:

```bash
git status --short --branch
git log -12 --oneline
```

Expected: `## main` with no worktree entries and a traceable sequence of
mechanism/acceptance commits.

- [ ] **Step 5: Record final verified acceptance commit**

If audit fixes changed evidence/docs:

```bash
git add BEHAVIOR_MATRIX.md README.md tests/acceptance
git commit -m "docs: verify final MiniPostgres acceptance"
```

If no files changed, retain the existing final acceptance commit and report
the fresh commands without creating an empty commit.

## Plan self-review

- Vacuum classification is conservative and snapshot-aware.
- Maintenance removes index entries before making any slot reusable.
- Compaction never renumbers live slots and files do not claim to shrink.
- Vacuum changes use the same WAL-before-data and recovery path as DML.
- HOT eligibility requires unchanged indexed columns and same-page capacity.
- One index root TID survives HOT chains; all fetched versions remain
  heap/snapshot checked.
- HOT chain traversal detects corruption and cannot loop indefinitely.
- Pruning retains redirect roots while indexes reference them.
- PostgreSQL differential tests are explicit-profile evidence, not default
  fake success.
- The behavior matrix requires exact source and test node IDs.
- Final acceptance crosses query, clean restart, crash recovery, concurrency,
  Vacuum, HOT, and owner shutdown in one lifecycle.
- Completion is audited against every specification, not inferred from a green
  smoke test.
- No task creates course chapters, wire protocol, replication, SSI, TOAST, or
  production autovacuum.

