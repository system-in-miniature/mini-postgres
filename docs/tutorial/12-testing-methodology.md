# 12. Testing Methodology: From Local Rules to PostgreSQL 18

MiniPostgres is credible as a teaching kernel only when its mechanisms are
executable claims rather than architectural resemblance. A parser smoke test
cannot prove crash durability; a successful restart cannot prove snapshot
isolation; matching one PostgreSQL query cannot prove internal page safety.
This repository therefore layers focused tests, executable contracts,
property models, integration/restart scenarios, adversarial concurrency and
crash experiments, final acceptance, and an explicitly configured PostgreSQL
18 differential profile.

This chapter organizes those directories into five evidence layers. The layers
overlap by design: a high-risk mechanism should be observed through more than
one lens.

## Learning objectives

After this chapter, you will be able to:

- choose the smallest test layer that can falsify a proposed mechanism;
- explain what property, integration, concurrency, crash, and acceptance tests
  prove—and what they do not;
- trace a behavior-matrix claim to a source owner and directly collectable
  pytest node;
- run the local five-layer confidence slice and interpret its result;
- configure a PostgreSQL 18 differential run without mistaking a skipped
  external profile for passed compatibility.

## Layer 1: local rules and public contracts

Unit tests isolate algorithms and state transitions. Examples include lexer
tokens, binder name resolution, expression arithmetic, slotted-page
compaction, Clock replacement, B+Tree split/merge, snapshot visibility, wait
graph cycles, WAL framing, and cleanup horizons. A failure points to a narrow
owner, which makes this the cheapest layer for edge cases.

Contract tests sit nearby but focus on stable observable behavior:
`QueryResult`, transaction commands, `EXPLAIN`, uniqueness, and public schema
constraints. They may cross several classes while staying bounded to one API
promise. For example,
`tests/contract/test_explain_analyze.py` proves that every plan node has
estimated and actual fields and that analysis does not change selected rows.

The source owners are the functions used throughout this tutorial:
`src/minipostgres/executor/expressions.py`, `evaluate()`;
`src/minipostgres/transaction/visibility.py`, `is_visible()`;
`src/minipostgres/wal/records.py`, `encode_record()` and `decode_record()`; and
`src/minipostgres/maintenance/horizon.py`, `classify_version()`.

Local tests are necessary but insufficient. A correct `decode_record()` test
does not show that engine startup invokes recovery at the right boundary.

## Layer 2: property and reference-model checks

Example-based tests enumerate cases the author remembered. Property tests
generate many valid action sequences or values and compare the implementation
with a simpler model. The repository uses Hypothesis for:

- SQL expression evaluation versus a three-valued reference evaluator;
- slotted pages versus an abstract stable-slot model;
- B+Tree contents versus a sorted multimap;
- heap behavior versus a logical table model;
- encoded key order versus accepted scalar order;
- join-order alternatives preserving the same result;
- selectivity staying within probability bounds;
- VACUUM idempotence.

`tests/property/test_expression_model.py`, for example, is not a benchmark. It
searches combinations of SQL boolean values and operators for a semantic
counterexample. `tests/property/test_btree_multimap.py` can find a structural
sequence—insert, duplicate, delete, range—that a few hand-written examples may
miss.

A property is only as good as its oracle and strategy. Comparing two paths that
share the same faulty helper can create false confidence. The reference model
should be smaller and structurally independent, and generated states must
include boundaries such as `NULL`, minimum/maximum int64, page fullness,
duplicate keys, and repeated cleanup.

## Layer 3: integrated ownership and restart

Integration tests exercise boundaries that unit tests intentionally replace:
engine-to-catalog, executor-to-heap, heap-to-buffer, buffer-to-disk,
B+Tree publication, and clean restart. They ask whether individually correct
components are wired in the correct order.

Representative tests create a database directory, execute SQL through
`src/minipostgres/engine.py`, `Database.execute_for_session()`, close or reopen
it, and assert catalog, rows, indexes, statistics, or instrumentation. This
catches failures such as an executor bypassing `TableAccess`, a dirty page not
being flushed on clean close, or an index build being published before its
relation is durable.

Restart matters because in-memory assertions can pass while durable state is
wrong. `tests/integration/test_btree_restart.py` verifies point/range behavior
after clean restart. HOT and VACUUM integration nodes inspect both logical
query results and physical/index consequences. The
[architecture reference](../architecture-reference.md) describes the
ownership boundaries these tests cross.

## Layer 4: adversarial schedules and failure positions

Concurrency tests use independent `DatabaseSession` objects, Python threads,
and observable synchronization such as `LockManager.waiting_xids()`. They
construct non-repeatable reads, pinned RR snapshots, writer waits, uniqueness
races, and a two-row deadlock. Deterministic barriers or queue observations are
stronger evidence than “sleep and hope the race happened.”

Reliability tests inspect WAL/page ordering and restart recovery. Crash tests
go further: a subprocess reaches a named failpoint and terminates without
normal cleanup. The matrix includes positions before/after WAL append and
flush, during page write, around COMMIT, and during checkpoint publication.
After restart, durable acknowledged transactions must be visible, incomplete
transactions must not be visible, and derived indexes must agree with heap
truth.

`src/minipostgres/testing/failpoints.py`, `hit()`, is the narrow injection
boundary used by commit and storage paths. A failpoint is not a mock durability
result; it creates a precise interruption position so real on-disk recovery
code can be observed.

These tests remain bounded to one process's files and Python concurrency. They
do not demonstrate network partitions, replication, kernel/filesystem
behavior on every platform, or PostgreSQL's multi-process shared-memory
interactions.

## Layer 5: acceptance, traceability, and differential behavior

Acceptance tests compose completed mechanisms into phase and final stories.
`tests/acceptance/test_final_acceptance.py` creates 300 indexed accounts,
analyzes statistics, observes an `IndexScan`, checks RR visibility across a
writer commit, vacuums, checkpoints, reopens, and verifies data plus cleanup of
temporary index-build artifacts. This is a valuable closure test precisely
because lower layers already localize failures.

Traceability prevents a broad acceptance pass from becoming vague.
`src/minipostgres/acceptance.py`, `load_behavior_matrix()`, parses
`BEHAVIOR_MATRIX.md` into `BehaviorEvidence`: area, contract, source paths,
test node IDs, and deliberate difference. It rejects duplicate areas, missing
source evidence, and missing tests. Each row is therefore a machine-checkable
claim-to-owner-to-test link, not a decorative coverage table.

Finally, `src/minipostgres/differential/postgres.py`,
`Postgres18.connect()`, imports psycopg, connects to an explicitly supplied
DSN, and verifies `server_version_num` is in the PostgreSQL 18 range.
`Postgres18.execute()` executes SQL and normalizes fetched rows to tuples. The
current profile test proves that the configured service is PostgreSQL 18 and
that it reports the expected deterministic literal semantics. It does **not**
yet execute the same SQL through MiniPostgres in that test, so it is an
external-profile probe and adapter foundation, not a completed two-engine
differential comparison.

The intended differential overlap is deliberately narrow. A paired comparison
must exclude unsupported SQL, planner text, cost/timing, error strings, locale
collation, and unordered result order. Once both engines are actually run, a
match shows only that selected observable semantics agree; it does not make
MiniPostgres PostgreSQL-compatible.

## Compared with PostgreSQL's own test ecosystem

PostgreSQL uses extensive regression, isolation, TAP, recovery, upgrade, and
platform/buildfarm testing. Its source tree includes expected-output
regression tests and the `src/test/isolation` scheduler for controlled
concurrent permutations. MiniPostgres borrows the methodological idea that
different risks need different harnesses, not those harness formats.

MiniPostgres's `tests/differential/` supplies the version-gated adapter for
using a real PostgreSQL 18 server as an external semantic oracle. The present
test validates that profile; a true differential case must additionally run
MiniPostgres and compare normalized results. PostgreSQL itself is not an oracle
for MiniPostgres-specific page bytes, structured plan objects, typed Python
exceptions, or deterministic highest-XID victim selection. Those deliberate
differences are listed in
[Differences from PostgreSQL](../differences.md), while the
[behavior matrix](../behavior-matrix.md) links positive claims to local proof
and the [PostgreSQL mapping](../postgresql-mapping.md) classifies conceptual
correspondence.

## Hands-on experiment: one slice through five layers

This command selects a local rule, a property model, an integrated SQL loop, a
concurrency behavior, and final acceptance:

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline pytest -q \
  tests/unit/test_types.py \
  tests/property/test_expression_model.py \
  tests/integration/test_query_loop.py \
  tests/concurrency/test_read_phenomena.py \
  tests/acceptance/test_final_acceptance.py
```

Measured output:

```text
..........                                                               [100%]
10 passed in 7.55s
```

Ten collected tests passed. This is a teaching slice, not a replacement for
the complete suite.

## PostgreSQL 18 differential profile — requires runtime validation

The profile requires a PostgreSQL 18 server reached through a DSN, so it
requires socket access and is marked **requires runtime validation** in this
environment. The local command was still collected without a DSN:

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline pytest -q \
  tests/differential/test_postgres18.py
```

Measured local output:

```text
s                                                                        [100%]
=========================== short test summary info ============================
SKIPPED [1] tests/differential/test_postgres18.py:13: MINIPOSTGRES_PG18_DSN is not configured
1 skipped in 0.29s
```

That is a skip, not a pass. To perform the runtime validation where PostgreSQL
18 is available, install the optional group, create an isolated test database,
and provide its DSN:

```bash
uv sync --group postgres18
MINIPOSTGRES_PG18_DSN='postgresql://USER:PASSWORD@HOST:5432/TEST_DB' \
  uv run pytest -q tests/differential/test_postgres18.py
```

Do not point a differential suite with future mutating cases at valuable data.
`Postgres18.connect()` will reject PostgreSQL 17 or 19 even if the connection
succeeds.

## Exercises

1. **Understanding.** Which layer should own the invariant “live tuple extents
   never overlap,” and which additional layer proves those pages survive
   restart?

    Acceptance: choose two distinct layers and explain their different
    failure localization.

    ??? note "Reference answer"
        Unit/property tests for slotted pages should generate layouts and
        assert non-overlap locally. An integration/restart test should write
        those pages through the buffer/disk boundary and decode them after
        reopen. The first isolates layout logic; the second verifies wiring
        and persistence.

2. **Understanding.** Why does the no-DSN differential result above not count
   as PostgreSQL parity evidence?

    Acceptance: cite the observed pytest state and the code guard that caused
    it.

    ??? note "Reference answer"
        Pytest reported `SKIPPED`, not passed. The test checks
        `MINIPOSTGRES_PG18_DSN` and calls `pytest.skip()` when absent, so no
        socket connection and no comparison through `Postgres18.execute()`
        occurred.

3. **Hands-on.** In a disposable worktree, add a behavior-matrix row for a
   real existing contract and a parser test that proves malformed rows are
   rejected. Do not edit the tutorial author's `src/` tree.

    Acceptance: the row must name at least one source path, a collectable exact
    pytest node ID, and a deliberate difference; the positive parser test and
    malformed-row test must both pass.

    ??? note "Reference answer"
        Choose an implemented behavior not already represented, add its exact
        source owner and node ID to `BEHAVIOR_MATRIX.md`, and extend
        `tests/acceptance/test_behavior_matrix.py` with a temporary malformed
        table containing the wrong cell count or a missing test item. Assert
        `load_behavior_matrix()` raises `ValueError`. Do not invent a source
        or test merely to satisfy the schema.

4. **Hands-on.** Extend the PostgreSQL 18 differential profile with one frozen
   read-only expression supported by both systems.

    Acceptance: first add a local MiniPostgres assertion, then compare the
    normalized ordered rows against `Postgres18.execute()`; document why
    collation, planner text, timing, and error text are excluded. The result
    remains **requires runtime validation** until run against PostgreSQL 18.

    ??? note "Reference answer"
        A bounded candidate is arithmetic plus explicit `NULL` predicates,
        using an `ORDER BY` whenever multiple rows are returned. Keep setup in
        an isolated test database. Check the server-version guard, run the
        exact differential node with `MINIPOSTGRES_PG18_DSN`, and record the
        live output; a local skip is not acceptance.

## Summary

Trust comes from matched evidence, not test count alone. Local and contract
tests isolate rules, property models search state spaces, integration tests
cross ownership and restart boundaries, adversarial tests force schedules and
crash positions, and acceptance plus the PostgreSQL 18 adapter/profile
establish the path to explicit external comparison without claiming the
current skip or probe is a paired result. The behavior matrix keeps each positive
claim attached to source, proof, and a deliberate PostgreSQL difference. With
that methodology, the preceding chapters form an inspectable database kernel
rather than a collection of plausible diagrams.
