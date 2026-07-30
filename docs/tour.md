# A Kernel Tour of a Query

> **Language**: English | [简体中文](zh/tour.md)

This tour starts when `Database.execute()` receives a SQL statement, follows
the real execution path through pages, transactions, and WAL, and then returns
to the maintenance mechanisms. Each stop uses one of the following three
labels to describe its relationship with PostgreSQL:

- **Equivalent**: preserves the same core contract or algorithmic shape; this
  does not imply byte-for-byte interface or file-format compatibility.
- **Deliberately simplified**: follows the same mechanism but narrows the
  syntax, concurrency, statistics, or durability boundary.
- **Semantically opposite**: adopts a strategy opposite to PostgreSQL's so
  that the teaching evidence is more direct.

## 0. Overall route

```text
SQL text
  -> sql/ lexer + parser + binder
  -> planner/ logical rules + cost optimizer
  -> executor/ Volcano tree
  -> storage/indexed.py
       -> storage/heap.py
       -> index/btree.py
       -> storage/buffer.py
  -> transaction visibility + locks
  -> wal/
  -> maintenance/ ANALYZE, VACUUM, HOT
```

Ordinary queries pull rows down through the first three stops. Write queries
also enter MVCC, locking, index maintenance, and WAL; explicit
`ANALYZE`/`VACUUM` operations later update statistics or reclaim old versions.

## 1. SQL text becomes bound semantics

**This project:** `src/minipostgres/sql/lexer.py`, `parser.py`, `binder.py`  
**PostgreSQL:** `src/backend/parser/scan.l`, `gram.y`, `analyze.c`, and
`parse_*.c`  
**Label: Deliberately simplified**

The Lexer and recursive-descent Parser produce only a syntax AST. The Binder
then reads the catalog and resolves table and column identities, types,
aliases, aggregate legality, and contextual `NULL`. This boundary between
parsing and analysis/binding corresponds to PostgreSQL's transition from a
raw parse tree to an analyzed `Query`. MiniPostgres differs by using a small,
frozen grammar and a JSON catalog rather than implementing PostgreSQL's full
type coercion, namespaces, permissions, and system-catalog semantics.

## 2. A logical plan becomes a physical plan

**This project:** `src/minipostgres/planner/`, `catalog/statistics.py`,
`maintenance/analyze.py`  
**PostgreSQL:** `src/backend/optimizer/`, `src/backend/statistics/`, and the
`pg_statistic` system catalog  
**Label: Deliberately simplified**

`planner.py` constructs an immutable logical plan, `rules.py` performs
constant folding, predicate pushdown, and column pruning, and `optimizer.py`
then compares SeqScan/IndexScan and NestedLoop/HashJoin while performing
bounded dynamic-programming join ordering for two through four tables.

`ANALYZE` produces row count, page count, null fraction, distinct count, MCVs,
and equi-depth histograms. Selectivity estimation consults MCVs first; equality
mass outside the MCV set is divided among the remaining distinct values, while
range predicates use histogram interpolation. This corresponds to PostgreSQL
deriving selectivity from the MCVs and histograms in `pg_statistic`, but this
project uses an exact full-table scan, fewer statistics types, and fixed cost
constants, and it has neither extended statistics nor PostgreSQL's many scan
and join paths.

## 3. The Volcano execution tree pulls rows

**This project:** `src/minipostgres/executor/base.py`, `factory.py`,
`operators.py`  
**PostgreSQL:** `src/backend/executor/execMain.c` and `node*.c`  
**Label: Equivalent**

The factory turns physical nodes into an executor tree. Every node follows
`open()` / `next()` / `close()`, and a parent pulls rows from its child one at
a time through `next()`. This is the Volcano/iterator model. The
`EXPLAIN ANALYZE` wrapper preserves the same pull contract while only
accumulating actual row counts and elapsed time for each node.

Here, "equivalent" refers to the execution model: PostgreSQL's executor uses
`ExecProcNode` to drive a plan-state tree, whereas MiniPostgres uses Python
objects and fewer node types.

## 4. DML, post-wait EPQ, and index coordination

**This project:** `executor/operators.py`,
`storage/indexed.py::replace_mvcc/delete_mvcc`  
**PostgreSQL:** the EvalPlanQual (EPQ) paths in
`src/backend/executor/execMain.c` and `nodeModifyTable.c`  
**Label: Equivalent (simplified)**

UPDATE/DELETE first collect candidate TIDs from the execution tree. After a
writer acquires the tuple lock, it may discover that another transaction has
already committed an update. Under Read Committed, it then reevaluates the
original WHERE predicate against the latest row and skips the modification if
the predicate no longer holds. This EPQ predicate recheck, newly implemented
in the working tree, preserves PostgreSQL's key rule that a stale candidate
must not be modified blindly after a wait.

The simplification is that it rechecks only the frozen expression subset and
the latest version of one row rather than rerunning PostgreSQL's full EPQ plan,
trigger, partition-routing, and related paths. Under Repeatable Read, a
serialization conflict is raised if the snapshot version differs from the
latest post-lock version.

## 5. Heap pages and MVCC visibility

**This project:** `src/minipostgres/storage/heap.py`,
`storage/slotted.py`, `transaction/visibility.py`  
**PostgreSQL:** `src/backend/access/heap/heapam.c` and
`HeapTupleSatisfiesMVCC` in `heapam_visibility.c`  
**Label: Equivalent (with a deliberately simplified layout)**

The heap consists of checksummed 8192-byte slotted pages, and a TID is the
stable pair `(page_id, slot_id)`. A version header stores `xmin`, `xmax`, and
the chain successor; visibility first checks the creator and then whether the
deleter is visible in the current snapshot. This preserves the core decision
order of `HeapTupleSatisfiesMVCC`.

This project's tuple header, slot format, and version chain are not
PostgreSQL's on-disk format. In particular, `root_tid()` scans every version
to expose predecessor relationships, with O(N) complexity. PostgreSQL locates
them directly through line-pointer redirection and HOT flags; this scan should
not be treated as a production implementation technique.

## 6. Buffer pool and clock sweep

**This project:** `src/minipostgres/storage/buffer.py`,
`storage/replacer.py`  
**PostgreSQL:** `src/backend/storage/buffer/bufmgr.c` and the clock sweep in
`freelist.c`  
**Label: Equivalent (simplified)**

A PageGuard owns one pin, and a pinned frame cannot be evicted. The clock hand
scans frames: a frame with its reference bit set has that bit cleared and gets
a second chance; an unreferenced, evictable frame becomes the victim. Before a
dirty page is written, it must pass through the WAL flush gate.

PostgreSQL uses production facilities including shared buffers, usage counts,
concurrent atomic state, and a background writer. This implementation is
in-process, fixed-frame, and deterministic, but its pin, second-chance, and
WAL-before-data contracts point in the same direction.

## 7. B+Tree lookup, split, and merge

**This project:** `src/minipostgres/index/`  
**PostgreSQL:** `src/backend/access/nbtree/`  
**Label: Deliberately simplified**

Page 0 is the metapage. Internal pages store separators and children; leaf
pages store encoded key/TID pairs and sibling links. An overflowing insert
splits the page and promotes a separator upward. An underfull deletion first
borrows from a sibling and then merges, shrinking the root when necessary.
Point and range lookups ultimately return candidate heap TIDs, and the
executor still rechecks the heap.

These structures correspond to `nbtree`, but omit PostgreSQL's concurrent
page-locking protocol, high keys, right-link concurrent traversal,
deduplication, suffix truncation, vacuum cycles, and other details. Key
encoding also covers only this project's bounded scalar set.

## 8. Transaction status and snapshots

**This project:** `transaction/status.py`, `snapshot.py`, `manager.py`  
**PostgreSQL:** `src/backend/access/transam/clog.c` (CLOG/`pg_xact`) and
`src/backend/utils/time/snapmgr.c`  
**Label: Equivalent (simplified)**

The status table reports whether an XID is in progress, committed, or aborted,
corresponding to CLOG's responsibility for transaction commit status. A
snapshot stores `xmax` and the active XID set: Read Committed refreshes it for
each statement, while Repeatable Read fixes it from the first data statement.
This corresponds to the snapshot lifetimes for isolation levels in snapmgr.

The status table is an in-memory, educational durability model, and snapshots
do not include PostgreSQL's full support for subtransactions, command IDs,
snapshot export/import, SSI predicate locks, and related features.

## 9. Writer locks and deadlock detection

**This project:** `transaction/locks.py`, `deadlock.py`  
**PostgreSQL:** `src/backend/storage/lmgr/lock.c`, `proc.c`, `deadlock.c`  
**Label: Deliberately simplified**

Tuple keys and unique keys use FIFO exclusive locks. Each waiter in the queue
points to the owner and earlier waiters to form a wait-for graph; when a cycle
is detected, the highest XID is selected as the deterministic victim. This
corresponds to PostgreSQL's detection of deadlocks from lock-wait
relationships, but PostgreSQL has a complete lock-mode/conflict matrix,
soft-edge reordering, and different victim handling. This project has neither
shared locks nor `SELECT FOR UPDATE`.

## 10. WAL, checkpoints, and recovery

**This project:** `src/minipostgres/wal/`, heap page LSN, and the buffer WAL
gate  
**PostgreSQL:** `src/backend/access/transam/xlog.c`, `xloginsert.c`, and
`full_page_writes`  
**Label: Semantically opposite (full-page-image strategy)**

MiniPostgres records a complete post-image for every heap-page change. A
commit is published only after its commit record is fsynced. Recovery uses the
page LSN to decide whether to REDO and rebuilds derived indexes after an
unclean recovery.

After a checkpoint, PostgreSQL attaches a full-page image to the first change
of a page to repair a torn page; later changes in the same checkpoint cycle
usually need only more compact physiological WAL records. PostgreSQL uses this
design because one FPI establishes the page's post-checkpoint baseline, after
which operation or block-local changes can be replayed. This greatly reduces
WAL, replication, and recovery I/O. MiniPostgres does the exact opposite by
writing a whole page every time. It uses more space but makes
WAL-before-data and idempotent REDO easy to observe. It is REDO-only and does
not have PostgreSQL's complete WAL-record ecosystem.

## 11. VACUUM, HOT, and statistics maintenance

**This project:** `src/minipostgres/maintenance/`,
`storage/indexed.py::vacuum`  
**PostgreSQL:** `src/backend/access/heap/vacuumlazy.c`, the HOT paths in
`heapam.c`, and `src/backend/commands/analyze.c`  
**Label: Deliberately simplified**

Explicit VACUUM computes a cleanup horizon from active snapshots, removes
exact index entries before reclaiming stable slots, and can prune dead
intermediate versions from a HOT chain. A HOT update requires the replacement
version to fit on the same heap page and every encoded index key to remain
unchanged, allowing the index to continue pointing to the root TID.

PostgreSQL's lazy vacuum, HOT redirect/dead line pointers, pruning, visibility
map, freezing, autovacuum, and statistics sampling are much richer. This
project uses explicit synchronous maintenance so tests can directly observe
when reclamation is safe and why no new index entry is required.

## Suggested reading order

First use `examples/demo.py` to run a SELECT with a WHERE clause and an UPDATE,
then follow calls through
`engine.py -> sql/ -> planner/ -> executor/ -> storage/indexed.py`. Next read
`transaction/visibility.py`, `storage/replacer.py`, and `wal/recovery.py`
individually, and finally use the concurrency, eviction, and crash experiments
in `LABS.md` to verify the contracts above.
