# MiniPostgres Reference Project Design

**Date:** 2026-07-27  
**Status:** Approved by delegated design authority  
**Repository:** `~/MiniPostgres-workspace/MiniPostgres`

## 1. Product definition

MiniPostgres is a single-process relational database kernel written in Python.
It is inspired by PostgreSQL's architecture, but it is not wire-compatible
with PostgreSQL and does not claim SQL-dialect compatibility.

The project exists to make this path executable and inspectable:

```text
SQL
→ AST
→ Binder
→ Logical Plan
→ Optimizer
→ Physical Plan
→ Volcano Executor
→ Heap / B+Tree
→ Buffer Pool
→ Disk
```

Transactions cross that path:

```text
Transaction Manager
├── XID and snapshot
├── tuple visibility
├── row and unique-key locks
├── transaction status
├── WAL and checkpoint
└── Vacuum horizon
```

The project is developed before the course. Course chapters, quizzes, and
teaching handoffs are deliberately excluded from this repository until the
reference implementation has passed final acceptance.

## 2. Graduation outcome

The finished project must demonstrate all of the following with executable
tests:

- binding SQL names to catalog identities;
- producing and recursively executing logical and physical plan trees;
- choosing between sequential and index scans and between nested-loop and
  hash joins;
- encoding rows in fixed-size slotted pages;
- accessing all persistent heap and index pages through a buffer pool;
- storing B+Tree entries as keys mapped to candidate TIDs;
- preserving stable TIDs while compacting tuple bytes inside a page;
- creating tuple versions for updates and applying snapshot visibility;
- preventing conflicting writers and detecting a two-transaction deadlock;
- enforcing the WAL-before-data and durable-commit-before-success rules;
- recovering committed state with REDO after injected crashes;
- keeping transactions without durable commit invisible after recovery;
- reclaiming dead tuple versions without violating an active snapshot;
- avoiding new index entries for eligible heap-only updates.

## 3. Design alternatives

Three alternatives were considered.

1. **Balanced relational database.** Give the parser, optimizer, storage,
   concurrency, and recovery equal depth. This gives broad feature coverage but
   weakens the PostgreSQL-specific storage and transaction story.
2. **Query-engine first.** Concentrate on SQL, cardinality estimation, join
   algorithms, and join ordering. This resembles a database query course more
   than a MiniPostgres kernel.
3. **Storage and transaction kernel first.** Keep a real query-processing
   loop, but make Heap/TID, Buffer Pool, B+Tree, MVCC, WAL, Vacuum, and HOT the
   architectural center.

Alternative 3 is selected. It matches the domain-first rule established by the
other Mini projects: generic boundaries stay thin, while the system's
distinctive state and failure semantics receive the implementation depth.

## 4. Authoritative references

PostgreSQL 18 stable documentation is the behavior and architecture reference.
Development-branch source code may clarify a mechanism but cannot silently
expand scope.

Primary reference areas:

- query path and executor;
- physical storage and page layout;
- B-Tree indexes;
- transaction identifiers and isolation;
- WAL internals;
- routine vacuuming and HOT.

The implementation is independent. PostgreSQL and educational database source
code are read as design references, never copied as an answer base.

## 5. Frozen scope

### 5.1 SQL statements

The accepted SQL subset is:

```sql
CREATE TABLE
CREATE INDEX

INSERT
SELECT
UPDATE
DELETE

BEGIN
COMMIT
ROLLBACK

WHERE
INNER JOIN
GROUP BY
ORDER BY
LIMIT

EXPLAIN
EXPLAIN ANALYZE
ANALYZE
VACUUM
```

Aggregates:

```text
COUNT
SUM
AVG
MIN
MAX
```

Constraints:

```text
NOT NULL
PRIMARY KEY
UNIQUE
```

### 5.2 Types and expression semantics

Types:

```text
INT64
FLOAT64
BOOLEAN
TEXT
NULL
```

Frozen rules:

- integers are signed 64-bit values and overflow is an error;
- `INT64` widens to `FLOAT64` for mixed numeric arithmetic and comparison;
- no other implicit casts exist;
- boolean predicates use SQL three-valued logic;
- comparisons involving `NULL` produce unknown except `IS NULL` and
  `IS NOT NULL`;
- `WHERE` retains only true rows;
- `COUNT(*)` counts rows, while the other aggregates ignore `NULL`;
- `AVG` returns `FLOAT64`;
- text is UTF-8 and uses bytewise binary collation;
- ascending sort places nulls last and descending sort places nulls first
  unless an explicit supported null-order modifier is present;
- result order is unspecified without `ORDER BY`.

### 5.3 Explicit exclusions

The project does not implement:

- PostgreSQL wire protocol or `psql` compatibility;
- PostgreSQL's complete grammar, casts, collations, or error text;
- rewrite rules, views, triggers, stored procedures, or extension APIs;
- users, roles, privileges, or authentication;
- foreign keys;
- SSI Serializable isolation;
- parallel query or multiple processes;
- replication or logical decoding;
- full TOAST, visibility map, index-only scan, or production autovacuum;
- GiST, GIN, BRIN, or hash indexes;
- XID wraparound and freezing;
- full ARIES analysis/REDO/UNDO;
- PostgreSQL's on-disk format.

## 6. Public API and process model

The normative API is synchronous and in-process:

```python
db = Database.open("./demo")
db.execute("CREATE TABLE users (id INT PRIMARY KEY, name TEXT)")

with db.transaction(isolation="repeatable_read") as tx:
    tx.execute("INSERT INTO users VALUES (1, 'Jonah')")
    rows = tx.execute("SELECT * FROM users WHERE id = 1")
```

A small REPL may call the same API. No network server exists.

The engine is single-process. Normal statement execution is synchronous.
Concurrency tests use Python threads plus deterministic barriers to create
specific interleavings. Process-local latches protect in-memory structures;
transaction locks protect logical rows and unique keys. These are different
mechanisms and have separate APIs.

## 7. Architecture and stable boundaries

```text
SQL text
   ↓
Lexer → Parser → AST
                 ↓
              Binder ← Catalog
                 ↓
          Logical Plan
                 ↓
             Optimizer ← Statistics
                 ↓
          Physical Plan
                 ↓
         Volcano Executor
          ↙             ↘
   Heap Access        B+Tree Access
          ↘             ↙
             Buffer Pool
                 ↓
             Disk Manager
                 ↓
        heap / index / WAL files
```

Stable interfaces are introduced before their persistent implementation:

- `TableAccess` owns tuple insertion, candidate scans, fetch, version update,
  and delete marking;
- `IndexAccess` owns key lookup, range iteration, insert, and delete;
- `PageStore` owns fixed-size page reads, writes, allocation, and sync;
- `BufferPool` is the only normal path from access methods to `PageStore`;
- `LogManager` owns WAL append, flush position, and record scanning;
- `TransactionManager` owns XIDs, snapshots, status, and commit protocol.

The early `MemoryTable` is retained as a reference implementation and test
double. The executor is not rewritten when `HeapTable` arrives.

## 8. Catalog and DDL contract

The catalog assigns stable numeric IDs to tables, columns, and indexes.
Metadata is stored in deterministic JSON using:

```text
write temporary file
→ fsync file
→ atomic replace
→ fsync parent directory
```

DDL is auto-commit and cannot execute inside an explicit user transaction.
The engine holds an exclusive schema latch while changing metadata. This
deliberately avoids transactional system catalogs.

Catalog metadata is not part of the heap WAL. `CREATE TABLE` creates storage
before publishing metadata. `CREATE INDEX` builds and fsyncs the complete index
before publishing it. Startup removes unpublished temporary artifacts and
rejects metadata that references missing primary storage.

## 9. Query front end

### 9.1 Lexer and parser

A hand-written lexer and recursive-descent parser implement only the frozen
grammar. The parser produces syntax-level AST nodes and never consults storage.

### 9.2 Binder

The binder:

- resolves table aliases and column names;
- rejects ambiguous and unknown columns;
- expands `*`;
- resolves catalog IDs;
- inserts the one allowed numeric widening;
- validates aggregate placement and grouping;
- produces typed bound expressions.

### 9.3 Logical and physical plans

Logical operators:

```text
Scan, Filter, Project, Join, Aggregate, Sort, Limit,
Insert, Update, Delete
```

Physical operators:

```text
Values, SeqScan, IndexScan, Filter, Project,
NestedLoopJoin, HashJoin, Aggregate, Sort, Limit,
ModifyTable
```

All plan nodes are immutable dataclasses. Expressions are independent of AST
nodes so execution does not depend on parser structures.

## 10. Executor

Every executor implements:

```python
open() -> None
next() -> Row | None
close() -> None
```

The executor uses demand-pull recursion. `close` is idempotent and is guaranteed
by a context manager even when evaluation fails.

Rows flowing between plan nodes contain typed values plus optional source TIDs.
`UPDATE` and `DELETE` require the source TID from their child plan. Modify
operators never mutate Python lists or disk files directly; they call
`TableAccess` under a transaction.

Runtime errors abort the current statement. Inside an explicit transaction,
the transaction becomes failed and accepts only `ROLLBACK`.

## 11. Page, tuple, and TID format

`PAGE_SIZE` is 8192 bytes.

```text
┌──────────────────────┐
│ fixed page header    │
├──────────────────────┤
│ slot directory       │ ↓
├──────────────────────┤
│ free space           │
├──────────────────────┤
│ tuple bytes          │ ↑
└──────────────────────┘
```

The page header contains:

```text
magic
format_version
page_type
page_id
page_lsn
lower
upper
special
checksum
```

The `page_lsn` field exists before WAL is implemented. The checksum covers the
serialized page with the checksum field zeroed.

A TID is:

```python
TID(page_id: int, slot_id: int)
```

Tuple compaction may move tuple bytes but never renumbers a live slot. A freed
slot can be reused only after Vacuum has removed every corresponding index
entry while holding the table maintenance lock. Unclean startup rebuilds
indexes before accepting requests, preventing stale persistent TIDs from
surviving a crash.

Tuple headers contain:

```text
xmin
xmax
next_version_tid
flags
column_count
null_bitmap_length
payload_length
```

The payload stores a length-delimited encoding. Tuples cannot span pages.
Oversized tuples fail with `RowTooLarge`.

## 12. Disk manager, heap, and buffer pool

The disk manager maps relation IDs and fork kinds to files. Page allocation is
append-only within a file; freed heap space is reused inside existing pages.

The buffer pool owns:

- a fixed number of frames;
- `page_id → frame` lookup per relation;
- pin counts;
- dirty state;
- a Clock replacement policy;
- page guards that unpin automatically.

Invariants:

- a pinned frame cannot be evicted;
- dirty eviction routes through the WAL flush gate;
- no executor or access method performs normal direct file reads;
- a page guard can mark a page dirty only with the LSN of the change;
- flushing a dirty page first flushes WAL through `page_lsn`.

The heap maintains an approximate free-space map:

```text
page_id → free-space category
```

It verifies the actual page before insertion and repairs stale estimates.

## 13. B+Tree

The B+Tree is page-based and contains:

- a metapage;
- internal pages;
- leaf pages;
- left and right leaf sibling links;
- root split;
- leaf and internal split;
- deletion, redistribution, and merge;
- ordered range iteration.

Leaf entries map encoded keys to ordered lists of TIDs. Internal separator keys
route searches. Unique indexes use the same structure but acquire a
transactional key lock before checking candidate heap versions.

The index returns candidate TIDs only. Every `IndexScan` fetches the heap tuple
and applies snapshot visibility.

Index pages persist on clean shutdown. Heap state is the recovery authority:
after an unclean shutdown, all indexes are rebuilt from committed visible heap
versions before the database opens. This deliberately avoids implementing
PostgreSQL's B-Tree WAL protocols while keeping index correctness observable.

## 14. Statistics, optimizer, and EXPLAIN

`ANALYZE` stores:

```text
row_count
page_count
null_fraction
distinct_count
min_value
max_value
most_common_values
equi_depth_histogram
```

The cost model estimates:

- sequential scan;
- index scan plus heap fetch;
- nested-loop join;
- hash join;
- in-memory and external-style sort work.

Rules:

- constant folding;
- filter pushdown;
- projection pruning;
- equality/range selectivity;
- sequential versus index scan;
- nested-loop versus hash join;
- dynamic-programming inner-join ordering for two through four relations.

Larger joins preserve source order. No cross-product elimination or exhaustive
search beyond four relations is promised.

`EXPLAIN` returns the chosen tree with estimated cost and rows.
`EXPLAIN ANALYZE` executes it and adds actual rows and elapsed time. Tests assert
structured plan fields rather than unstable formatted text or timing values.

## 15. Transactions, snapshots, and locks

XIDs are monotonically increasing positive integers and do not wrap.

Transaction states:

```text
IN_PROGRESS
COMMITTED
ABORTED
```

Snapshot:

```python
Snapshot(xmax: int, active_xids: frozenset[int])
```

Visibility additionally recognizes the current transaction so it sees its own
earlier writes.

Isolation:

- Read Committed obtains one snapshot per statement;
- Repeatable Read obtains one snapshot at its first data statement and reuses
  it for the transaction.

Updates mark the old tuple's `xmax` and insert a new tuple with the current
`xmin`. Deletes set `xmax`. Aborted creators are invisible; aborted deleters do
not hide the old version.

The lock manager provides:

- tuple write locks keyed by `(table_id, TID)`;
- unique-key locks keyed by `(index_id, encoded_key)`;
- FIFO wait queues;
- transaction-wide release;
- wait-for graph deadlock detection;
- deterministic victim choice: highest XID in the detected cycle.

This project does not emulate PostgreSQL's complete table-lock mode matrix.

## 16. WAL, commit, checkpoint, and recovery

The WAL is a checksummed, length-delimited append-only file. Each record has:

```text
record_length
record_type
lsn
xid
payload_length
payload
checksum
```

Record types:

```text
BEGIN
HEAP_PAGE_IMAGES
COMMIT
ABORT
CHECKPOINT
```

Each heap mutation record contains the complete post-image of every heap page
changed by that logical operation. This is intentionally larger than
PostgreSQL WAL, but makes REDO and torn-page repair precise without ARIES.

Commit protocol:

```text
append BEGIN lazily before first mutation
→ append page-image records before dirty pages may flush
→ append COMMIT
→ flush WAL through COMMIT
→ publish COMMITTED status
→ release locks
→ return success
```

Abort appends and flushes `ABORT` only if the transaction wrote data. Physical
tuple versions remain; visibility treats them as aborted and Vacuum reclaims
them.

Recovery:

```text
load control file
→ scan and checksum WAL from checkpoint LSN
→ truncate an incomplete final WAL record
→ REDO a page image when disk page is corrupt or page_lsn is older
→ derive durable transaction states
→ mark every remaining begun transaction ABORTED
→ rebuild all indexes after unclean shutdown
→ write a clean control state only at clean shutdown
```

The control file is checksummed and atomically replaced. A sharp checkpoint:

```text
flush WAL
→ flush all dirty heap pages
→ persist transaction-status snapshot
→ append and flush CHECKPOINT
→ atomically replace control file
```

WAL retention remains unbounded in the mainline implementation. WAL recycling
and fuzzy checkpoints are excluded.

## 17. Vacuum and HOT

Vacuum takes the table maintenance lock and computes:

```text
oldest_active_xid = min(active snapshot horizons)
```

It removes only versions that no active or future supported snapshot can see.
For each reclaimed version it:

1. removes matching index entries;
2. marks the heap slot reusable;
3. compacts tuple bytes without renumbering live slots;
4. updates the free-space map and statistics.

Vacuum does not promise to shrink relation files.

A simplified HOT update is eligible when:

- no indexed column changes;
- the source page has enough free space.

The old tuple links to the new tuple on the same page. Existing indexes retain
the root TID. Heap fetch follows the version chain and applies visibility. HOT
chain pruning occurs only when the same Vacuum horizon proves an intermediate
version dead.

HOT is implemented after ordinary MVCC, WAL, recovery, and Vacuum work. It is
an optimization, not a prerequisite for correctness.

## 18. Error model

Public errors are typed:

```text
SqlSyntaxError
BindError
TypeMismatch
ConstraintViolation
SerializationConflict
DeadlockDetected
TransactionAborted
RowTooLarge
CorruptPage
CorruptWal
CatalogError
DatabaseClosed
```

Errors never expose partially initialized plan or page objects. Corruption is
fail-closed unless WAL contains an applicable verified page image.

## 19. Test architecture

Test groups:

```text
tests/unit
tests/contract
tests/integration
tests/concurrency
tests/property
tests/crash
tests/differential
tests/acceptance
```

Core invariants:

- `lower <= upper <= special <= PAGE_SIZE`;
- every live slot references an in-page tuple extent;
- live tuple extents do not overlap;
- pinned frames are never selected for replacement;
- dirty heap pages cannot pass the WAL flush gate early;
- successful commit responses imply durable COMMIT records;
- B+Tree order and leaf sibling traversal agree;
- index results are heap-visibility checked;
- aborted creators are never visible;
- Vacuum preserves every version visible to an active snapshot;
- HOT does not add an index entry.

Property models:

- slotted page versus an abstract stable-slot model;
- B+Tree versus a sorted multimap;
- expression evaluation versus a three-valued reference evaluator;
- MVCC visibility versus an explicit truth table;
- recovered state versus durable acknowledged transaction history.

Differential tests run the frozen deterministic SQL subset against PostgreSQL
18 when a test DSN is explicitly configured. The default suite does not require
an external service. Differential comparison excludes planner text, timing,
exact errors, unsupported casts, locale collation, and unordered result order.

Crash tests run mutations in a subprocess and terminate at named failpoints:

```text
before WAL append
after WAL append before flush
after WAL flush before page write
during page write
after page write before COMMIT
after COMMIT append before flush
after COMMIT flush before response
during checkpoint file replacement
```

After recovery:

- every transaction that returned commit success is present;
- no transaction without durable commit is visible;
- indexes return the same visible rows as heap scans.

## 20. Implementation phases

### Phase A: Query loop

- package, errors, values, schema, and durable catalog;
- lexer, parser, AST, binder, and typed expressions;
- logical/physical plans and Volcano executor;
- `MemoryTable` reference access method;
- statements, joins, aggregates, sorting, limits, and basic EXPLAIN.

### Phase B: Persistent storage

- page codec, tuple codec, and stable TID;
- disk manager, buffer pool, page guards, Clock replacement;
- heap file and free-space map;
- page-based B+Tree and persistent catalog integration;
- restart and property tests.

### Phase C: Planning

- index scans;
- statistics and `ANALYZE`;
- cost model, transformation rules, join algorithm choice;
- join-order dynamic programming;
- structured `EXPLAIN ANALYZE`.

### Phase D: Transactions and recovery

- transactions, snapshots, visibility, and explicit isolation;
- tuple and unique-key locks plus deadlock detection;
- MVCC update/delete and constraint enforcement;
- WAL, page LSN, commit protocol, checkpoint, and REDO;
- subprocess crash matrix and index rebuild.

### Phase E: Maintenance and acceptance

- Vacuum horizon and index cleanup;
- stable-slot reuse and heap compaction;
- simplified HOT chains and pruning;
- PostgreSQL 18 differential profile;
- end-to-end acceptance and behavioral matrix.

Every phase ends in usable, tested software. Later phases replace no public
query interface and do not bypass earlier storage boundaries.

## 21. Repository layout

```text
MiniPostgres/
├── README.md
├── SCOPE.md
├── ARCHITECTURE.md
├── BEHAVIORAL_CONTRACT.md
├── DIFFERENCES_FROM_POSTGRESQL.md
├── pyproject.toml
├── src/minipostgres/
│   ├── engine.py
│   ├── errors.py
│   ├── sql/
│   ├── catalog/
│   ├── planner/
│   ├── executor/
│   ├── storage/
│   ├── index/
│   ├── transaction/
│   ├── wal/
│   └── maintenance/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── concurrency/
│   ├── property/
│   ├── crash/
│   ├── differential/
│   └── acceptance/
└── docs/superpowers/
    ├── specs/
    └── plans/
```

No `course/`, `days/`, quizzes, or teaching summaries are created during
reference-project development.

## 22. Final acceptance

Final acceptance requires:

1. a clean clone/install path using the declared package manager;
2. static checks and the complete default test suite passing;
3. query, storage, index, optimizer, MVCC, WAL, recovery, Vacuum, and HOT
   behavior linked to direct tests in a behavioral matrix;
4. a clean restart preserving committed catalog and data;
5. an unclean restart preserving durable commits, hiding incomplete
   transactions, and rebuilding correct indexes;
6. deterministic concurrency demonstrations for non-repeatable reads,
   repeatable reads, write conflicts, unique conflicts, and deadlock victim
   selection;
7. no direct executor-to-file or executor-to-Python-list storage bypass;
8. documentation stating every deliberate difference from PostgreSQL;
9. a clean Git worktree.

Passing a small smoke test is not evidence of project completion. Each listed
mechanism must have source, contract, failure, and acceptance evidence.

## 23. Sources

- PostgreSQL 18, *The Path of a Query*:  
  <https://www.postgresql.org/docs/18/query-path.html>
- PostgreSQL 18, *Database Page Layout*:  
  <https://www.postgresql.org/docs/18/storage-page-layout.html>
- PostgreSQL 18, *Transaction Isolation*:  
  <https://www.postgresql.org/docs/18/transaction-iso.html>
- PostgreSQL 18, *WAL Internals*:  
  <https://www.postgresql.org/docs/18/wal-internals.html>
- PostgreSQL 18, *Heap-Only Tuples*:  
  <https://www.postgresql.org/docs/18/storage-hot.html>
- PostgreSQL 18, *Routine Vacuuming*:  
  <https://www.postgresql.org/docs/18/routine-vacuuming.html>

