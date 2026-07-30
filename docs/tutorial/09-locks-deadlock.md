# 9. Locks and Deterministic Deadlock Detection

MVCC allows readers and writers to overlap, but it does not make conflicting
writes safe by itself. MiniPostgres serializes writers with exclusive,
reentrant locks on logical tuple roots and encoded unique keys. Waiters line up
FIFO. From those queues the lock manager derives a wait-for graph; if a cycle
appears, it chooses the highest XID as a deterministic victim. This chapter
connects resource identity, queue fairness, uniqueness, cycle detection, and
transaction cleanup.

## Learning objectives

By the end, you will be able to:

- distinguish tuple-root locks from unique-key locks and explain why both are
  needed;
- derive wait-for graph edges from an owner and a FIFO queue;
- trace a two-row deadlock to the deterministic highest-XID victim;
- explain how victim abort releases resources and wakes survivors;
- contrast MiniPostgres's process-local exclusive locks with PostgreSQL's lock
  modes and deadlock policy.

## Two resource identities

`src/minipostgres/transaction/locks.py` defines immutable
`TupleLockKey(table_id, tid)` and `UniqueKeyLockKey(index_id, encoded_key)`.
They solve different races.

A tuple lock serializes update or delete of one logical row. The TID used is
the root of its version chain, not whichever successor happened to be visible.
`src/minipostgres/storage/indexed.py`, `replace_mvcc()` and `delete_mvcc()`,
call `HeapTable.root_tid()` before `LockManager.acquire()`. If each version had
an independent lock, two writers could lock different versions of the same
logical row and both proceed.

A unique-key lock serializes the *absence or ownership* of a key. Two
transactions can try to insert the same new key when no heap tuple yet exists,
so there is no shared tuple TID to lock. `_acquire_unique_keys()` locks the
encoded key before `_check_unique_global()` resolves committed, in-progress,
and aborted candidate versions. When the first transaction finishes, the
second rechecks global uniqueness and either proceeds after an abort or raises
`ConstraintViolation` after a commit.

These locks are exclusive only. There are no shared reader row locks,
table-level modes, intention locks, predicate locks, or lock escalation.
Ordinary snapshot reads do not acquire them.

## FIFO acquisition and reentrancy

`LockManager.acquire()` uses a `threading.Condition` around all owner and queue
state. `_owners` maps one resource to an XID; `_queues` maps it to a
`deque` of waiting XIDs. If a transaction already owns the resource,
acquisition is reentrant and immediately records it in the transaction's
resource set.

Otherwise the XID is appended once. It may acquire only when the resource has
no owner *and* it is at the queue head:

```python
while owner is not None or queue[0] != transaction.xid:
    ...
    condition.wait()
```

The head condition matters. Without it, a newly scheduled waiter could race
past an older awakened waiter after release. FIFO is a local fairness contract,
not a guarantee of bounded transaction completion: a transaction can hold one
resource indefinitely, and a chain of dependencies can still block many
waiters.

`LockManager.release_all()` removes owned resources and queued requests, drops
the transaction from diagnostic state, and calls `notify_all()`. Every waiter
then rechecks the loop condition. Release is tied to
`TransactionManager.commit()` and `TransactionManager.abort()`, so locks do not
survive a transaction outcome.

## Building the wait-for graph from queues

A deadlock is not “a query waited too long.” It is a cycle of dependencies for
which no member can make progress by waiting. `LockManager._wait_graph()`
reconstructs dependencies from current owners and queue order.

For one resource owned by XID 4 with queue `[7, 9]`, XID 7 waits for 4. XID 9
waits for both 4 and earlier waiter 7, because FIFO prevents 9 from acquiring
first even after 4 releases. The graph therefore contains `7 -> 4` and
`9 -> {4, 7}`. Queue order is part of the blocking relation.

`src/minipostgres/transaction/deadlock.py`,
`WaitForGraph.deadlock_victim()`, performs depth-first search. `visited`
prevents repeated completed searches, while `active` and `stack` represent the
current recursion path. An edge to an active node identifies a cycle; the
function slices the stack at that node and returns the maximum XID in the
cycle.

Sorted nodes and targets make traversal deterministic, but the victim rule is
even more important for stable tests: the greatest XID loses. This is a
teaching policy, not a claim that the newest transaction always has the least
rollback cost.

## A two-row deadlock, step by step

Let low XID 10 update account A and high XID 11 update account B. Each owns one
tuple-root lock. Next:

1. XID 10 requests B and queues behind owner 11, producing edge `10 -> 11`.
2. XID 11 requests A and queues behind owner 10, producing `11 -> 10`.
3. `deadlock_victim()` sees cycle `{10, 11}` and chooses 11.
4. `LockManager._abort_victim()` invokes the manager's victim handler.
5. `TransactionManager._abort_deadlock_victim()` marks 11 failed and aborts
   it; abort releases B and removes 11's queued request for A.
6. The condition wakes XID 10, which can acquire B and continue.
7. The acquisition call in victim 11 raises `DeadlockDetected`.

The repository's concurrency test asserts both the exception and the survivor's
final committed values. Merely asserting that one thread stopped would miss
the crucial recovery contract.

Deadlock detection runs synchronously inside the wait loop rather than in a
background detector. There is no `deadlock_timeout`, no periodic worker, and
no user-configurable victim cost. The small state space makes immediate graph
construction clear and deterministic.

## Locks, MVCC, and uniqueness meet

Locks do not decide visibility. After waiting, the storage access method uses
transaction statuses and snapshots to resolve the globally live or
snapshot-visible version. Chapter 8's RR conflict and RC predicate recheck
therefore happen *after* tuple acquisition.

Likewise, a unique-key lock does not itself prove uniqueness. It provides
serialization for `_check_unique_global()` in
`src/minipostgres/storage/indexed.py`. That function examines matching index
candidates and heap-version status. An aborted insertion can leave derived
index state that does not represent a live conflict; a committed insertion
does. The lock makes the check-and-install sequence exclusive for that key.

Acquiring more than one unique key can itself participate in a wait cycle.
MiniPostgres uses one common `LockManager` and one union `LockKey`, so tuple and
key dependencies appear in the same graph rather than in disconnected
detectors.

## Failure state and client responsibility

A deadlock victim is aborted by the manager and its acquisition raises
`DeadlockDetected`. The client should treat the transaction as lost and begin
a new transaction if it wants to retry. Retrying only the final SQL statement
would omit earlier decisions made under the aborted transaction's snapshot.

The survivor is not automatically committed. It merely becomes runnable and
continues under its existing isolation rules. This distinction matters in
systems language: deadlock resolution restores *progress*, not success for all
remaining transactions.

`waiting_xids()` provides a diagnostic snapshot used by deterministic tests.
It lets a test wait until a transaction has actually entered a queue instead
of guessing with a long sleep. It is not a monitoring API with stable
production compatibility.

## Compared with PostgreSQL 18

PostgreSQL's heavyweight lock manager is centered in
`src/backend/storage/lmgr/lock.c`; row-level tuple locking crosses heap access
methods and multixact machinery. Deadlock search and reporting live in
`src/backend/storage/lmgr/deadlock.c`, usually triggered after
`deadlock_timeout`. Unique indexes use access-method cooperation and
speculative insertion rather than MiniPostgres's single encoded-key lock
abstraction.

Both systems reason over blocking dependencies and abort a victim to break a
cycle. PostgreSQL has many lock modes, soft edges from queue order, prepared
transactions, richer victim considerations, detailed diagnostics, and
cross-process shared memory. MiniPostgres has process-local Python condition
variables, exclusive modes, and “highest XID loses.”

The boundary is recorded in the `locks` row of the
[behavior matrix](../behavior-matrix.md) and in
[Differences from PostgreSQL](../differences.md).
The [PostgreSQL mapping](../postgresql-mapping.md) labels correspondence by
contract rather than file-format or API compatibility.

## Hands-on experiment: isolate the graph policy

This experiment calls the pure graph object, avoiding scheduling noise:

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline python - <<'PY'
from minipostgres.transaction.deadlock import WaitForGraph
print("cycle victim:", WaitForGraph({7: {9}, 9: {12}, 12: {7}}).deadlock_victim())
print("acyclic:", WaitForGraph({7: {9}, 9: {12}}).deadlock_victim())
PY
```

Measured output:

```text
cycle victim: 12
acyclic: None
```

Now verify FIFO acquisition and the full engine-level two-row cycle:

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline pytest -q \
  tests/unit/transaction/test_locks.py::test_lock_waiters_acquire_in_fifo_order \
  tests/concurrency/test_deadlock.py::test_two_row_deadlock_aborts_highest_xid
```

Measured output:

```text
..                                                                       [100%]
2 passed in 0.62s
```

The first test observes acquisition order 2 then 3. The second waits for real
queue entry, creates a cycle, observes `DeadlockDetected` in the high-XID
session, and verifies the low-XID transaction can commit.

## Exercises

1. **Understanding.** Resource R is owned by XID 3 and has FIFO queue
   `[5, 8]`. What graph edges does `_wait_graph()` add?

    Acceptance: include queue-order blockers, not only the owner.

    ??? note "Reference answer"
        It adds `5 -> {3}` and `8 -> {3, 5}`. XID 8 cannot pass XID 5 even
        after owner 3 releases.

2. **Understanding.** Why can a unique insert conflict exist before there is a
   tuple TID shared by both transactions?

    Acceptance: identify the resource that must be serialized and the check
    performed after waiting.

    ??? note "Reference answer"
        Both transactions compete for the same encoded index key while their
        prospective tuples have different or not-yet-published TIDs.
        `UniqueKeyLockKey` serializes that key; after acquisition,
        `_check_unique_global()` decides whether an existing candidate is
        globally live and conflicting.

3. **Hands-on.** In a disposable worktree, add a unit test for a four-node
   graph containing a three-node cycle plus an acyclic incoming node. Do not
   modify the tutorial author's `src/` tree.

    Acceptance: the selected victim must be the greatest XID *inside the
    cycle*, not the greatest XID anywhere in the graph; also add an assertion
    for a self-cycle. Run `tests/unit/transaction/test_deadlock_graph.py`.

    ??? note "Reference answer"
        One useful graph is `{20: {7}, 7: {9}, 9: {12}, 12: {7}}`. XID 20 is
        outside the cycle, so the victim is 12. A self-cycle such as
        `{4: {4}}` returns 4. No production change should be necessary because
        `deadlock_victim()` slices only the active DFS stack from the repeated
        node.

## Summary

MiniPostgres locks logical tuple roots and unique encoded keys with one
exclusive FIFO manager. Queue ownership and order induce a wait-for graph;
depth-first cycle detection chooses the highest cycle XID, abort releases its
resources, and survivors resume without being implicitly committed. The next
chapter makes those transaction outcomes durable: WAL ordering must ensure
that neither a dirty page nor a successful commit reaches the outside world
before its recovery evidence.
