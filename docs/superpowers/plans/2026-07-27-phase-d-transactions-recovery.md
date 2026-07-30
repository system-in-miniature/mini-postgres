# Phase D Transactions and Recovery Design and Implementation History

**Historical objective:** Add Read Committed and Repeatable Read transactions, PostgreSQL-style tuple-version visibility, conflicting-writer locks, durable commit, sharp checkpoints, and deterministic REDO recovery from injected process crashes.

**Architecture:** Transaction status and snapshots determine logical visibility; tuple and unique-key locks serialize conflicting writers without blocking ordinary reads. Heap mutation emits checksummed full-page post-images to WAL before a dirty page can flush. Durable COMMIT is the success boundary, recovery replays newer/corrupt heap pages and marks incomplete XIDs aborted, then rebuilds indexes from committed heap truth.

**Tech Stack:** Python 3.12, standard library threads/conditions, `struct`, `zlib.crc32`, subprocess crash tests, uv, pytest, Hypothesis, Ruff, Pyright.

---

## File map

```text
src/minipostgres/transaction/model.py       isolation, state, transaction
src/minipostgres/transaction/snapshot.py    immutable snapshot and horizon
src/minipostgres/transaction/status.py      commit/abort state table
src/minipostgres/transaction/visibility.py  tuple visibility truth table
src/minipostgres/transaction/manager.py     XID/snapshot/commit orchestration
src/minipostgres/transaction/locks.py       tuple/key FIFO locks
src/minipostgres/transaction/deadlock.py    wait-for graph and victim
src/minipostgres/wal/records.py             checksummed record codec
src/minipostgres/wal/manager.py             append, flush, scan, tail truncate
src/minipostgres/wal/control_file.py        atomic recovery metadata
src/minipostgres/wal/checkpoint.py          sharp checkpoint
src/minipostgres/wal/recovery.py            REDO and status reconstruction
src/minipostgres/testing/failpoints.py       named subprocess crash gates
tests/unit/transaction/
tests/unit/wal/
tests/concurrency/
tests/crash/
tests/acceptance/test_phase_d.py
```

### Milestone 1: Transaction, isolation, snapshot, and status models

**Recorded file scope:**
- Added: `src/minipostgres/transaction/__init__.py`
- Added: `src/minipostgres/transaction/model.py`
- Added: `src/minipostgres/transaction/snapshot.py`
- Added: `src/minipostgres/transaction/status.py`
- Added: `tests/unit/transaction/test_models.py`
- Added: `tests/unit/transaction/test_status.py`

**Recorded activity 1 — Test intent: failing state-transition tests**

```python
def test_transaction_state_machine_is_one_way() -> None:
    tx = Transaction(xid=7, isolation=IsolationLevel.READ_COMMITTED)
    tx.mark_failed()
    assert tx.state is TransactionState.FAILED
    with pytest.raises(TransactionAborted):
        tx.require_usable()
    tx.mark_aborted()
    with pytest.raises(TransactionAborted):
        tx.mark_committed()


def test_snapshot_horizon_and_status_defaults() -> None:
    snapshot = Snapshot(xmax=20, active_xids=frozenset({11, 14}))
    assert snapshot.oldest_active_xid == 11
    statuses = TransactionStatusTable()
    assert statuses.get(99) is TransactionStatus.IN_PROGRESS
    statuses.set(99, TransactionStatus.COMMITTED)
    assert statuses.get(99) is TransactionStatus.COMMITTED
```

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/unit/transaction/test_models.py`, `tests/unit/transaction/test_status.py`.

Historical expected evidence: imports fail because transaction models do not exist.

**Recorded activity 3 — Design outcome: immutable snapshots and guarded transitions**

Freeze:

```python
class IsolationLevel(Enum): READ_COMMITTED, REPEATABLE_READ
class TransactionState(Enum): ACTIVE, FAILED, COMMITTED, ABORTED
class TransactionStatus(Enum): IN_PROGRESS, COMMITTED, ABORTED
@dataclass(frozen=True, slots=True)
class Snapshot:
    xmax: int
    active_xids: frozenset[int]
```

`Transaction` owns XID, isolation, state, optional repeatable snapshot,
write flag, and acquired resource keys. State methods hold an internal lock and
reject invalid transitions. Status table changes are monotonic except
`IN_PROGRESS → COMMITTED|ABORTED`.

**Recorded activity 4 — Verification intent: model tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/unit/transaction`.

Historical expected evidence: all commands pass.

### Milestone 2: MVCC visibility truth table

**Recorded file scope:**
- Added: `src/minipostgres/transaction/visibility.py`
- Added: `tests/unit/transaction/test_visibility.py`
- Added: `tests/property/test_visibility_model.py`

**Recorded activity 1 — Test intent: failing visibility cases**

```python
@pytest.mark.parametrize(
    ("xmin_status", "xmax", "xmax_status", "visible"),
    [
        (ABORTED, 0, IN_PROGRESS, False),
        (COMMITTED, 0, IN_PROGRESS, True),
        (COMMITTED, 12, ABORTED, True),
        (COMMITTED, 12, COMMITTED, False),
        (COMMITTED, 12, IN_PROGRESS, True),
    ],
)
def test_visibility_status_cases(
    xmin_status, xmax, xmax_status, visible
) -> None:
    statuses = TransactionStatusTable()
    statuses.set(10, xmin_status)
    if xmax:
        statuses.set(xmax, xmax_status)
    candidate = TupleVersion(
        xmin=10,
        xmax=xmax,
        next_tid=None,
        values=(1,),
    )
    snapshot = Snapshot(xmax=20, active_xids=frozenset())
    assert is_visible(candidate, snapshot, current_xid=7, statuses=statuses) is visible


def test_current_transaction_sees_own_insert_and_hides_own_delete() -> None:
    assert is_visible(version(xmin=7, xmax=0), snapshot, 7, statuses)
    assert not is_visible(version(xmin=7, xmax=7), snapshot, 7, statuses)
```

Property tests compare implementation against an explicit branch-by-branch
reference function over generated XIDs/statuses/snapshots.

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/unit/transaction/test_visibility.py`, `tests/property/test_visibility_model.py`.

Historical expected evidence: visibility function does not exist.

**Recorded activity 3 — Design outcome: creator/deleter visibility**

Rules:

1. current XID sees its own created version unless it also deleted it;
2. aborted creators and creators active/new at snapshot are invisible;
3. committed creators older than snapshot are candidates;
4. `xmax=0`, aborted deleter, active deleter, or deleter new at snapshot leaves
   the version visible;
5. current or committed old deleter hides it.

System XID is always committed and older than user snapshots. Visibility is a
pure function and never mutates hint bits.

**Recorded activity 4 — Verification intent: visibility tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/unit/transaction/test_visibility.py`, `tests/property/test_visibility_model.py`.

Historical expected evidence: all commands pass.

### Milestone 3: Transaction manager and statement snapshots

**Recorded file scope:**
- Added: `src/minipostgres/transaction/manager.py`
- Changed: `src/minipostgres/engine.py`
- Added: `tests/unit/transaction/test_manager.py`
- Added: `tests/concurrency/test_isolation_snapshots.py`
- Added: `tests/contract/test_transaction_commands.py`

**Recorded activity 1 — Test intent: failing isolation/API tests**

```python
def test_read_committed_gets_new_snapshot_per_statement(manager) -> None:
    reader = manager.begin(IsolationLevel.READ_COMMITTED)
    first = manager.statement_snapshot(reader)
    writer = manager.begin(IsolationLevel.READ_COMMITTED)
    manager.commit(writer)
    second = manager.statement_snapshot(reader)
    assert writer.xid in first.active_xids
    assert writer.xid not in second.active_xids


def test_repeatable_read_reuses_first_data_snapshot(manager) -> None:
    reader = manager.begin(IsolationLevel.REPEATABLE_READ)
    first = manager.statement_snapshot(reader)
    commit_other_transaction(manager)
    assert manager.statement_snapshot(reader) is first


def test_failed_explicit_transaction_accepts_only_rollback(engine) -> None:
    engine.execute("BEGIN")
    with pytest.raises(MiniPostgresError):
        engine.execute("SELECT missing FROM users")
    with pytest.raises(TransactionAborted):
        engine.execute("SELECT 1")
    assert engine.execute("ROLLBACK").command_tag == "ROLLBACK"
```

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/unit/transaction/test_manager.py`, `tests/concurrency/test_isolation_snapshots.py`, `tests/contract/test_transaction_commands.py`.

Historical expected evidence: transaction commands are bound but not orchestrated.

**Recorded activity 3 — Design outcome: XID and transaction ownership**

Manager allocates monotonically increasing XIDs under a lock, registers active
transactions, creates snapshots from `next_xid` and active XIDs, and removes
terminal transactions. Engine holds one explicit transaction per client
`DatabaseSession`; `Database.execute` uses a default session. Statements
outside BEGIN use implicit transactions and commit/abort automatically.

DDL rejects execution inside explicit transactions. Read Committed refreshes
per statement. Repeatable Read caches the first data snapshot. A statement
error marks an explicit transaction failed; implicit transactions abort.

**Recorded activity 4 — Verification intent: manager/API tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/unit/transaction/test_manager.py`, `tests/concurrency/test_isolation_snapshots.py`, `tests/contract/test_transaction_commands.py`.

Historical expected evidence: all commands pass.

### Milestone 4: MVCC heap scan/insert/update/delete

**Recorded file scope:**
- Changed: `src/minipostgres/storage/heap.py`
- Changed: `src/minipostgres/executor/base.py`
- Changed: `src/minipostgres/executor/operators.py`
- Added: `tests/integration/test_mvcc_heap.py`
- Added: `tests/concurrency/test_read_phenomena.py`

**Recorded activity 1 — Test intent: failing tuple-version behavior tests**

```python
def test_update_creates_new_version_and_keeps_old_snapshot(engine) -> None:
    seed_user(engine, age=20)
    reader = engine.session()
    reader.execute("BEGIN ISOLATION LEVEL REPEATABLE READ")
    assert reader.execute("SELECT age FROM users").rows == ((20,),)
    engine.execute("UPDATE users SET age = 21")
    assert reader.execute("SELECT age FROM users").rows == ((20,),)
    assert engine.execute("SELECT age FROM users").rows == ((21,),)


def test_aborted_insert_and_delete_have_visibility_not_physical_undo(engine) -> None:
    writer = engine.session()
    writer.execute("BEGIN")
    writer.execute("INSERT INTO users VALUES (9, 'temp')")
    writer.execute("ROLLBACK")
    assert engine.execute("SELECT * FROM users WHERE id = 9").rows == ()
    assert physical_versions_for_id(engine, 9)[0].xmin_status is ABORTED
```

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/integration/test_mvcc_heap.py`, `tests/concurrency/test_read_phenomena.py`.

Historical expected evidence: Phase B physically replaces/deletes rows.

**Recorded activity 3 — Thread transaction context through heap access**

The recorded change extended `TableAccess` with transaction/snapshot arguments. Insert encodes
`xmin=current_xid`. Delete writes `xmax=current_xid` to the old slot. Update
marks old `xmax` then inserts a new version, sets old `next_tid`, and returns
new TID. Scan/fetch iterate physical candidates then call `is_visible`.

Index maintenance adds the new version's TID and retains the old candidate.
IndexScan heap-rechecks visibility. Transaction rollback changes only status;
physical garbage remains.

**Recorded activity 4 — Verification intent: MVCC heap tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/integration/test_mvcc_heap.py`, `tests/concurrency/test_read_phenomena.py`.

Historical expected evidence: all commands pass.

### Milestone 5: FIFO tuple and unique-key locks

**Recorded file scope:**
- Added: `src/minipostgres/transaction/locks.py`
- Added: `tests/unit/transaction/test_locks.py`
- Added: `tests/concurrency/test_write_conflicts.py`
- Added: `tests/concurrency/test_unique_conflicts.py`

**Recorded activity 1 — Test intent: failing lock ordering/conflict tests**

```python
def test_lock_waiters_acquire_in_fifo_order(lock_manager) -> None:
    resource = TupleLockKey(table_id=1, tid=TID(0, 1))
    lock_manager.acquire(tx1, resource)
    start_waiter(tx2, resource)
    start_waiter(tx3, resource)
    lock_manager.release_all(tx1)
    assert acquired_order.take() == tx2.xid
    lock_manager.release_all(tx2)
    assert acquired_order.take() == tx3.xid


def test_unique_key_lock_allows_only_one_committed_insert(engine) -> None:
    first, second = concurrent_sessions()
    first.execute("BEGIN")
    second.execute("BEGIN")
    first.execute("INSERT INTO users VALUES (7, 'first')")
    pending = run_async(second.execute, "INSERT INTO users VALUES (7, 'second')")
    first.execute("COMMIT")
    with pytest.raises(ConstraintViolation):
        pending.result()
```

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/unit/transaction/test_locks.py`, `tests/concurrency/test_write_conflicts.py`, `tests/concurrency/test_unique_conflicts.py`.

Historical expected evidence: writers are only statement-serialized or race.

**Recorded activity 3 — Design outcome: per-resource FIFO queues**

Resources are:

```python
TupleLockKey(table_id, root_tid)
UniqueKeyLockKey(index_id, encoded_key)
```

One XID owns a resource reentrantly. Waiters enqueue once and wait on a
condition until they are queue head and resource is free. Aborted waiters are
removed. `release_all` releases every resource recorded by the transaction
and notifies waiters.

The recorded change updated/delete lock the root version TID before visibility recheck. Unique
insert/update locks the encoded key before scanning candidate heap versions;
the check treats another in-progress version as conflicting and a committed
visible version as a constraint violation.

**Recorded activity 4 — Verification intent: lock/conflict tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/unit/transaction/test_locks.py`, `tests/concurrency/test_write_conflicts.py`, `tests/concurrency/test_unique_conflicts.py`.

Historical expected evidence: all commands pass.

### Milestone 6: Wait-for graph deadlock detection

**Recorded file scope:**
- Added: `src/minipostgres/transaction/deadlock.py`
- Changed: `src/minipostgres/transaction/locks.py`
- Added: `tests/unit/transaction/test_deadlock_graph.py`
- Added: `tests/concurrency/test_deadlock.py`

**Recorded activity 1 — Test intent: failing cycle/victim tests**

```python
def test_detector_returns_highest_xid_in_cycle() -> None:
    graph = WaitForGraph({7: {9}, 9: {12}, 12: {7}})
    assert graph.deadlock_victim() == 12


def test_two_row_deadlock_aborts_deterministic_victim(engine) -> None:
    low, high = begin_sessions_in_xid_order(engine)
    low.execute("UPDATE accounts SET n = n + 1 WHERE id = 1")
    high.execute("UPDATE accounts SET n = n + 1 WHERE id = 2")
    low_wait = run_async(
        low.execute, "UPDATE accounts SET n = n + 1 WHERE id = 2"
    )
    with pytest.raises(DeadlockDetected):
        high.execute("UPDATE accounts SET n = n + 1 WHERE id = 1")
    high.execute("ROLLBACK")
    assert low_wait.result().command_tag == "UPDATE 1"
```

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/unit/transaction/test_deadlock_graph.py`, `tests/concurrency/test_deadlock.py`.

Historical expected evidence: both waiters block because no cycle detector selects a victim.

**Recorded activity 3 — Detect on wait-edge insertion**

Build wait edges from each waiter to the current owner and earlier FIFO waiters
for that resource. On every new wait, run deterministic DFS over sorted XIDs.
If a cycle exists, choose its highest XID, mark that transaction failed with
`DeadlockDetected`, remove its waiters, release its owned locks, and notify all
affected queues. Detector work is synchronous; no background thread exists.

**Recorded activity 4 — Verification intent: deadlock tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/unit/transaction/test_deadlock_graph.py`, `tests/concurrency/test_deadlock.py`.

Historical expected evidence: all commands terminate and pass.

### Milestone 7: WAL records, append, flush, and tail recovery

**Recorded file scope:**
- Added: `src/minipostgres/wal/__init__.py`
- Added: `src/minipostgres/wal/records.py`
- Added: `src/minipostgres/wal/manager.py`
- Added: `tests/unit/wal/test_record_codec.py`
- Added: `tests/unit/wal/test_manager.py`
- Added: `tests/property/test_wal_codec.py`

**Recorded activity 1 — Test intent: failing codec/durability tests**

```python
def test_wal_record_round_trip_and_lsn_is_byte_position() -> None:
    record = HeapPageImages(xid=7, pages=((heap_key, page_bytes),))
    encoded = encode_record(lsn=128, record=record)
    decoded, next_lsn = decode_record(encoded, expected_lsn=128)
    assert decoded == record
    assert next_lsn == 128 + len(encoded)


def test_manager_truncates_incomplete_tail_but_rejects_middle_corruption(tmp_path) -> None:
    wal = WalManager.open(tmp_path)
    first = wal.append(BeginRecord(xid=7))
    wal.flush(first.end_lsn)
    append_partial_bytes(wal.path)
    assert list(WalManager.open(tmp_path).scan()) == [first]
    corrupt_first_record(wal.path)
    with pytest.raises(CorruptWal):
        list(WalManager.open(tmp_path).scan())
```

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/unit/wal`, `tests/property/test_wal_codec.py`.

Historical expected evidence: WAL modules do not exist.

**Recorded activity 3 — Design outcome: checksummed length-delimited WAL**

Header:

```text
magic, version, total_length, type, lsn, xid, payload_length, checksum
```

Types are BEGIN, HEAP_PAGE_IMAGES, COMMIT, ABORT, CHECKPOINT. Page-image
payload contains count and repeated serialized `PageKey + 8192 bytes`.
`append` holds one lock, assigns current file-end LSN, writes the complete
record, and advances append position. `flush(lsn)` calls `fsync` only when
needed and advances a monotonic durable LSN.

Startup scans from zero. An incomplete final header/body or checksum-failing
final record is truncated to the last verified boundary. Structural/checksum
failure before the physical tail raises `CorruptWal`.

**Recorded activity 4 — Verification intent: WAL codec/manager tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/unit/wal`, `tests/property/test_wal_codec.py`.

Historical expected evidence: all commands pass.

### Milestone 8: Heap mutation logging and WAL-before-data gate

**Recorded file scope:**
- Changed: `src/minipostgres/storage/buffer.py`
- Changed: `src/minipostgres/storage/heap.py`
- Changed: `src/minipostgres/transaction/manager.py`
- Added: `tests/reliability/test_wal_before_data.py`
- Added: `tests/reliability/test_page_lsn.py`

**Recorded activity 1 — Test intent: failing ordering tests**

```python
def test_heap_change_logs_post_image_before_dirty_visibility(recording_stack) -> None:
    heap = recording_stack.heap
    heap.insert(tx, snapshot, (1, "A"))
    assert recording_stack.events[:2] == [
        ("wal_append", "HEAP_PAGE_IMAGES"),
        ("mark_dirty", recording_stack.last_record_lsn),
    ]


def test_dirty_flush_forces_wal_through_page_lsn(recording_stack) -> None:
    dirty_page_at_lsn(recording_stack.pool, lsn=91)
    recording_stack.pool.flush_all()
    assert recording_stack.events.index(("wal_flush", 91)) < (
        recording_stack.events.index(("page_write", heap_key))
    )
```

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/reliability/test_wal_before_data.py`, `tests/reliability/test_page_lsn.py`.

Historical expected evidence: Phase B buffer gate accepts only zero and heap emits no WAL.

**Recorded activity 3 — Log complete post-images under mutation latch**

Before changing a page, capture/modify a private page image under its guard,
set its proposed `page_lsn` to the record start LSN, append one
HEAP_PAGE_IMAGES record containing every page affected by that logical
operation, then install image bytes in frames and mark them dirty at that LSN.

For an operation that allocates a page, allocation happens first but the empty
page is not dirty-flushable until its first page-image record exists. Buffer
flush calls `WalManager.flush(page_lsn)` before disk write. BEGIN is appended
once, immediately before a transaction's first page-image record.

**Recorded activity 4 — Verification intent: ordering tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/reliability/test_wal_before_data.py`, `tests/reliability/test_page_lsn.py`.

Historical expected evidence: all commands pass.

### Milestone 9: Durable commit and logical abort

**Recorded file scope:**
- Changed: `src/minipostgres/transaction/manager.py`
- Changed: `src/minipostgres/engine.py`
- Added: `tests/reliability/test_commit_protocol.py`
- Added: `tests/reliability/test_abort_protocol.py`

**Recorded activity 1 — Test intent: failing success-boundary tests**

```python
def test_commit_flushes_record_before_response_and_status(recording_engine) -> None:
    result = recording_engine.execute("INSERT INTO users VALUES (1, 'A')")
    assert result.command_tag == "INSERT 0 1"
    events = recording_engine.events
    assert events.index(("wal_append", "COMMIT")) < events.index(("wal_flush",))
    assert events.index(("wal_flush",)) < events.index(("status", "COMMITTED"))
    assert events.index(("status", "COMMITTED")) < events.index(("response",))


def test_abort_marks_versions_invisible_without_page_undo(engine) -> None:
    tx = engine.session()
    tx.execute("BEGIN")
    tx.execute("INSERT INTO users VALUES (5, 'aborted')")
    tx.execute("ROLLBACK")
    assert physical_tuple_exists(engine, 5)
    assert engine.execute("SELECT * FROM users WHERE id = 5").rows == ()
```

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/reliability/test_commit_protocol.py`, `tests/reliability/test_abort_protocol.py`.

Historical expected evidence: statuses/locks/responses are not ordered by durable WAL.

**Recorded activity 3 — Design outcome: finalization protocol**

Historical test and implementation coverage included transaction:

```text
append COMMIT
→ flush through COMMIT end
→ publish COMMITTED
→ release locks
→ remove active transaction
→ return
```

Read-only transactions publish committed without WAL. Written abort appends and
flushes ABORT, publishes ABORTED, releases locks, and returns; if WAL append or
flush fails, fail closed and do not report success. Deadlock and statement
errors route through the same abort owner exactly once.

**Recorded activity 4 — Verification intent: protocol tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/reliability/test_commit_protocol.py`, `tests/reliability/test_abort_protocol.py`.

Historical expected evidence: all commands pass.

### Milestone 10: Control file and sharp checkpoint

**Recorded file scope:**
- Added: `src/minipostgres/wal/control_file.py`
- Added: `src/minipostgres/wal/checkpoint.py`
- Added: `tests/unit/wal/test_control_file.py`
- Added: `tests/reliability/test_checkpoint.py`

**Recorded activity 1 — Test intent: failing atomic-checkpoint tests**

```python
def test_control_file_is_checksummed_and_atomically_replaced(tmp_path: Path) -> None:
    control = ControlFileStore(tmp_path)
    state = ControlState(
        checkpoint_lsn=100,
        next_xid=22,
        statuses=((1, COMMITTED), (7, ABORTED)),
        clean_shutdown=False,
    )
    control.replace(state)
    assert control.load() == state
    assert not control.temporary_path.exists()


def test_sharp_checkpoint_orders_flush_and_publication(recording_engine) -> None:
    recording_engine.checkpoint()
    assert recording_engine.events == [
        ("wal_flush", "append_position"),
        ("buffer_flush_all",),
        ("wal_append", "CHECKPOINT"),
        ("wal_flush", "checkpoint_end"),
        ("control_replace", "checkpoint"),
    ]
```

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/unit/wal/test_control_file.py`, `tests/reliability/test_checkpoint.py`.

Historical expected evidence: checkpoint/control components do not exist.

**Recorded activity 3 — Design outcome: atomic recovery metadata and sharp barrier**

Control file is fixed-header checksummed JSON payload containing format
version, checkpoint LSN, next XID, sorted non-in-progress status pairs, and
clean-shutdown flag. Replace with temp/fsync/rename/parent-fsync.

Checkpoint takes the engine checkpoint latch, flushes WAL to append position,
flushes all dirty pages through their WAL gates, snapshots statuses/next XID,
appends and flushes CHECKPOINT, then publishes control state pointing to that
record. Mainline retains all WAL.

**Recorded activity 4 — Verification intent: checkpoint tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/unit/wal/test_control_file.py`, `tests/reliability/test_checkpoint.py`.

Historical expected evidence: all commands pass.

### Milestone 11: REDO recovery and index rebuild

**Recorded file scope:**
- Added: `src/minipostgres/wal/recovery.py`
- Changed: `src/minipostgres/engine.py`
- Added: `tests/reliability/test_recovery.py`
- Added: `tests/reliability/test_index_rebuild.py`
- Added: `tests/property/test_recovery_history.py`

**Recorded activity 1 — Test intent: failing REDO/idempotence tests**

```python
def test_recovery_repairs_older_and_torn_pages_from_post_image(crashed_db) -> None:
    corrupt_committed_heap_page(crashed_db)
    report = recover(crashed_db.path)
    assert report.redone_pages >= 1
    assert reopen(crashed_db).execute("SELECT * FROM users").rows == committed_rows


def test_recovery_marks_begin_without_durable_commit_aborted(crashed_db) -> None:
    crash_after_page_flush_before_commit(crashed_db)
    db = reopen(crashed_db)
    assert db.execute("SELECT * FROM users WHERE id = 99").rows == ()
    assert db.transaction_status(unfinished_xid) is ABORTED


@given(durable_history_with_crash_point())
def test_recovered_rows_equal_durable_commit_model(history) -> None:
    recovered = execute_crash_and_recover(history)
    assert visible_rows(recovered) == history.durable_committed_rows
```

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/reliability/test_recovery.py`, `tests/reliability/test_index_rebuild.py`, `tests/property/test_recovery_history.py`.

Historical expected evidence: database opens pages directly without WAL replay.

**Recorded activity 3 — Design outcome: idempotent startup recovery**

Load verified control state, then scan WAL from checkpoint LSN. For each page
image, decode current disk page; write the image if the page is missing,
corrupt, or has lower page LSN. Record BEGIN/COMMIT/ABORT statuses in scan
order. After scan, mark every begun nonterminal XID aborted and set next XID
above control/WAL maxima.

If prior shutdown is unclean, discard every published B+Tree relation, rebuild
from all versions whose creator is committed and whose deleter does not make
them globally dead, fsync indexes, then atomically publish a running
`clean_shutdown=False` control state. Recovery is repeatable and yields no
additional changes on a second run.

**Recorded activity 4 — Verification intent: recovery tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/reliability/test_recovery.py`, `tests/reliability/test_index_rebuild.py`, `tests/property/test_recovery_history.py`.

Historical expected evidence: all commands pass.

### Milestone 12: Subprocess crash matrix and Phase D acceptance

**Recorded file scope:**
- Added: `src/minipostgres/testing/__init__.py`
- Added: `src/minipostgres/testing/failpoints.py`
- Added: `tests/crash/worker.py`
- Added: `tests/crash/test_commit_matrix.py`
- Added: `tests/crash/test_checkpoint_matrix.py`
- Added: `tests/acceptance/test_phase_d.py`
- Changed: `README.md`
- Changed: `ARCHITECTURE.md`
- Changed: `BEHAVIORAL_CONTRACT.md`
- Changed: `DIFFERENCES_FROM_POSTGRESQL.md`

**Recorded activity 1 — Test intent: failing named-failpoint matrix**

```python
@pytest.mark.parametrize(
    "failpoint",
    [
        "before_wal_append",
        "after_wal_append_before_flush",
        "after_wal_flush_before_page_write",
        "during_page_write",
        "after_page_write_before_commit",
        "after_commit_append_before_flush",
        "after_commit_flush_before_response",
    ],
)
def test_commit_crash_matrix(tmp_path: Path, failpoint: str) -> None:
    outcome = run_crash_worker(tmp_path, failpoint)
    recovered = Database.open(tmp_path)
    if outcome.commit_response_observed:
        assert recovered.execute("SELECT value FROM durable").rows == (("new",),)
    if not outcome.durable_commit_record:
        assert recovered.execute("SELECT value FROM durable").rows != (("new",),)
```

Checkpoint cases terminate after temporary write, before replace, and after
replace. Acceptance also runs Read Committed/Repeatable Read, write conflict,
unique conflict, deadlock, no-force commit, torn-page repair, and index rebuild.

**Recorded activity 2 — Verification intent: crash/acceptance tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/crash`, `tests/acceptance/test_phase_d.py`.

Historical expected evidence: failpoint worker or one or more recovery boundaries are absent.

**Recorded activity 3 — Design outcome: process failpoints and document reliability**

Failpoints are inert unless `MINIPOSTGRES_FAILPOINT` names exactly one accepted
gate. A hit writes an observation marker with `os.write`/`fsync`, then calls
`os._exit(86)` without cleanup. Tests run one fresh subprocess per gate and use
only marker/WAL/disk evidence, never child memory claims.

Historical documentation covered snapshot rules, tuple/key locks, deadlock victim, full-page-image WAL,
durable commit, no-force pages, checkpoint order, REDO, aborted-on-recovery,
index rebuild, unbounded WAL, and differences from PostgreSQL/ARIES.

**Recorded activity 4 — Verification intent: full Phase D verification**

Historical verification covered targeted or full test coverage, static analysis, diff hygiene.

Historical expected evidence: all static checks, concurrency tests, subprocess crash cases, and
acceptance tests pass.

**Recorded activity 5 — Recorded Phase D acceptance**

## Plan self-review

- Snapshot/status visibility is pure and tested independently from storage.
- Read Committed and Repeatable Read own different snapshot lifetimes.
- MVCC does not pretend to solve write-write or unique-key conflicts.
- Locks and process-local latches have separate types and owners.
- Deadlock detection cannot leave a selected victim's locks or waiters behind.
- BEGIN precedes first heap image; COMMIT durability precedes status/success.
- Dirty heap pages cannot pass WAL flush position.
- Full page images make torn-page REDO exact without claiming ARIES.
- Non-durable transactions need no physical UNDO because status makes their
  versions invisible.
- Unclean startup rebuilds derived indexes before serving queries.
- Crash acceptance uses subprocess evidence and every named boundary.
- No task adds replication, SSI, wire protocol, or course material.
