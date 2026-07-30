# Chapter 1 — Meet MiniPostgres

MiniPostgres is a database kernel you can hold in your head. It is large enough
to make parsing, planning, pages, indexes, MVCC, WAL, and maintenance executable,
but deliberately smaller than PostgreSQL. That boundary is the point of the
project: we can inspect a complete mechanism before confronting all the
production concerns that surround it.

This book follows the code that exists in this repository. A statement about a
mechanism names its source owner, and an experiment records output observed from
the current tree. MiniPostgres is not a server and does not speak the PostgreSQL
wire protocol. Its public interface is a synchronous Python API.

## Learning objectives

By the end of this chapter, you will be able to:

1. create a database directory and execute SQL through `Database`;
2. interpret the three public fields of `QueryResult`;
3. trace the outer boundary of one statement through
   `Database.execute()` and `Database.execute_for_session()`;
4. distinguish a modeled PostgreSQL mechanism from product compatibility; and
5. locate every later chapter on the end-to-end query path.

## Why read a teaching kernel?

Reading PostgreSQL directly is valuable, but it is a difficult first exposure.
One logical operation may cross generated parser code, system catalogs,
extension hooks, process-shared state, portability layers, decades of
compatibility decisions, and concurrency protocols. Those are necessary in a
production database. They can also hide the small invariant you are trying to
learn.

MiniPostgres narrows the environment while retaining the shape of the
relational kernel. The route advertised in `README.md` is executable:

```text
SQL
→ Lexer / Parser
→ Binder
→ Logical Plan
→ Rule Rewriter / Cost Optimizer
→ Physical Plan
→ Volcano Executor
→ TableAccess
→ Heap / B+Tree
→ Buffer Pool
→ Relation Pages / WAL
```

The narrowing is explicit. The catalog is JSON rather than transactional
system tables. The grammar is frozen. There are four scalar types. Execution
is in one Python process. Those choices let a test observe invariants such as
stable tuple identifiers and WAL-before-data ordering without pretending to
be a PostgreSQL replacement. Keep the repository's
[differences page](../differences.md), [behavior matrix](../behavior-matrix.md),
and [PostgreSQL mapping](../postgresql-mapping.md) beside this book.

## The public boundary

The public package exports `Database` from `src/minipostgres/__init__.py`.
`Database.open()` in `src/minipostgres/engine.py` converts its argument to a
`Path`, opens the catalog, and constructs the engine. Construction opens
statistics, disk, WAL, and the control file; performs recovery; creates the
buffer pool; opens heap and index access methods; and creates transaction and
execution services. This is more than an in-memory SQL evaluator: a directory
is a durable database identity.

The normal ownership pattern is a context manager:

```python
with Database.open("./demo") as db:
    result = db.execute("SELECT 1")
```

`Database.__exit__()` delegates to `Database.close()`. Closing takes a clean
checkpoint and releases the disk manager. Use the context manager in examples
so that success and exceptions both cross the intended shutdown path.

`Database.execute()` is intentionally thin:

```python
def execute(self, sql: str) -> QueryResult:
    return self._default_session.execute(sql)
```

The default session calls `Database.execute_for_session()`. That function is
the outer coordinator for a statement. It parses and binds the SQL, recognizes
transaction-control statements, starts an implicit transaction when needed,
takes a statement snapshot, dispatches DDL, maintenance, EXPLAIN, or relational
work, and then commits or aborts the implicit transaction. Later chapters open
each of those boxes.

The return type is the frozen dataclass `QueryResult` in
`src/minipostgres/engine.py`. Its learner-facing fields are:

- `columns`: a tuple of output column names;
- `rows`: an immutable tuple of immutable row tuples; and
- `command_tag`: a concise description such as `SELECT 2` or `INSERT 0 2`.

It also has structured `plan` and `maintenance` fields for EXPLAIN and VACUUM.
Do not parse the command tag to recover rows. The fields have separate jobs.

## Your first database

From the repository root, synchronize the locked development environment:

```bash
uv sync
```

The project requires Python 3.12 or later. The rest of this tutorial prefixes
commands with `uv run`, ensuring they use the environment described by
`pyproject.toml` and `uv.lock`.

### Experiment: execute a complete query loop

Run:

```bash
uv run python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres import Database

with TemporaryDirectory() as root, Database.open(root) as db:
    print(db.execute(
        "CREATE TABLE users (id INT PRIMARY KEY, name TEXT)"
    ).command_tag)
    print(db.execute(
        "INSERT INTO users VALUES (1, 'Ada'), (2, 'Grace')"
    ).command_tag)
    result = db.execute("SELECT name FROM users ORDER BY id")
    print(result.columns)
    print(result.rows)
    print(result.command_tag)
PY
```

Observed output:

```text
CREATE TABLE
INSERT 0 2
('name',)
(('Ada',), ('Grace',))
SELECT 2
```

Every operation used the direct API; no socket or background service was
involved. The temporary directory still exercised catalog publication,
relation files, WAL, transactions, and clean shutdown. `PRIMARY KEY` also
caused the engine's `_create_constraint_index()` path to publish a durable
unique B+Tree, although this query did not need to expose that implementation
detail.

The ordering is deterministic because the query includes `ORDER BY id`.
Without `ORDER BY`, SQL does not promise a presentation order even if a simple
scan currently appears stable.

## Following the call once

For a `SELECT`, `Database.execute_for_session()` calls the public `parse()`
function in `src/minipostgres/sql/parser.py`, then
`Binder.bind()` in `src/minipostgres/sql/binder.py`. It asks
`TransactionManager.statement_snapshot()` for visibility state and passes a
transaction-specific `ExecutionContext` to `Database._dispatch()`.

`_dispatch()` routes a `BoundSelect` to `_execute_relational()`. That method:

1. calls `Planner.logical()` in `src/minipostgres/planner/planner.py`;
2. calls `Database._optimize()`, which constructs a
   `CostBasedOptimizer` and returns a physical plan;
3. calls `build_executor()` and `collect()` in the executor package; and
4. uses `_materialize_select()` to turn internal execution rows into immutable
   public tuples.

For INSERT, UPDATE, and DELETE, the same relational route returns one computed
affected-row count and formats it as a command tag. This common pipeline is a
useful architectural test: modification operators do not bypass binding,
planning, execution, or transaction ownership.

Errors also have transaction semantics. If parse or binding fails inside an
explicit transaction, `execute_for_session()` marks that transaction failed.
If dispatch fails in an implicit transaction, it aborts the transaction before
re-raising. Typed exceptions live in `src/minipostgres/errors.py`; the project
does not claim PostgreSQL SQLSTATE or message-text compatibility.

## The map of this book

Chapters 2–6 move forward through the query and storage path. Chapter 2 turns
SQL text into bound semantics. Chapter 3 descends into 8192-byte pages, stable
slots, the buffer pool, Clock replacement, and the free-space map. Chapter 4
explains tuple versions and snapshot visibility. Chapter 5 studies persistent
B+Trees. Chapter 6 builds statistics and chooses physical plans.

Chapters 7–12 continue with Volcano execution, isolation behavior, locks and
deadlocks, WAL recovery, VACUUM/HOT, and the repository's five-layer testing
methodology. The order alternates between representation and policy: first
learn what state exists, then learn who may observe or change it.

## Compared with PostgreSQL

The closest PostgreSQL entry point is a backend receiving a statement through
the frontend/backend protocol, not a call to a Python object. PostgreSQL then
crosses parsing, analysis, rewrite, planning, and execution subsystems. The
pipeline shape is related, but the interface and supported surface are not.

The repository's [differences page](../differences.md) is categorical: there
is no server process, wire protocol, `psql`, authentication, roles, privileges,
or complete SQL dialect. Storage files, catalogs, WAL, and checkpoints use
custom formats. The [mapping](../postgresql-mapping.md) labels correspondences
as equivalent, deliberately simplified, or semantically opposite; an
“equivalent” label applies to a core contract, never byte compatibility.

For this chapter, the evidence row is `query_path` in the
[behavior matrix](../behavior-matrix.md). It names
`src/minipostgres/engine.py` as owner and an integration test proving that SQL
is bound, planned, optimized, and executed. That is stronger than a diagram,
but narrower than a claim of PostgreSQL compatibility.

## Exercises

### 1. Understanding: results versus tags

Why does `QueryResult` keep `rows` and `command_tag` separate? Give one example
where treating the tag as data would lose information.

??? note "Reference answer"

    A tag summarizes statement completion, such as `SELECT 2`; it does not
    contain column names, values, NULLs, or types. The two selected names in
    the experiment cannot be reconstructed from `SELECT 2`. Immutable
    `columns` and `rows` are the data contract; the tag is status metadata.

### 2. Hands-on: prove persistence across a clean restart

Write a temporary script that creates a table in a non-temporary subdirectory,
closes the database, reopens it, and selects the inserted row. Do not change
`src/`.

Acceptance:

- the first context manager prints `INSERT 0 1`;
- the second prints `((7, 'persistent'),)`; and
- the directory contains catalog, relation, WAL, and control artifacts.

??? note "Reference answer"

    One possible script is:

    ```python
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from minipostgres import Database

    with TemporaryDirectory() as parent:
        root = Path(parent) / "db"
        with Database.open(root) as db:
            db.execute("CREATE TABLE notes (id INT, body TEXT)")
            print(db.execute(
                "INSERT INTO notes VALUES (7, 'persistent')"
            ).command_tag)
        with Database.open(root) as db:
            print(db.execute("SELECT * FROM notes").rows)
        print(sorted(path.name for path in root.iterdir()))
    ```

### 3. Hands-on design: add a public diagnostic without implementing it

Propose a `Database.storage_root` read-only property. Identify the source
location, write the minimal diff, and specify a test. Keep the repository
unchanged.

Acceptance:

- the property calls `_ensure_open()`;
- it returns the existing `Path` rather than a string; and
- the test verifies access after `close()` raises `DatabaseClosed`.

??? note "Reference answer"

    The proposed diff belongs beside `Database.catalog` in
    `src/minipostgres/engine.py`:

    ```diff
    +    @property
    +    def storage_root(self) -> Path:
    +        self._ensure_open()
    +        return self._root
    ```

    A focused test should open a database, assert
    `database.storage_root == tmp_path`, call `database.close()`, and use
    `pytest.raises(DatabaseClosed)` around a second property access.

## Summary

MiniPostgres exposes a small public API without reducing the internal journey
to a toy: `Database.execute_for_session()` coordinates parsing, binding,
snapshots, dispatch, execution, and transaction completion, and `QueryResult`
returns immutable data. The project models selected PostgreSQL mechanisms but
does not implement a PostgreSQL-compatible product. In Chapter 2, we open the
first box and watch raw characters acquire syntax, names, types, and SQL
three-valued meaning.
