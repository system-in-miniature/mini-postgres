# Phase A Query Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a typed, in-process SQL query loop over a retained `MemoryTable` access method, including catalog, parsing, binding, plans, Volcano execution, joins, aggregates, modification statements, and structured EXPLAIN.

**Architecture:** SQL text becomes syntax-only AST, then catalog-aware bound plans, then immutable logical and physical nodes executed through a demand-pull interface. The executor depends on `TableAccess`, not Python collections; `MemoryTable` is the first access-method implementation and remains a differential reference when disk heap arrives.

**Tech Stack:** Python 3.12, standard library, uv, pytest, Hypothesis, Ruff, Pyright.

---

## File map

```text
pyproject.toml                         package, test, lint, and type config
src/minipostgres/__init__.py           public Database and type exports
src/minipostgres/errors.py             typed public errors
src/minipostgres/types.py              SQL types, scalar values, three-valued logic
src/minipostgres/row.py                TID, column binding, execution/result rows
src/minipostgres/catalog/model.py      columns, tables, indexes, immutable schemas
src/minipostgres/catalog/catalog.py    ID allocation and atomic JSON metadata
src/minipostgres/sql/tokens.py         token kinds and keyword set
src/minipostgres/sql/lexer.py          SQL text to tokens
src/minipostgres/sql/ast.py            syntax-only statement/expression nodes
src/minipostgres/sql/parser.py         frozen recursive-descent grammar
src/minipostgres/sql/bound.py          typed expressions and bound statement forms
src/minipostgres/sql/binder.py         name/type/aggregate resolution
src/minipostgres/planner/logical.py    immutable logical operator tree
src/minipostgres/planner/physical.py   immutable physical operator tree
src/minipostgres/planner/planner.py    bound statements to initial plans
src/minipostgres/executor/base.py      open/next/close and execution context
src/minipostgres/executor/expressions.py bound expression evaluation
src/minipostgres/executor/memory.py    retained TableAccess reference implementation
src/minipostgres/executor/operators.py Volcano query and modification operators
src/minipostgres/executor/factory.py   physical plan to executor tree
src/minipostgres/engine.py             Database lifecycle and statement orchestration
tests/unit/                            focused codecs, lexer, parser, binder, expression tests
tests/contract/                        public SQL behavior and error contracts
tests/integration/                     multi-operator query loops and catalog restart
tests/property/                        expression and query model properties
```

### Task 1: Package, errors, types, and rows

**Files:**
- Create: `pyproject.toml`
- Create: `src/minipostgres/__init__.py`
- Create: `src/minipostgres/errors.py`
- Create: `src/minipostgres/types.py`
- Create: `src/minipostgres/row.py`
- Create: `tests/unit/test_types.py`
- Create: `tests/unit/test_rows.py`

- [ ] **Step 1: Write failing scalar and row tests**

```python
def test_sql_boolean_truth_tables_and_null_comparison() -> None:
    assert sql_and(True, None) is None
    assert sql_and(False, None) is False
    assert sql_or(True, None) is True
    assert sql_not(None) is None
    assert compare_values("=", None, 1) is None


def test_execution_row_merges_cells_and_tids() -> None:
    left = ExecutionRow({ColumnBinding(1, 0): 7}, {1: TID(0, 2)})
    right = ExecutionRow({ColumnBinding(2, 0): "x"}, {2: TID(0, 5)})
    merged = left.merge(right)
    assert merged.cells[ColumnBinding(1, 0)] == 7
    assert merged.tids == {1: TID(0, 2), 2: TID(0, 5)}
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest -q tests/unit/test_types.py tests/unit/test_rows.py
```

Expected: collection fails because `minipostgres.types` and
`minipostgres.row` do not exist.

- [ ] **Step 3: Implement the package primitives**

Define:

```python
class DataType(Enum):
    INT64 = "int64"
    FLOAT64 = "float64"
    BOOLEAN = "boolean"
    TEXT = "text"

Scalar = int | float | bool | str | None

@dataclass(frozen=True, slots=True)
class TID:
    page_id: int
    slot_id: int

@dataclass(frozen=True, slots=True)
class ColumnBinding:
    table_id: int
    column_id: int

@dataclass(slots=True)
class ExecutionRow:
    cells: dict[ColumnBinding, Scalar]
    tids: dict[int, TID]
    computed: dict[object, Scalar] = field(default_factory=dict)
```

Implement strict scalar validation, int64 overflow checks, the sole
`INT64 → FLOAT64` widening, SQL boolean operators, null-propagating arithmetic
and comparison, and typed errors from the accepted design.

- [ ] **Step 4: Run primitive tests and static checks**

Run:

```bash
uv run pytest -q tests/unit/test_types.py tests/unit/test_rows.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src tests/unit
git commit -m "feat: add MiniPostgres value primitives"
```

### Task 2: Durable catalog

**Files:**
- Create: `src/minipostgres/catalog/__init__.py`
- Create: `src/minipostgres/catalog/model.py`
- Create: `src/minipostgres/catalog/catalog.py`
- Create: `tests/unit/catalog/test_model.py`
- Create: `tests/integration/test_catalog_restart.py`

- [ ] **Step 1: Write failing catalog tests**

```python
def test_catalog_assigns_stable_ids_and_survives_restart(tmp_path: Path) -> None:
    catalog = Catalog.open(tmp_path)
    users = catalog.create_table(
        "users",
        (
            Column("id", DataType.INT64, nullable=False),
            Column("name", DataType.TEXT, nullable=True),
        ),
    )
    reopened = Catalog.open(tmp_path)
    assert reopened.table("users") == users
    assert reopened.table(users.table_id).schema.column("name").column_id == 1


def test_catalog_rejects_duplicate_names_case_insensitively(tmp_path: Path) -> None:
    catalog = Catalog.open(tmp_path)
    catalog.create_table("Users", (Column("id", DataType.INT64),))
    with pytest.raises(CatalogError):
        catalog.create_table("users", (Column("other", DataType.INT64),))
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest -q tests/unit/catalog tests/integration/test_catalog_restart.py
```

Expected: collection fails because catalog modules do not exist.

- [ ] **Step 3: Implement immutable metadata and atomic persistence**

Define immutable `Column`, `Schema`, `TableMetadata`, and `IndexMetadata`
dataclasses. `Catalog.open(path)` reads `catalog.json` or starts with
`next_table_id=1` and `next_index_id=1`. Mutations serialize sorted,
versioned JSON to `catalog.json.tmp`, fsync it, replace `catalog.json`, and
fsync the directory.

Names are normalized with `casefold`. Metadata retains the original display
name. Table and column lookups accept stable numeric IDs.

- [ ] **Step 4: Run catalog tests**

Run:

```bash
uv run pytest -q tests/unit/catalog tests/integration/test_catalog_restart.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/catalog tests/unit/catalog tests/integration/test_catalog_restart.py
git commit -m "feat: persist typed catalog metadata"
```

### Task 3: Lexer

**Files:**
- Create: `src/minipostgres/sql/__init__.py`
- Create: `src/minipostgres/sql/tokens.py`
- Create: `src/minipostgres/sql/lexer.py`
- Create: `tests/unit/sql/test_lexer.py`
- Create: `tests/property/test_lexer_literals.py`

- [ ] **Step 1: Write failing lexer examples and properties**

```python
def test_lexer_handles_keywords_identifiers_numbers_and_sql_strings() -> None:
    tokens = lex("SELECT name, 1.5 FROM users WHERE note = 'it''s ok';")
    assert [token.kind for token in tokens] == [
        TokenKind.SELECT, TokenKind.IDENT, TokenKind.COMMA,
        TokenKind.FLOAT, TokenKind.FROM, TokenKind.IDENT,
        TokenKind.WHERE, TokenKind.IDENT, TokenKind.EQ,
        TokenKind.STRING, TokenKind.SEMICOLON, TokenKind.EOF,
    ]
    assert tokens[9].value == "it's ok"


@given(st.text(alphabet=st.characters(blacklist_characters="'\x00")))
def test_quoted_string_round_trips(value: str) -> None:
    escaped = value.replace("'", "''")
    assert lex(f"'{escaped}'")[0].value == value
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest -q tests/unit/sql/test_lexer.py tests/property/test_lexer_literals.py
```

Expected: collection fails because lexer modules do not exist.

- [ ] **Step 3: Implement a bounded lexer**

Create position-aware tokens for identifiers, frozen keywords, integers,
floats, strings, punctuation, arithmetic, comparison operators, and EOF.
Reject NUL, unterminated strings, malformed numeric literals, and unknown
characters with `SqlSyntaxError(line, column, message)`.

- [ ] **Step 4: Run lexer tests and checks**

Run:

```bash
uv run pytest -q tests/unit/sql/test_lexer.py tests/property/test_lexer_literals.py
uv run ruff check src tests
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/sql tests/unit/sql tests/property/test_lexer_literals.py
git commit -m "feat: tokenize the frozen SQL subset"
```

### Task 4: AST and recursive-descent parser

**Files:**
- Create: `src/minipostgres/sql/ast.py`
- Create: `src/minipostgres/sql/parser.py`
- Create: `tests/unit/sql/test_parser_ddl_dml.py`
- Create: `tests/unit/sql/test_parser_select.py`
- Create: `tests/unit/sql/test_parser_precedence.py`

- [ ] **Step 1: Write failing statement and precedence tests**

```python
def test_parse_select_join_group_order_limit() -> None:
    stmt = parse(
        "SELECT u.name, COUNT(o.id) AS n "
        "FROM users u INNER JOIN orders o ON u.id = o.user_id "
        "WHERE o.total >= 10 GROUP BY u.name ORDER BY n DESC LIMIT 5"
    )
    assert isinstance(stmt, SelectStmt)
    assert stmt.from_table.alias == "u"
    assert len(stmt.joins) == 1
    assert stmt.limit == 5


def test_and_binds_more_tightly_than_or() -> None:
    stmt = parse("SELECT * FROM t WHERE a = 1 OR b = 2 AND c = 3")
    assert isinstance(stmt.where, BinaryExpr)
    assert stmt.where.operator == "OR"
    assert isinstance(stmt.where.right, BinaryExpr)
    assert stmt.where.right.operator == "AND"
```

Also cover `CREATE TABLE`, `INSERT` with multiple rows, `UPDATE`, `DELETE`,
`EXPLAIN [ANALYZE]`, null literals, `IS [NOT] NULL`, unary operators, aliases,
qualified stars, and a trailing semicolon.

- [ ] **Step 2: Run parser tests and verify RED**

Run:

```bash
uv run pytest -q tests/unit/sql/test_parser_ddl_dml.py \
  tests/unit/sql/test_parser_select.py tests/unit/sql/test_parser_precedence.py
```

Expected: collection fails because AST and parser modules do not exist.

- [ ] **Step 3: Implement immutable AST and parser**

Use frozen, slotted dataclasses for statement and expression nodes. Parse
expressions with:

```text
OR → AND → NOT → comparison/IS NULL → +,- → *,/ → unary → primary
```

Require exactly one statement per `parse` call. Keep all AST names unresolved
and preserve source spelling for diagnostics.

- [ ] **Step 4: Run parser tests**

Run:

```bash
uv run pytest -q tests/unit/sql
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/sql tests/unit/sql
git commit -m "feat: parse the MiniPostgres SQL subset"
```

### Task 5: Bound expressions and binder

**Files:**
- Create: `src/minipostgres/sql/bound.py`
- Create: `src/minipostgres/sql/binder.py`
- Create: `tests/unit/sql/test_binder_names.py`
- Create: `tests/unit/sql/test_binder_types.py`
- Create: `tests/unit/sql/test_binder_aggregates.py`

- [ ] **Step 1: Write failing binder contracts**

```python
def test_binder_rejects_ambiguous_unqualified_column(catalog: Catalog) -> None:
    statement = parse(
        "SELECT id FROM users u INNER JOIN orders o ON u.id = o.user_id"
    )
    with pytest.raises(BindError, match="ambiguous"):
        Binder(catalog).bind(statement)


def test_binder_widens_int_for_float_arithmetic(catalog: Catalog) -> None:
    bound = Binder(catalog).bind(parse("SELECT amount + 1 FROM payments"))
    expression = bound.items[0].expression
    assert expression.data_type is DataType.FLOAT64


def test_binder_requires_nonaggregate_columns_in_group_by(catalog: Catalog) -> None:
    with pytest.raises(BindError, match="GROUP BY"):
        Binder(catalog).bind(parse("SELECT region, COUNT(*) FROM sales"))
```

- [ ] **Step 2: Run binder tests and verify RED**

Run:

```bash
uv run pytest -q tests/unit/sql/test_binder_names.py \
  tests/unit/sql/test_binder_types.py tests/unit/sql/test_binder_aggregates.py
```

Expected: imports fail because binder modules do not exist.

- [ ] **Step 3: Implement catalog-aware binding**

Create hashable bound-expression nodes carrying `data_type` and `nullable`.
Resolve table scopes, aliases, stable `ColumnBinding` values, stars, output
aliases, comparison compatibility, arithmetic widening, boolean predicates,
aggregate signatures, grouping legality, and `ORDER BY` aliases.

Bound modification statements include target table IDs, target column IDs, and
typed expressions. Binder never accesses table rows.

- [ ] **Step 4: Run binder tests**

Run:

```bash
uv run pytest -q tests/unit/sql
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/sql tests/unit/sql
git commit -m "feat: bind SQL names and expression types"
```

### Task 6: Logical and physical plans

**Files:**
- Create: `src/minipostgres/planner/__init__.py`
- Create: `src/minipostgres/planner/logical.py`
- Create: `src/minipostgres/planner/physical.py`
- Create: `src/minipostgres/planner/planner.py`
- Create: `tests/unit/planner/test_logical_planner.py`
- Create: `tests/unit/planner/test_physical_planner.py`

- [ ] **Step 1: Write failing plan-shape tests**

```python
def test_select_plan_orders_filter_before_projection(bound_users_query) -> None:
    logical = Planner().logical(bound_users_query)
    assert isinstance(logical, LogicalProject)
    assert isinstance(logical.child, LogicalFilter)
    assert isinstance(logical.child.child, LogicalScan)


def test_join_defaults_to_nested_loop_in_phase_a(bound_join_query) -> None:
    physical = Planner().physical(Planner().logical(bound_join_query))
    joins = collect_nodes(physical, PhysicalNestedLoopJoin)
    assert len(joins) == 1
```

- [ ] **Step 2: Run planner tests and verify RED**

Run:

```bash
uv run pytest -q tests/unit/planner
```

Expected: collection fails because planner modules do not exist.

- [ ] **Step 3: Implement immutable plan nodes and baseline lowering**

Represent every logical and physical operator in the accepted design as a
frozen dataclass. Phase A lowers scans to sequential scans, equi-joins to hash
joins when one side is a simple equality key and to nested loops otherwise,
and inserts aggregate/sort/limit/modify nodes in semantic order.

Keep estimated cost and rows optional in Phase A, represented by `None`.

- [ ] **Step 4: Run planner tests**

Run:

```bash
uv run pytest -q tests/unit/planner tests/unit/sql
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/planner tests/unit/planner
git commit -m "feat: plan bound SQL into Volcano operators"
```

### Task 7: TableAccess and retained MemoryTable

**Files:**
- Create: `src/minipostgres/executor/__init__.py`
- Create: `src/minipostgres/executor/memory.py`
- Create: `tests/unit/executor/test_memory_table.py`
- Create: `tests/property/test_memory_table_model.py`

- [ ] **Step 1: Write failing access-method tests**

```python
def test_memory_table_uses_stable_tids_and_tombstones() -> None:
    table = MemoryTable(table_id=1, schema=users_schema)
    first = table.insert((1, "A"))
    second = table.insert((2, "B"))
    table.delete(first)
    assert table.fetch(first) is None
    assert table.fetch(second) == (2, "B")
    assert list(table.scan()) == [(second, (2, "B"))]


@given(st.lists(st.tuples(st.integers(), st.text()), unique=True))
def test_scan_matches_insert_model(rows) -> None:
    table = MemoryTable(table_id=1, schema=users_schema)
    tids = [table.insert(row) for row in rows]
    assert list(table.scan()) == list(zip(tids, rows, strict=True))
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest -q tests/unit/executor/test_memory_table.py \
  tests/property/test_memory_table_model.py
```

Expected: collection fails because `MemoryTable` does not exist.

- [ ] **Step 3: Implement the access protocol and reference table**

Define a runtime-checkable `TableAccess` protocol with:

```python
insert(values) -> TID
fetch(tid) -> tuple[Scalar, ...] | None
scan() -> Iterator[tuple[TID, tuple[Scalar, ...]]]
replace(tid, values) -> TID
delete(tid) -> bool
```

`MemoryTable` assigns `TID(0, monotonically_increasing_slot)`, keeps deleted
slots as tombstones, validates rows against schema, and never exposes its
internal containers.

- [ ] **Step 4: Run access tests**

Run:

```bash
uv run pytest -q tests/unit/executor/test_memory_table.py \
  tests/property/test_memory_table_model.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/executor tests/unit/executor tests/property/test_memory_table_model.py
git commit -m "feat: add the reference table access method"
```

### Task 8: Expression evaluator and core Volcano operators

**Files:**
- Create: `src/minipostgres/executor/base.py`
- Create: `src/minipostgres/executor/expressions.py`
- Create: `src/minipostgres/executor/operators.py`
- Create: `src/minipostgres/executor/factory.py`
- Create: `tests/unit/executor/test_expressions.py`
- Create: `tests/unit/executor/test_query_operators.py`
- Create: `tests/property/test_expression_model.py`

- [ ] **Step 1: Write failing evaluator and operator tests**

```python
def test_filter_drops_false_and_unknown_rows(context) -> None:
    child = StubExecutor(rows_for_values(True, False, None))
    executor = FilterExecutor(child, bound_boolean_column, context)
    assert collect(executor) == [rows_for_values(True)[0]]


def test_hash_join_preserves_duplicate_matches(context) -> None:
    left = StubExecutor(user_rows((1, "A"), (1, "B")))
    right = StubExecutor(order_rows((1, 10), (1, 20)))
    executor = HashJoinExecutor(left, right, user_id_expr, order_user_id_expr, context)
    assert len(collect(executor)) == 4
```

Property tests compare arithmetic, comparisons, and boolean combinations
against a small explicit three-valued reference evaluator.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest -q tests/unit/executor/test_expressions.py \
  tests/unit/executor/test_query_operators.py tests/property/test_expression_model.py
```

Expected: imports fail because executor components do not exist.

- [ ] **Step 3: Implement execution context and operators**

Implement idempotent `open`/`close`, context-managed collection, and:

```text
ValuesExecutor
SeqScanExecutor
FilterExecutor
ProjectExecutor
NestedLoopJoinExecutor
HashJoinExecutor
AggregateExecutor
SortExecutor
LimitExecutor
```

`AggregateExecutor` supports global aggregation on empty input, grouped
aggregation, aggregate null rules, and deterministic group encounter order.
`SortExecutor` uses frozen binary/null ordering. The factory recursively maps
physical nodes to executors.

- [ ] **Step 4: Run executor tests**

Run:

```bash
uv run pytest -q tests/unit/executor tests/property/test_expression_model.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/executor tests/unit/executor tests/property/test_expression_model.py
git commit -m "feat: execute relational operators with Volcano"
```

### Task 9: Modification operators and constraints

**Files:**
- Modify: `src/minipostgres/executor/operators.py`
- Modify: `src/minipostgres/executor/factory.py`
- Create: `tests/unit/executor/test_modify_operators.py`
- Create: `tests/contract/test_constraints.py`

- [ ] **Step 1: Write failing DML and constraint tests**

```python
def test_update_uses_source_tid_and_returns_affected_count(engine) -> None:
    engine.execute("CREATE TABLE users (id INT NOT NULL, age INT)")
    engine.execute("INSERT INTO users VALUES (1, 20), (2, 30)")
    result = engine.execute("UPDATE users SET age = age + 1 WHERE id = 2")
    assert result.command_tag == "UPDATE 1"
    assert engine.execute("SELECT age FROM users WHERE id = 2").rows == ((31,),)


def test_not_null_is_enforced_before_access_mutation(engine) -> None:
    engine.execute("CREATE TABLE users (id INT NOT NULL)")
    with pytest.raises(ConstraintViolation):
        engine.execute("INSERT INTO users VALUES (NULL)")
    assert engine.execute("SELECT COUNT(*) FROM users").rows == ((0,),)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest -q tests/unit/executor/test_modify_operators.py \
  tests/contract/test_constraints.py
```

Expected: tests fail because modify executors and engine fixture are missing.

- [ ] **Step 3: Implement insert, update, and delete executors**

Add `InsertExecutor`, `UpdateExecutor`, and `DeleteExecutor`. Validate complete
candidate rows before mutating `TableAccess`. Update and delete consume source
TIDs from their child rows. Return one command-result row containing the
affected count; the engine converts it to a command tag.

Phase A enforces `NOT NULL`. `PRIMARY KEY` and `UNIQUE` metadata parse and bind,
but their indexed concurrency-safe enforcement begins with B+Tree integration.

- [ ] **Step 4: Run modification tests**

Run:

```bash
uv run pytest -q tests/unit/executor tests/contract/test_constraints.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/executor tests/unit/executor tests/contract/test_constraints.py
git commit -m "feat: execute validated row modifications"
```

### Task 10: Database orchestration and SQL contract

**Files:**
- Create: `src/minipostgres/engine.py`
- Modify: `src/minipostgres/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/contract/test_database_api.py`
- Create: `tests/integration/test_query_loop.py`
- Create: `tests/integration/test_join_aggregate.py`

- [ ] **Step 1: Write failing public API tests**

```python
def test_database_executes_query_loop_across_statements(tmp_path: Path) -> None:
    with Database.open(tmp_path) as db:
        db.execute("CREATE TABLE users (id INT NOT NULL, name TEXT)")
        assert db.execute(
            "INSERT INTO users VALUES (1, 'A'), (2, 'B')"
        ).command_tag == "INSERT 0 2"
        result = db.execute(
            "SELECT name FROM users WHERE id >= 1 ORDER BY id DESC LIMIT 1"
        )
        assert result.columns == ("name",)
        assert result.rows == (("B",),)


def test_join_group_and_aggregate_end_to_end(engine) -> None:
    seed_users_and_orders(engine)
    result = engine.execute(
        "SELECT u.name, COUNT(o.id), SUM(o.total) "
        "FROM users u INNER JOIN orders o ON u.id = o.user_id "
        "GROUP BY u.name ORDER BY u.name"
    )
    assert result.rows == (("A", 2, 30), ("B", 1, 7))
```

- [ ] **Step 2: Run integration tests and verify RED**

Run:

```bash
uv run pytest -q tests/contract/test_database_api.py \
  tests/integration/test_query_loop.py tests/integration/test_join_aggregate.py
```

Expected: imports fail because `Database` does not exist.

- [ ] **Step 3: Implement the engine lifecycle**

`Database.open(path)` owns a catalog and table-access registry. `execute`:

```text
parse → bind → logical plan → physical plan → executor tree → materialize result
```

`CREATE TABLE` is auto-commit, persists metadata, and installs a `MemoryTable`.
On Phase A reopen, catalog metadata survives but rows are empty by explicit
contract. `close` is idempotent; operations after close raise `DatabaseClosed`.

Return immutable:

```python
QueryResult(columns: tuple[str, ...], rows: tuple[tuple[Scalar, ...], ...],
            command_tag: str)
```

- [ ] **Step 4: Run the SQL contract**

Run:

```bash
uv run pytest -q tests/contract tests/integration
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/engine.py src/minipostgres/__init__.py tests
git commit -m "feat: close the in-process SQL query loop"
```

### Task 11: Structured EXPLAIN and failure-state cleanup

**Files:**
- Modify: `src/minipostgres/planner/physical.py`
- Modify: `src/minipostgres/executor/base.py`
- Modify: `src/minipostgres/engine.py`
- Create: `tests/contract/test_explain.py`
- Create: `tests/integration/test_executor_cleanup.py`

- [ ] **Step 1: Write failing EXPLAIN and cleanup tests**

```python
def test_explain_returns_structured_plan_without_executing(engine) -> None:
    engine.execute("CREATE TABLE users (id INT)")
    result = engine.execute("EXPLAIN DELETE FROM users")
    assert result.plan is not None
    assert result.plan.node_type == "ModifyTable"
    assert engine.execute("SELECT COUNT(*) FROM users").rows == ((0,),)


def test_executor_tree_closes_after_expression_error(engine, monkeypatch) -> None:
    tracker = install_close_tracker(monkeypatch)
    with pytest.raises(TypeMismatch):
        engine.execute("SELECT 1 / 0")
    assert tracker.opened == tracker.closed
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest -q tests/contract/test_explain.py \
  tests/integration/test_executor_cleanup.py
```

Expected: tests fail because structured plan output and cleanup instrumentation
are absent.

- [ ] **Step 3: Implement explain output and guaranteed closure**

Add immutable `PlanExplanation(node_type, details, estimated_rows,
estimated_cost, actual_rows, elapsed_ms, children)`. `EXPLAIN` only plans;
`EXPLAIN ANALYZE` measures execution with `perf_counter` and records actual row
counts. The engine owns executor closure in `finally`.

- [ ] **Step 4: Run explain and cleanup tests**

Run:

```bash
uv run pytest -q tests/contract/test_explain.py \
  tests/integration/test_executor_cleanup.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres tests/contract/test_explain.py \
  tests/integration/test_executor_cleanup.py
git commit -m "feat: explain plans and close failed executions"
```

### Task 12: Phase A documentation and acceptance

**Files:**
- Create: `README.md`
- Create: `SCOPE.md`
- Create: `ARCHITECTURE.md`
- Create: `BEHAVIORAL_CONTRACT.md`
- Create: `DIFFERENCES_FROM_POSTGRESQL.md`
- Create: `tests/acceptance/test_phase_a.py`

- [ ] **Step 1: Write failing documentation and acceptance checks**

```python
def test_phase_a_query_engine_acceptance(tmp_path: Path) -> None:
    with Database.open(tmp_path) as db:
        create_acceptance_schema(db)
        load_acceptance_rows(db)
        assert_query_join_aggregate_update_delete_and_explain(db)


def test_docs_state_project_not_course_and_memory_boundary() -> None:
    readme = Path("README.md").read_text()
    assert "not PostgreSQL-compatible" in readme
    assert "MemoryTable" in readme
    assert "course is designed after the reference project" in readme
```

- [ ] **Step 2: Run acceptance tests and verify RED**

Run:

```bash
uv run pytest -q tests/acceptance/test_phase_a.py
```

Expected: fails because acceptance helper and project documents are absent.

- [ ] **Step 3: Write reference-project documentation**

Document the direct API, frozen SQL/type subset, query flow, TableAccess
boundary, Phase A volatility, error contracts, unsupported PostgreSQL
features, and exact commands for installation and verification. Do not create
course chapters or quizzes.

- [ ] **Step 4: Run full Phase A verification**

Run:

```bash
uv sync
uv run ruff check .
uv run pyright src
uv run pytest -q
git diff --check
```

Expected: static checks pass, all tests pass, and diff check is silent.

- [ ] **Step 5: Commit Phase A acceptance**

```bash
git add README.md SCOPE.md ARCHITECTURE.md BEHAVIORAL_CONTRACT.md \
  DIFFERENCES_FROM_POSTGRESQL.md tests/acceptance
git commit -m "docs: accept MiniPostgres query engine phase"
```

## Plan self-review

- Every Phase A design requirement maps to a task.
- Parser, binder, planner, executor, and access-method types have one owner.
- `MemoryTable` is retained rather than bypassed or discarded.
- Persistence claims are limited to catalog metadata in Phase A.
- Primary/unique syntax is accepted, but enforcement is explicitly deferred to
  the indexed storage phase rather than falsely implemented with a scan.
- Transaction statements, `CREATE INDEX`, `ANALYZE`, and `VACUUM` remain
  reserved for their owning phases.
- No task creates course material or a network adapter.
- Every task uses test-first, explicit RED/GREEN commands, static checks, and a
  focused commit.

