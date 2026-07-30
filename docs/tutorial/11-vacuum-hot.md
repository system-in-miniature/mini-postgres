# 11. VACUUM, Reclamation Horizons, and HOT Chains

MVCC avoids overwriting a version that an older snapshot may still need. The
cost is physical debris: aborted inserts, committed old versions, stale index
entries, and update chains. MiniPostgres reclaims that debris with explicit,
synchronous `VACUUM`. A global horizon protects active snapshots; exact index
entries are removed before heap slots are reused. Heap-only tuple (HOT)
updates reduce index churn when the replacement stays on the same page and
all encoded index keys are unchanged.

## Learning objectives

By the end of this chapter, you will be able to:

- compute the conservative cleanup horizon from active transactions;
- classify aborted and superseded versions as keep or dead;
- explain why stale index entries must disappear before slot reuse;
- trace a HOT update from eligibility through root-TID lookup and chain
  visibility;
- state how MiniPostgres VACUUM/HOT differs from PostgreSQL autovacuum,
  freezing, visibility maps, and line-pointer redirects.

## Reclamation requires a proof

A version being invisible to the transaction running VACUUM is not enough.
Another active RR transaction may hold an older snapshot that can still see
it. `src/minipostgres/maintenance/horizon.py`, `cleanup_horizon()`, finds a
conservative global boundary.

It starts with `next_xid`. For every active transaction, it adds either the
transaction's XID (if it has no pinned snapshot) or the pinned snapshot's
`xmax` and active XIDs. The minimum is the cleanup horizon. Any transaction
that could need old history therefore pulls the horizon backward.

`classify_version()` returns only `KEEP` or `DEAD`. An aborted creator older
than the horizon is dead. A version whose creator and deleter both committed,
whose `xmin` and nonzero `xmax` are older than the horizon, is dead. Everything
else stays. “Keep” can mean currently visible, possibly visible to an active
snapshot, too new to prove safe, or dependent on an unresolved outcome.

This conservative binary rule is intentionally easier to audit than a
production vacuum state machine. Reclamation occurs only after a proof that no
supported active snapshot needs the version.

## Engine-level VACUUM coordination

`src/minipostgres/engine.py`, `Database._vacuum()`, computes one horizon,
selects one table or all tables, and acquires a per-table maintenance lease
through `src/minipostgres/maintenance/coordinator.py`,
`MaintenanceCoordinator.maintenance()`. Ordinary inserts, updates, and deletes
take the corresponding writer lease. This prevents physical reclamation from
racing with table writers inside the single process.

Each `IndexedTableAccess.vacuum()` returns a `VacuumResult` with pages scanned,
dead versions removed, index entries removed, reclaimed bytes, and HOT
versions pruned. The engine sums results, marks statistics stale, and returns a
command tag such as `VACUUM 2`.

VACUUM is not allowed inside an explicit user transaction in
`Database.execute_for_session()`. It runs as its own statement transaction and
publishes WAL for its heap-page changes. It is manual: no background
autovacuum thread watches dead-tuple thresholds.

## Ordinary dead-version cleanup

`src/minipostgres/storage/indexed.py`,
`IndexedTableAccess.vacuum()`, snapshots the physical versions and first
identifies HOT chains. Versions not handled by chain pruning follow the
ordinary path:

1. apply `classify_version()` against the global horizon and status table;
2. for each published index, delete the exact `(encoded key, TID)` entry;
3. call `HeapTable.reclaim_version()` to delete the slot payload;
4. compact the slotted page and publish its new full-page WAL image.

Index deletion must precede slot reuse. A TID is `(page_id, slot_id)`.
Compaction keeps live slot IDs stable, but a dead slot can later hold a new
tuple. If a stale index entry remained, the same numeric TID could point to an
unrelated row. Heap rechecks protect query predicates, yet retaining such
aliases would violate index ownership and uniqueness reasoning.

`VACUUM` is physically idempotent for an unchanged state. A second run finds
no newly dead versions and reports zero removals. It compacts pages but does
not truncate relation files.

## What makes an update HOT

An ordinary MVCC update creates a successor and adds index entries for it.
When index keys did not change, that duplicates index references for versions
of one logical row. PostgreSQL's HOT idea is to keep one indexed root and link
heap-only successors on the same page.

MiniPostgres centralizes its rule in
`src/minipostgres/maintenance/hot.py`, `hot_eligible()`:

```python
return same_heap_page and old_index_keys == new_index_keys
```

`IndexedTableAccess.replace_mvcc()` first obtains the actual replacement TID
from `HeapTable.replace_version()`. It compares the replacement page to the
visible version's page and compares the encoded keys for every index. If both
conditions hold, it does not insert successor index entries. Otherwise every
new key/TID is published normally.

This is an outcome-based teaching rule. PostgreSQL decides eligibility from
modified attributes and available page space before or during placement.
MiniPostgres observes actual placement and encoded-key equality. Encoded
equality matters more than comparing a hand-picked SQL column because all
published indexes participate.

## Following and pruning a HOT chain

Heap tuple versions carry `next_tid`. `src/minipostgres/storage/heap.py`,
`HeapTable.version_chain()`, follows successors while verifying that the chain
has no cycle, every referenced slot exists, and every member stays on the root
page. `HeapTable.root_tid()` performs an O(N) scan of physical versions to
build a predecessor map and walk backward to the oldest member.

That root lookup is explicitly a simplification. PostgreSQL can use line
pointer redirect and HOT flags to locate chains without scanning all page
versions. MiniPostgres spends time to make the predecessor relationship
visible in Python.

Index scans find the root TID. `IndexedTableAccess.fetch_mvcc()` resolves the
version in that chain visible to the current snapshot. Thus an RR reader can
follow the same root to an older successor while a newer transaction follows
it to the newest committed member.

During VACUUM, a chain qualifies for HOT pruning when its root is indexed and
its successor is not independently indexed. Dead non-root members are
candidates, but the newest physical member is preserved unless the ordinary
path can remove the whole logical row. `HeapTable.prune_chain()` rewrites each
predecessor's `next_tid` around removable intermediates, reclaims their slots,
and logs page changes. The root index entry remains stable.

## Long snapshots demonstrate the safety boundary

The repository test
`tests/integration/test_vacuum_reuse.py::test_long_repeatable_snapshot_prevents_reclamation`
opens an RR reader on a row, performs a concurrent non-HOT update, and runs
VACUUM. The first VACUUM removes zero versions because the reader's pinned
snapshot lowers the horizon. After the reader commits, a second VACUUM can
reclaim at least one old version.

This is more meaningful than counting dead bytes after a single session. It
tests that maintenance respects a visibility promise made to another active
transaction. The behavior matrix's `vacuum` evidence row points directly to
that node.

## Compared with PostgreSQL 18

PostgreSQL heap vacuum and pruning span files such as
`src/backend/access/heap/vacuumlazy.c`, `pruneheap.c`, and `heapam.c`.
Autovacuum scheduling lives under `src/backend/postmaster/autovacuum.c`.
PostgreSQL tracks global visibility with horizons and transaction metadata,
cleans indexes, prunes HOT chains, freezes old XIDs, updates visibility and
free-space maps, and protects against wraparound.

MiniPostgres preserves the central safety story—do not reclaim what an active
snapshot can see; clean index entries before reuse; keep same-page,
index-unchanged successors heap-only—but omits autovacuum, freeze,
wraparound, visibility maps, cost delay, concurrent index vacuum protocols,
and file truncation. Its maintenance is synchronous and process-local.

See `vacuum` and `hot` in the
[behavior matrix](../behavior-matrix.md),
[Differences from PostgreSQL](../differences.md),
and the storage flow in the
[architecture reference](../architecture-reference.md).

## Hands-on experiment: prune a HOT chain

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres import Database

with TemporaryDirectory() as root, Database.open(root) as db:
    db.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
    db.execute("INSERT INTO users VALUES (1, 20)")
    for age in (21, 22, 23):
        db.execute(f"UPDATE users SET age = {age} WHERE id = 1")
    result = db.execute("VACUUM users")
    print(result.command_tag)
    print("rows:", db.execute("SELECT * FROM users").rows)
    print("removed:", result.maintenance.dead_versions_removed)
    print("HOT pruned:", result.maintenance.hot_versions_pruned)
PY
```

Measured output:

```text
VACUUM 2
rows: ((1, 23),)
removed: 2
HOT pruned: 2
```

The newest row remains and two obsolete intermediate versions are removed.
Verify the snapshot horizon and index-root contracts:

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline pytest -q \
  tests/integration/test_vacuum_reuse.py::test_long_repeatable_snapshot_prevents_reclamation \
  tests/integration/test_hot_pruning.py::test_vacuum_prunes_dead_hot_intermediates_and_keeps_index_root
```

```text
..                                                                       [100%]
2 passed in 1.02s
```

## Exercises

1. **Understanding.** Why is “not visible to the VACUUM transaction” weaker
   than “safe to reclaim”?

    Acceptance: include another session and its snapshot horizon.

    ??? note "Reference answer"
        A long RR session may retain a snapshot under which the old version is
        visible even though VACUUM's newer snapshot rejects it. The global
        horizon includes active snapshots and delays reclamation until none
        can need that history.

2. **Understanding.** An update changes no SQL values but its replacement is
   placed on another heap page. Is it HOT in MiniPostgres?

    Acceptance: apply both operands of `hot_eligible()`.

    ??? note "Reference answer"
        No. The encoded keys are equal, but `same_heap_page` is false. The
        successor needs normal index entries rather than a root-local HOT
        chain.

3. **Hands-on.** In a disposable worktree, add a test that runs VACUUM twice
   after deleting an indexed row and asserts index safety and idempotence. Do
   not edit the tutorial author's `src/` tree.

    Acceptance: first run removes one version and the exact index search is
    empty; second run removes zero; inserting a new row afterward must not be
    returned by searching the old key. Run the test plus
    `tests/property/test_vacuum_idempotence.py`.

    ??? note "Reference answer"
        Use the pattern in
        `tests/integration/test_vacuum_reuse.py`,
        `test_vacuum_removes_dead_versions_and_stale_index_entries`.
        Encode the old key with `KeyCodec`, inspect the published tree after
        the first VACUUM, then capture physical versions before and after the
        second. No production patch should be required.

## Summary

VACUUM is proof-driven physical cleanup. A conservative horizon includes every
active supported snapshot; dead ordinary versions lose exact index entries
before reusable slots, while HOT chains keep one indexed root and prune safe
intermediates. The design preserves the mechanism without PostgreSQL's broad
maintenance infrastructure. The final chapter asks how we know each claim is
true: tests must cover local rules, generated state spaces, component
boundaries, adversarial schedules/crashes, and end-to-end correspondence.
