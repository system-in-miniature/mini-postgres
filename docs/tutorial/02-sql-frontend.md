# Chapter 2 — The SQL Front End

A database must separate what text says from what that text means in a
particular catalog. MiniPostgres makes the separation visible: the lexer emits
positioned tokens, the recursive-descent parser builds a syntax tree, and the
binder resolves catalog identities and types. Only then may planning begin.

## Learning objectives

After this chapter, you can:

1. trace SQL through `lex()`, `parse()`, and `Binder.bind()`;
2. explain how recursive-descent functions encode precedence;
3. distinguish an AST column name from a stable `ColumnBinding`;
4. evaluate `NULL` predicates with SQL three-valued logic; and
5. predict when MiniPostgres inserts its sole implicit numeric widening.

## Characters become positioned tokens

The public `lex()` function in `src/minipostgres/sql/lexer.py` constructs
`_Lexer` and calls `_Lexer.scan()`. The scanner maintains byte-independent
source offsets plus one-based line and column positions. `_identifier()`
case-folds a candidate to recognize the keyword map in
`src/minipostgres/sql/tokens.py`; otherwise it emits `IDENT`.
`_number()` distinguishes integer and floating literals and rejects non-finite
floating values. `_string()` accepts SQL's doubled-quote escape. `_symbol()`
recognizes punctuation and operators, including two-character comparisons.

Every token is a frozen `Token` with kind, lexeme, typed value, line, and
column. The explicit EOF token matters: the parser can require that exactly one
statement was consumed. Syntax failures therefore name a location rather than
silently accepting a valid prefix.

This lexer is bounded by design. It is not PostgreSQL's `scan.l`: there are no
quoted identifiers, dollar-quoted strings, comments, parameters, or the full
operator language. The exact supported surface is visible in `TokenKind` and
`KEYWORDS`, rather than implied by the word “SQL.”

## Tokens become a syntax AST

`parse()` in `src/minipostgres/sql/parser.py` creates `_Parser(source)` and
calls `_Parser.parse()`. The constructor lexes immediately. `parse()` obtains
one statement, optionally consumes one semicolon, and then requires EOF.
`_statement()` dispatches CREATE, INSERT, SELECT, UPDATE, DELETE, EXPLAIN,
ANALYZE, VACUUM, and transaction control.

Expression precedence is encoded by calls:

```text
_expression
  → _or
    → _and
      → _not
        → _comparison
          → _additive
            → _multiplicative
              → _unary
                → _primary
```

Each level consumes operators of one precedence and delegates operands to the
next tighter level. Thus `1 + 2 * 3` becomes addition whose right child is
multiplication. `_comparison()` permits one comparison or `IS [NOT] NULL` and
explicitly rejects chained comparisons. `_primary()` handles literals,
parentheses, column references, stars, and function-call syntax.

The dataclasses in `src/minipostgres/sql/ast.py` remain syntactic. A
`ColumnRef("id")` does not yet say which table or type owns `id`.
`Literal(None)` is deliberately untyped. Keeping the AST catalog-free lets the
parser be tested with no database directory.

## The binder assigns meaning

`Binder.bind()` in `src/minipostgres/sql/binder.py` resets its scope and
dispatches by statement class. `_bind_table_ref()` asks the `Catalog` for
metadata, establishes an alias, rejects duplicate visible names, and rejects
self-joins because runtime identity is currently a catalog table ID rather
than an alias instance.

`_resolve_column()` searches the current scope. Zero matches produce “unknown
column”; multiple matches produce “ambiguous column.” One match becomes a
`BoundColumn` containing `ColumnBinding(table_id, column_id)`, display name,
`DataType`, and nullability. The stable IDs survive later rewrites even when
names or output aliases would be ambiguous.

Binding also validates contexts. `_bind_predicate()` requires BOOLEAN.
`_bind_function()` recognizes only supported aggregates, prevents aggregates
in WHERE/JOIN, prevents nesting, and determines result types. Grouped queries
are checked so unaggregated columns are actually grouping keys. `*` is
expanded only where its context permits.

The bound nodes in `src/minipostgres/sql/bound.py` are immutable semantic
input to the planner. That is the front-end boundary: later layers should not
redo name lookup or guess literal types.

## NULL and three-valued logic

Python has two booleans; SQL predicates have `TRUE`, `FALSE`, and `UNKNOWN`.
MiniPostgres represents UNKNOWN as `None` in the `SqlBool` alias in
`src/minipostgres/types.py`.

`sql_not()` preserves UNKNOWN. `sql_and()` returns false if either operand is
false, otherwise UNKNOWN if either is unknown. `sql_or()` returns true if
either operand is true, otherwise UNKNOWN if either is unknown.
`compare_values()` returns UNKNOWN immediately when either side is NULL.
WHERE keeps only TRUE, so both FALSE and UNKNOWN are filtered out.

This explains a sometimes surprising expression:

```text
flag OR note = 'keep'
```

For `(NULL, 'drop')`, the result is UNKNOWN OR FALSE = UNKNOWN and the row is
discarded. For `(NULL, 'keep')`, it is UNKNOWN OR TRUE = TRUE. For
`(TRUE, NULL)`, it is TRUE OR UNKNOWN = TRUE.

Use `IS NULL`, not `= NULL`, to test nullness. The parser creates
`IsNullExpr`, and the binder creates `BoundIsNull` with a non-null BOOLEAN
result.

## The narrow widening rule

The scalar set in `src/minipostgres/types.py::DataType` is `INT64`,
`FLOAT64`, `BOOLEAN`, and `TEXT`. `infer_type()` checks `bool` before `int`
because Python booleans subclass integers. `validate_int64()` rejects values
outside signed 64-bit bounds.

`Binder._numeric_pair()` implements the only implicit non-NULL widening: if
either numeric operand is FLOAT64, it wraps an INT64 operand in `BoundCast` to
FLOAT64. Otherwise the result stays INT64. `_comparable_pair()` also uses this
rule for numeric comparisons and gives an untyped NULL the other operand's
type. There is no automatic TEXT-to-number or BOOLEAN-to-INT conversion.

At runtime, `widen_numeric_pair()` and `compare_values()` in `types.py`
preserve the same contract for scalar helpers. Integer arithmetic remains in
the signed-64 domain; the expression evaluator checks overflow rather than
silently adopting Python's unbounded integers.

## Experiment: inspect all three stages

Run:

```bash
uv run python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres import Database
from minipostgres.sql.lexer import lex
from minipostgres.sql.parser import parse

sql = "SELECT id + 0.5 AS widened FROM items WHERE flag OR note = 'keep'"
print([token.kind.name for token in lex(sql)])
print(type(parse(sql)).__name__)
with TemporaryDirectory() as root, Database.open(root) as db:
    db.execute("CREATE TABLE items (id INT, flag BOOLEAN, note TEXT)")
    db.execute(
        "INSERT INTO items VALUES "
        "(1, NULL, 'drop'), (2, NULL, 'keep'), (3, TRUE, NULL)"
    )
    result = db.execute(sql + " ORDER BY id")
    print(result.columns)
    print(result.rows)
PY
```

Observed output:

```text
['SELECT', 'IDENT', 'PLUS', 'FLOAT', 'AS', 'IDENT', 'FROM', 'IDENT', 'WHERE', 'IDENT', 'OR', 'IDENT', 'EQ', 'STRING', 'EOF']
SelectStmt
('widened',)
((2.5,), (3.5,))
```

The token stream retains syntax categories. The parser knows the statement
shape but needs no catalog. During database execution, the binder resolves
`id`, `flag`, and `note`; inserts a cast for `id + 0.5`; and types the
predicate as nullable BOOLEAN. Three-valued evaluation removes row 1 and keeps
rows 2 and 3. The float outputs prove widening happened.

No socket is used, so this experiment is fully verified in the repository
runtime.

## Compared with PostgreSQL

PostgreSQL's nearby owners include `src/backend/parser/scan.l`, `gram.y`,
`analyze.c`, and the `parse_*.c` analysis modules. It also separates a raw
parse tree from a catalog-aware analyzed `Query`. That boundary is the
directionally faithful part.

The scale differs sharply. PostgreSQL resolves schemas, search paths,
overloads, collations, domains, polymorphism, coercion categories, privileges,
CTEs, subqueries, and much more. MiniPostgres has a handwritten parser, four
types, a fixed aggregate set, and simple widening. See the query-engine section
of [Differences from PostgreSQL](../differences.md) and stop 1 of the
[mapping](../postgresql-mapping.md). The `query_path` row in the
[behavior matrix](../behavior-matrix.md) is the executable evidence anchor;
it does not imply grammar parity.

## Exercises

### 1. Understanding: precedence

Sketch the AST shape for `NOT a = 1 OR b + 2 * 3 > 8`. Which parser functions
establish that shape?

??? note "Reference answer"

    The root is `OR`. Its left child is `NOT` over `a = 1`. Its right child is
    `>` with `b + (2 * 3)` on the left and `8` on the right. `_or`, `_not`,
    `_comparison`, `_additive`, and `_multiplicative` establish that nesting.

### 2. Understanding: UNKNOWN

Evaluate `NULL = 1 OR FALSE`, `NULL = 1 AND FALSE`, and
`NOT (NULL = 1)`.

??? note "Reference answer"

    They are UNKNOWN, FALSE, and UNKNOWN. Comparisons with NULL yield UNKNOWN;
    UNKNOWN OR FALSE remains UNKNOWN, FALSE dominates AND, and NOT preserves
    UNKNOWN.

### 3. Hands-on: add `--` line comments

Extend the lexer so `--` starts a comment that runs to the newline or EOF.
A single `-` must remain a `MINUS` token.

Acceptance:

- add the behavior in `src/minipostgres/sql/lexer.py`;
- add a unit test covering an inline comment, a whole-line comment, and the
  line/column positions of tokens after the newline; and
- run `uv run pytest -q tests/unit/sql/test_lexer.py` and get a green result.

??? note "Reference answer"

    Detect the two-character opener before `_symbol()` can emit the first
    minus, then advance to—but not through—the newline. The existing whitespace
    branch will consume that newline and update the position:

    ```diff
             if character.isspace():
                 self._advance()
                 continue
    +        if character == "-" and self._peek(1) == "-":
    +            self._line_comment()
    +            continue
             line, column = self._line, self._column
    @@
    +    def _line_comment(self) -> None:
    +        while not self._at_end and self._peek() != "\n":
    +            self._advance()
    ```

    A focused test is:

    ```python
    def test_lexer_skips_line_comments_and_preserves_positions() -> None:
        tokens = lex("SELECT 1 -- inline\n-- whole line\nFROM users")

        assert [token.kind for token in tokens] == [
            TokenKind.SELECT,
            TokenKind.INTEGER,
            TokenKind.FROM,
            TokenKind.IDENT,
            TokenKind.EOF,
        ]
        assert [(token.line, token.column) for token in tokens] == [
            (1, 1),
            (1, 8),
            (3, 1),
            (3, 6),
            (3, 11),
        ]
    ```

### 4. Hands-on: add a binder rejection test

Without changing implementation, write a test asserting that
`SELECT missing FROM users` raises `BindError`.

Acceptance:

- create the table first;
- assert the exception type, not its entire message; and
- show that `SELECT id FROM users` still binds and executes afterward.

??? note "Reference answer"

    Use `Database.open(tmp_path)`, execute `CREATE TABLE users (id INT)`, then
    wrap the missing-column statement in `pytest.raises(BindError)`. Finally
    assert the valid query returns an empty row tuple. Because the invalid
    statement is implicit, its aborted transaction does not poison the default
    session.

## Summary

The front end deliberately has three owners: `lex()` turns characters into
positioned tokens, `parse()` turns tokens into catalog-free syntax, and
`Binder.bind()` assigns stable identities, types, and contextual legality.
Three-valued logic and one narrow INT64-to-FLOAT64 widening are semantic
contracts, not parser tricks. Chapter 3 follows the bound query downward to
the fixed pages and buffer frames that hold its rows.
