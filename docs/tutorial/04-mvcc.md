# Chapter 4 — MVCC, Tuple Versions, and Snapshots

Multi-version concurrency control separates physical history from logical
visibility. An UPDATE does not need to destroy the row another transaction is
reading. Instead, MiniPostgres stores creator/deleter transaction IDs and
links versions; each statement evaluates those versions against a snapshot.

## Learning objectives

After this chapter, you can:

1. interpret `xmin`, `xmax`, and `next_tid` in `TupleVersion`;
2. apply `is_visible()` in creator-then-deleter order;
3. explain the `Snapshot(xmax, active_xids)` boundary;
4. distinguish Read Committed snapshot refresh from Repeatable Read pinning;
   and
5. identify what this model omits from PostgreSQL MVCC.

## Physical history

`TupleVersion` in `src/minipostgres/storage/tuple.py` has four fields:

```python
TupleVersion(
    xmin: int,
    xmax: int,
    next_tid: TID | None,
    values: tuple[Scalar, ...],
)
```

`xmin` names the transaction that created the version. `xmax == 0` means no
transaction has deleted or superseded it; otherwise `xmax` names that
transaction. `next_tid` links to a successor version. The values remain with
the physical version so an older snapshot can still read them.

`HeapTable.insert_version()` in `src/minipostgres/storage/heap.py` encodes a
new version with the current transaction's XID, zero `xmax`, and no successor.
`HeapTable.replace_version()` inserts replacement bytes, then rewrites the old
version with `xmax=current_xid` and `next_tid=replacement`. Deletion uses
`delete_version()` to set `xmax` without creating a successor.

These changes are protected by the table lock at this layer and are published
as WAL-backed page images. Writer coordination and post-wait conflict policy
are covered later; this chapter focuses on the version representation and
visibility decision.

## Transaction state and status

`TransactionManager.begin()` in
`src/minipostgres/transaction/manager.py` assigns the next monotonically
increasing XID and records an active `Transaction`. A transaction has an
`IsolationLevel`, state, optional repeatable snapshot, write flag, and owned
resources.

`TransactionStatusTable` in `transaction/status.py` maps XIDs to
`IN_PROGRESS`, `COMMITTED`, or `ABORTED`. Unknown XIDs default to in progress.
Committed and aborted states are terminal. This is an in-process teaching
analogue of PostgreSQL's transaction-status responsibility, not its `pg_xact`
storage format.

The special `SYSTEM_XID` marks versions inserted through the storage reference
path outside ordinary transactional DML. `is_visible()` treats it as committed.
Normal engine queries use transaction-owned versions.

## What a snapshot means

`Snapshot` in `src/minipostgres/transaction/snapshot.py` is immutable:

- `xmax` is the next XID at snapshot creation; any XID greater than or equal
  to it is in the snapshot's future;
- `active_xids` is the set of other transactions that were active; even if
  they commit later, this snapshot remembers that they were not complete.

The validation requires active XIDs to be positive and below `xmax`.
`oldest_active_xid` is the minimum active XID or `xmax` when none exists. A
later VACUUM chapter uses such horizons to avoid reclaiming history still
visible to old snapshots.

`TransactionManager.statement_snapshot()` constructs snapshots. It excludes
the current transaction from `active_xids` because own changes receive special
visibility treatment. Under Read Committed it creates a new object for every
statement. Under Repeatable Read it saves the first snapshot in
`transaction.repeatable_snapshot` and returns that same object thereafter.

Snapshot lifetime, not a different row format, creates the isolation
difference.

## The visibility algorithm

`is_visible()` in `src/minipostgres/transaction/visibility.py` mirrors the
important decision order of `HeapTupleSatisfiesMVCC`: decide whether the
creator is visible, then decide whether a visible deletion hides the tuple.

First, own versions:

```text
if xmin == current_xid:
    visible unless xmax == current_xid
```

This gives a transaction read-your-writes behavior and hides its own deletion.

For another creator, the version is invisible if any condition holds:

1. creator status is not COMMITTED;
2. `xmin >= snapshot.xmax`; or
3. `xmin` appears in `snapshot.active_xids`.

A transaction that commits after the snapshot still fails condition 3. A
transaction allocated after the snapshot fails condition 2.

If the creator is visible and `xmax == 0`, the version is visible. If the
current transaction is the deleter, it is invisible. For another deleter, the
old version remains visible when the deletion is not committed, belongs to the
snapshot's future, or was active at snapshot creation. Only a deletion visible
to this snapshot hides it.

This is a two-sided rule: committed creation is insufficient; deletion
visibility must also be evaluated.

## Resolving a version chain

`HeapTable.resolve_visible()` starts from a TID and follows `next_tid`, checking
cycles and missing targets. It records every version for which `is_visible()`
returns true and finally returns the newest visible pair. A chain may contain
an aborted or future version that the reader skips while retaining an older
visible one.

`scan_visible()` first materializes physical versions and computes all
continuation TIDs. It begins resolution only at chain roots, preventing one
logical row from being emitted once per physical member. This is simple and
observable, though it is not a production traversal design.

`root_tid()` reveals an important simplification. It scans every physical
version to build a predecessor map and walks backward, an O(N) teaching
operation. PostgreSQL HOT metadata and line-pointer states provide much richer
direct navigation. The repository calls this difference out in its
[mapping](../postgresql-mapping.md).

## Statement execution and isolation

`Database.execute_for_session()` asks the manager for a snapshot after binding
and before dispatch. It creates an `ExecutionContext` containing the
transaction, snapshot, status table, and lock manager. Heap access receives
that context when scanning or fetching.

Implicit transactions live for one statement, so each statement naturally has
a fresh snapshot. Explicit sessions are created by
`Database.session(isolation=...)`; `BEGIN`, `COMMIT`, and `ROLLBACK` are parsed
and bound like other statements but handled at the engine coordination layer.

Read Committed permits a later statement in the same transaction to see rows
committed since its previous statement. Repeatable Read fixes its data view at
the first statement snapshot. It does not mean read-only: the transaction can
see its own new versions through the current-XID branch.

## Experiment: one update, two views

Run:

```bash
uv run python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres import Database
from minipostgres.transaction.model import IsolationLevel

with TemporaryDirectory() as root, Database.open(root) as db:
    db.execute("CREATE TABLE counters (id INT PRIMARY KEY, value INT)")
    db.execute("INSERT INTO counters VALUES (1, 10)")
    rc = db.session(isolation=IsolationLevel.READ_COMMITTED)
    rr = db.session(isolation=IsolationLevel.REPEATABLE_READ)
    rc.execute("BEGIN"); rr.execute("BEGIN")
    print("before", rc.execute("SELECT value FROM counters").rows,
          rr.execute("SELECT value FROM counters").rows)
    db.execute("UPDATE counters SET value = 11 WHERE id = 1")
    print("after ", rc.execute("SELECT value FROM counters").rows,
          rr.execute("SELECT value FROM counters").rows)
    rc.execute("ROLLBACK"); rr.execute("ROLLBACK")
PY
```

Observed output:

```text
before ((10,),) ((10,),)
after  ((11,),) ((10,),)
```

Both explicit transactions saw 10 before the default session committed its
UPDATE. The next Read Committed statement received a fresh snapshot and saw
11. Repeatable Read reused its first snapshot and followed the chain to the
older visible version.

Run the focused model tests:

```bash
uv run pytest -q tests/unit/transaction/test_visibility.py \
  tests/concurrency/test_isolation_snapshots.py
```

Observed output:

```text
.......                                                                  [100%]
7 passed in 0.15s
```

These experiments use direct in-process sessions, not sockets, and were
runtime-verified.

## Compared with PostgreSQL

PostgreSQL heap tuples also carry transaction visibility metadata, snapshots
track transaction boundaries, and Read Committed versus Repeatable Read
differs primarily in snapshot lifetime. The nearby owners include
`heapam_visibility.c`, `snapmgr.c`, and transaction status in `pg_xact`.

MiniPostgres omits command IDs, subtransactions, exported snapshots,
Serializable Snapshot Isolation, speculative insertion, XID wraparound,
freezing, hint bits, multixacts, and the production HOT/line-pointer layout.
Its status table is in process, its version chains are explicit TID links, and
its concurrency surface is bounded. See the transactions section of
[Differences](../differences.md), stops 5 and 8 of the
[mapping](../postgresql-mapping.md), and the `mvcc` row in the
[behavior matrix](../behavior-matrix.md).

## Exercises

### 1. Understanding: a late commit

Transaction 8 is active when a snapshot is taken with `xmax=10` and
`active_xids={8}`. It later commits. Is a version with `xmin=8` visible to that
snapshot?

??? note "Reference answer"

    No. Although the status is now COMMITTED and `8 < 10`, XID 8 remains in
    the snapshot's active set. The snapshot preserves what was incomplete at
    creation time.

### 2. Understanding: deletion in the future

A visible version has `xmax=12`, committed status, and the reader's snapshot
has `xmax=11`. Is the old version visible?

??? note "Reference answer"

    Yes. The deleting transaction is in the snapshot's future because
    `12 >= 11`. Its later commit cannot retroactively hide the version from
    this snapshot.

### 3. Hands-on: test read-your-writes

Create one explicit Repeatable Read session, insert a row, select it before
commit, roll back, then prove the default session cannot see it. Do not change
`src/`.

Acceptance:

- the explicit session returns the inserted row before rollback;
- `ROLLBACK` returns its command tag; and
- the default session returns no rows afterward.

??? note "Reference answer"

    Begin the Repeatable Read transaction, execute CREATE TABLE outside it
    (DDL is rejected inside explicit transactions), insert inside it, and
    select. The `xmin == current_xid` branch makes the row visible. After
    rollback, status is ABORTED, so another transaction rejects the creator.

### 4. Hands-on design: visibility truth table

Propose a parameterized unit test covering committed, active, future, and
aborted creators plus committed and active deleters.

Acceptance:

- construct `TupleVersion`, `Snapshot`, and `TransactionStatusTable` directly;
- include own insertion and own deletion; and
- give each case a descriptive pytest ID.

??? note "Reference answer"

    Use rows of `(name, xmin, xmax, current, xmax_boundary, active, statuses,
    expected)` and call `is_visible()` directly. Include IDs such as
    `committed_creator`, `creator_active_at_snapshot`, `future_creator`,
    `aborted_creator`, `active_deleter_keeps_old`, `committed_deleter_hides`,
    `own_insert`, and `own_delete`.

## Summary

MVCC is a visibility calculation over durable physical history.
`TupleVersion` records creator, deleter, and successor; `Snapshot` records the
future boundary and transactions active at capture; `is_visible()` evaluates
creator then deleter. Read Committed refreshes that evidence, while Repeatable
Read retains it. Chapter 5 shows how a B+Tree points into this heap history
without becoming the authority on visibility.
