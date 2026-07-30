# 8. Isolation Levels, Write Conflicts, and EPQ Rechecks

MVCC gives the executor several physical versions of a logical row. Isolation
defines which committed history a transaction may treat as its database.
MiniPostgres implements two useful policies: Read Committed (RC) refreshes its
snapshot for every statement, while Repeatable Read (RR) pins the first data
snapshot. That difference sounds small, but it determines read phenomena,
concurrent-update behavior, and whether a waiting writer rechecks a predicate
or raises a serialization conflict.

## Learning objectives

After this chapter, you will be able to:

- derive an RC or RR snapshot from `xmax` and the active-XID set;
- apply creator/deleter visibility rules to an `xmin`/`xmax` tuple version;
- explain why RR must reject a stale write even when it can still read its old
  version;
- trace the RC writer path from tuple-lock wait to EPQ-style predicate
  re-evaluation;
- state exactly which PostgreSQL isolation guarantees MiniPostgres does and
  does not preserve.

## A snapshot is a visibility boundary, not a copy of rows

`src/minipostgres/transaction/snapshot.py`, `Snapshot`, stores two facts:
`xmax`, the next XID at snapshot creation, and `active_xids`, the other
transactions then in progress. It does not clone heap pages or rows. A tuple
version can be tested against this compact boundary later.

`src/minipostgres/transaction/manager.py`,
`TransactionManager.statement_snapshot()`, owns snapshot policy. For an RC
transaction it constructs a new `Snapshot` on every statement. For RR it saves
the first one in `Transaction.repeatable_snapshot` and returns that same object
on later statements:

```python
if transaction.isolation is REPEATABLE_READ:
    transaction.repeatable_snapshot = snapshot
```

Suppose the next XID is 20 and transactions 17 and 19 are active. The snapshot
is `(xmax=20, active={17, 19})`. A version created by XID 18 may be visible if
18 committed; a version created by 20 or later is too new; a version created
by 17 is excluded because 17 was still active. The status table is still
needed: numeric position alone cannot tell whether an older creator committed
or aborted.

MiniPostgres assigns XIDs in process and stores transaction outcomes in
`TransactionStatusTable`. A current transaction sees its own insert and hides
its own delete without waiting for a status-table transition. This “read your
writes” rule is essential for useful explicit transactions.

## The visibility decision

`src/minipostgres/transaction/visibility.py`, `is_visible()`, evaluates the
creator first. A version is rejected when its creator did not commit, has an
XID at or beyond snapshot `xmax`, or appears in `active_xids`. System-created
versions are treated as committed. If the creator passes, a zero `xmax` means
no transaction deleted or superseded the version, so it is visible.

For a nonzero tuple `xmax`, the function asks whether the deleting transaction
was visible to the snapshot. A committed deleter that is older than `xmax` and
was not active makes the old version invisible. An aborted, too-new, or
snapshot-active deleter leaves the old version visible.

This is why MVCC is not simply “choose the greatest `xmin`.” Visibility depends
on two transaction outcomes and the snapshot's active set. It is also why
aborted physical versions can remain on disk safely until VACUUM: visibility
rejects them before reclamation.

The source comment correctly points toward PostgreSQL's
`HeapTupleSatisfiesMVCC`, but MiniPostgres uses a much smaller status model.
There are no hint bits, subtransaction ancestry, command IDs, multixacts, or
XID wraparound.

## Read Committed versus Repeatable Read

Consider two sessions. Both read value 10. A third transaction commits value
11. On its next statement, RC gets a new snapshot whose boundary includes the
committed writer and reads 11. RR reuses its earlier snapshot and reads 10.
That is the repository's executable non-repeatable-read distinction.

The implementation does not claim that RC is a transaction-wide snapshot; it
is explicitly statement scoped. Nor does RR mean serial execution. RR keeps a
stable read view, but another transaction may commit changes in parallel.
Stable visibility creates a further rule for writes: an RR transaction cannot
blindly overwrite a version that appeared after its snapshot.

`src/minipostgres/storage/indexed.py`,
`IndexedTableAccess._check_repeatable_read_write_conflict()`, compares the TID
visible under the transaction's saved snapshot with the globally live TID
after acquiring the writer lock. If they differ, it raises
`SerializationConflict("could not serialize access due to concurrent update")`.
The old version remains readable, yet basing a new write on it would lose or
misorder the intervening update. The transaction must roll back and the
application may retry from a new snapshot.

This conflict check belongs after lock acquisition. Before waiting, a candidate
can still be current. While waiting, its owner may commit a successor. The
writer must judge the state it will actually modify, not the state it observed
before blocking.

## Read Committed and EvalPlanQual-style rechecks

RC takes a different path. Its statement found candidate TID `t` because a
predicate was true. It then waits for another writer that owns the logical
row. When the lock is granted, the globally live version may have different
values. Updating it without rechecking could modify a row that no longer
matches the statement.

The planner carries the modification predicate into
`PhysicalModifyTable.recheck_predicate`. The executor's
`UpdateExecutor._predicate_recheck()` or
`DeleteExecutor._predicate_recheck()` in
`src/minipostgres/executor/operators.py` turns that bound expression into a
callable over the latest tuple values. It rebuilds a small `ExecutionRow` and
calls `evaluate()`; only `True` passes.

After the tuple lock is acquired,
`IndexedTableAccess.replace_mvcc()` resolves the globally live version. For RC,
if the recheck callable returns false, it reports `(None, False)`.
`UpdateExecutor._open()` then skips the candidate, so the command tag may be
`UPDATE 0`. `delete_mvcc()` applies the same rule for deletes. The comment
calls this a simplified equivalent of PostgreSQL EvalPlanQual (EPQ).

It is important to describe the positive mechanism precisely: MiniPostgres
re-evaluates the bounded statement predicate on the newest row after a writer
wait. It does not recreate PostgreSQL's full EPQ machinery for joins,
rowmarks, triggers, partitions, and complex plan states.

## Transaction failure and recovery by the caller

`src/minipostgres/engine.py`, `Database.execute_for_session()`, marks an active
explicit transaction failed when binding or execution raises. Subsequent work
calls `Transaction.require_usable()` and is rejected until `ROLLBACK`.
Implicit transactions are aborted immediately by the engine.

On successful commit,
`TransactionManager.commit()` publishes transaction status only after the
durability protocol described in Chapter 10. Both commit and abort remove the
transaction from the active set and release its locks. Therefore future
snapshots see a stable outcome rather than a vanished in-progress XID.

MiniPostgres has no savepoints or subtransactions. An error poisons the whole
explicit transaction, which is directionally similar to PostgreSQL's default
transaction-block behavior but lacks recovery to a savepoint.

## Compared with PostgreSQL 18

PostgreSQL's snapshot acquisition lives primarily in
`src/backend/utils/time/snapmgr.c`; heap visibility decisions live in
`src/backend/access/heap/heapam_visibility.c`. The executor's concurrent update
paths and EPQ machinery are spread across
`src/backend/executor/nodeModifyTable.c`, `execMain.c`, and access-method code.
At PostgreSQL `READ COMMITTED`, each command gets a new snapshot; at
`REPEATABLE READ`, the transaction uses one snapshot and concurrent-update
conflicts can produce SQLSTATE `40001`.

MiniPostgres preserves those teaching contracts but supports neither
PostgreSQL's Serializable Snapshot Isolation nor its predicate locks. It has
only RC and RR, an in-process XID/status table, and typed Python exceptions
rather than SQLSTATE parity. It also rejects self-joins because runtime identity
uses catalog table IDs rather than independent range-table instances.

Use the `mvcc` row of the [behavior matrix](../behavior-matrix.md), the
transaction section of
[Differences from PostgreSQL](../differences.md),
and the [architecture reference](../architecture-reference.md)
to keep equivalent ideas separate from product compatibility.

## Hands-on experiment: watch snapshots diverge

Run from the repository root:

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres import Database
from minipostgres.errors import SerializationConflict
from minipostgres.transaction.model import IsolationLevel

with TemporaryDirectory() as root, Database.open(root) as db:
    db.execute("CREATE TABLE counters (id INT PRIMARY KEY, value INT)")
    db.execute("INSERT INTO counters VALUES (1, 10)")
    rc = db.session()
    rr = db.session(isolation=IsolationLevel.REPEATABLE_READ)
    rc.execute("BEGIN"); rr.execute("BEGIN")
    print("first:", rc.execute("SELECT value FROM counters").rows,
          rr.execute("SELECT value FROM counters").rows)
    db.execute("UPDATE counters SET value = 11 WHERE id = 1")
    print("second:", rc.execute("SELECT value FROM counters").rows,
          rr.execute("SELECT value FROM counters").rows)
    try:
        rr.execute("UPDATE counters SET value = 12 WHERE id = 1")
    except SerializationConflict as error:
        print(type(error).__name__ + ":", error)
    rr.execute("ROLLBACK"); rc.execute("COMMIT")
PY
```

Measured output:

```text
first: ((10,),) ((10,),)
second: ((11,),) ((10,),)
SerializationConflict: could not serialize access due to concurrent update
```

The repository's threaded EPQ regression was also run:

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline pytest -q \
  tests/concurrency/test_write_conflicts.py::test_read_committed_writer_rechecks_predicate_after_lock_wait
```

```text
..                                                                       [100%]
2 passed in 0.74s
```

The node is parametrized for `UPDATE` and `DELETE`, hence two cases.

## Exercises

1. **Understanding.** Given snapshot `(xmax=12, active={9})`, is a version
   `(xmin=8 committed, xmax=9 in progress)` visible to transaction 10?

    Acceptance: apply creator and deleter rules separately.

    ??? note "Reference answer"
        Yes. Creator 8 committed before the snapshot boundary and was not
        active. Deleter 9 was active in the snapshot, so its deletion is not
        visible; the old version remains visible.

2. **Understanding.** Why does RR compare the snapshot-visible TID with the
   globally live TID only after acquiring the tuple lock?

    Acceptance: mention a state transition that can occur during the wait and
    the anomaly prevented.

    ??? note "Reference answer"
        Another owner may commit a successor while this writer waits. Comparing
        after acquisition detects that the RR writer's source is stale and
        prevents a lost update based on an old snapshot.

3. **Hands-on.** In a disposable worktree, add a concurrency test where an RC
   `DELETE ... WHERE value = 10` waits behind a transaction that changes the
   value to 11. Do not modify the tutorial author's `src/` tree.

    Acceptance: use a deterministic queue observation rather than `sleep()` as
    the synchronization assertion; the delete must return `DELETE 0`, and the
    final row must contain value 11. Run the new test three times with
    `pytest --count` if that plugin is available, otherwise loop the exact
    node in the shell.

    ??? note "Reference answer"
        Follow
        `tests/concurrency/test_write_conflicts.py`,
        `test_read_committed_writer_rechecks_predicate_after_lock_wait`.
        Start both transactions, update to 11 in the first, submit the delete
        in a one-worker pool, wait until the second XID appears in
        `waiting_xids()`, then commit the first. The pending result is
        `DELETE 0` because `DeleteExecutor` rechecks `value = 10` against 11.

## Summary

Snapshots are compact visibility boundaries. RC refreshes them per statement
and rechecks a waiting writer's predicate against the newest row; RR pins one
and raises `SerializationConflict` when its write source is no longer globally
current. Both behaviors emerge from the combination of transaction status,
tuple versions, locks, and executor predicate evaluation. The next chapter
opens the lock manager itself: FIFO queues are useful until dependencies form
a cycle, at which point deterministic deadlock resolution is required.
