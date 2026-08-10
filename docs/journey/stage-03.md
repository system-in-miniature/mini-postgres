# Stage 03 · Frozen SQL lexer

### Goal

Build frozen sql lexer and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/minipostgres/sql/__init__.py`
    - `src/minipostgres/sql/lexer.py`
    - `src/minipostgres/sql/tokens.py`
    - `tests/property/test_lexer_literals.py`
    - `tests/unit/sql/test_lexer.py`

### The problem at this point

Raw SQL must become bounded tokens with explicit keyword, literal, identifier, and error rules.

### Test contract

#### See the failure first

The focused tests force frozen sql lexer through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/property/test_lexer_literals.py"
    ```diff
    diff --git a/tests/property/test_lexer_literals.py b/tests/property/test_lexer_literals.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..7523b5fae254a1aaa65c7731dd3857243b322287
    --- /dev/null
    +++ b/tests/property/test_lexer_literals.py
    @@ -0,0 +1,36 @@
    +from __future__ import annotations
    +
    +from hypothesis import given
    +from hypothesis import strategies as st
    +
    +from minipostgres.sql.lexer import lex
    +from minipostgres.sql.tokens import TokenKind
    +
    +
    +@given(
    +    st.text(
    +        alphabet=st.characters(
    +            blacklist_categories=("Cs",),
    +            blacklist_characters="'\x00",
    +        )
    +    )
    +)
    +def test_quoted_string_round_trips(value: str) -> None:
    +    escaped = value.replace("'", "''")
    +    token = lex(f"'{escaped}'")[0]
    +
    +    assert token.kind is TokenKind.STRING
    +    assert token.value == value
    +
    +
    +@given(st.integers(min_value=-(2**63), max_value=2**63 - 1))
    +def test_integer_literal_round_trips_magnitude(value: int) -> None:
    +    tokens = lex(str(value))
    +
    +    if value < 0:
    +        assert tokens[0].kind is TokenKind.MINUS
    +        assert tokens[1].value == abs(value)
    +    else:
    +        assert tokens[0].kind is TokenKind.INTEGER
    +        assert tokens[0].value == value
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force frozen sql lexer through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert token.kind is TokenKind.STRING
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/sql/test_lexer.py"
    ```diff
    diff --git a/tests/unit/sql/test_lexer.py b/tests/unit/sql/test_lexer.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..842fab01fc65cab9360eba4739201f6d9284adff
    --- /dev/null
    +++ b/tests/unit/sql/test_lexer.py
    @@ -0,0 +1,79 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.errors import SqlSyntaxError
    +from minipostgres.sql.lexer import lex
    +from minipostgres.sql.tokens import TokenKind
    +
    +
    +def test_lexer_handles_keywords_identifiers_numbers_and_sql_strings() -> None:
    +    tokens = lex("SELECT name, 1.5 FROM users WHERE note = 'it''s ok';")
    +
    +    assert [token.kind for token in tokens] == [
    +        TokenKind.SELECT,
    +        TokenKind.IDENT,
    +        TokenKind.COMMA,
    +        TokenKind.FLOAT,
    +        TokenKind.FROM,
    +        TokenKind.IDENT,
    +        TokenKind.WHERE,
    +        TokenKind.IDENT,
    +        TokenKind.EQ,
    +        TokenKind.STRING,
    +        TokenKind.SEMICOLON,
    +        TokenKind.EOF,
    +    ]
    +    assert tokens[3].value == 1.5
    +    assert tokens[9].value == "it's ok"
    +
    +
    +def test_lexer_is_case_insensitive_for_keywords_but_preserves_identifiers() -> None:
    +    tokens = lex("select MixedCase from Users")
    +
    +    assert tokens[0].kind is TokenKind.SELECT
    +    assert tokens[1].value == "MixedCase"
    +    assert tokens[3].value == "Users"
    +
    +
    +def test_lexer_recognizes_frozen_operators_and_punctuation() -> None:
    +    tokens = lex("a<=1 AND b<>2 OR c!=3, d.* + -4 / (5)")
    +
    +    assert [token.kind for token in tokens] == [
    +        TokenKind.IDENT,
    +        TokenKind.LTE,
    +        TokenKind.INTEGER,
    +        TokenKind.AND,
    +        TokenKind.IDENT,
    +        TokenKind.NEQ,
    +        TokenKind.INTEGER,
    +        TokenKind.OR,
    +        TokenKind.IDENT,
    +        TokenKind.NEQ,
    +        TokenKind.INTEGER,
    +        TokenKind.COMMA,
    +        TokenKind.IDENT,
    +        TokenKind.DOT,
    +        TokenKind.STAR,
    +        TokenKind.PLUS,
    +        TokenKind.MINUS,
    +        TokenKind.INTEGER,
    +        TokenKind.SLASH,
    +        TokenKind.LPAREN,
    +        TokenKind.INTEGER,
    +        TokenKind.RPAREN,
    +        TokenKind.EOF,
    +    ]
    +
    +
    +def test_lexer_tracks_line_and_column_for_errors() -> None:
    +    with pytest.raises(SqlSyntaxError, match=r"line 2, column 3.*unexpected"):
    +        lex("SELECT\n  @")
    +
    +
    +def test_lexer_rejects_unterminated_string_and_nul() -> None:
    +    with pytest.raises(SqlSyntaxError, match="unterminated string"):
    +        lex("SELECT 'broken")
    +    with pytest.raises(SqlSyntaxError, match="NUL"):
    +        lex("SELECT \x00")
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force frozen sql lexer through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert token.kind is TokenKind.STRING
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is frozen sql lexer. Raw SQL must become bounded tokens with explicit keyword, literal, identifier, and error rules.

### Why this mechanism is necessary

Raw SQL must become bounded tokens with explicit keyword, literal, identifier, and error rules. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

The lexer consumes every character or raises at its exact unsupported boundary.

### Mechanism blocks

#### Frozen SQL lexer mechanism

The lexer consumes every character or raises at its exact unsupported boundary.

??? note "File diff: src/minipostgres/sql/lexer.py"
    ```diff
    diff --git a/src/minipostgres/sql/lexer.py b/src/minipostgres/sql/lexer.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..e219724872e45f35548fe412f377eada9088cc17
    --- /dev/null
    +++ b/src/minipostgres/sql/lexer.py
    @@ -0,0 +1,164 @@
    +"""Position-aware lexer for the frozen SQL subset."""
    +
    +from __future__ import annotations
    +
    +import math
    +from typing import NoReturn
    +
    +from minipostgres.errors import SqlSyntaxError
    +from minipostgres.sql.tokens import KEYWORDS, Token, TokenKind
    +
    +
    +class _Lexer:
    +    def __init__(self, source: str) -> None:
    +        self._source = source
    +        self._offset = 0
    +        self._line = 1
    +        self._column = 1
    +
    +    def scan(self) -> tuple[Token, ...]:
    +        tokens: list[Token] = []
    +        while not self._at_end:
    +            character = self._peek()
    +            if character == "\x00":
    +                self._fail("NUL is not allowed in SQL text")
    +            if character.isspace():
    +                self._advance()
    +                continue
    +            line, column = self._line, self._column
    +            if character.isalpha() or character == "_":
    +                tokens.append(self._identifier(line, column))
    +            elif character.isdigit():
    +                tokens.append(self._number(line, column))
    +            elif character == "'":
    +                tokens.append(self._string(line, column))
    +            else:
    +                tokens.append(self._symbol(line, column))
    +        tokens.append(Token(TokenKind.EOF, "", None, self._line, self._column))
    +        return tuple(tokens)
    +
    +    @property
    +    def _at_end(self) -> bool:
    +        return self._offset >= len(self._source)
    +
    +    def _peek(self, distance: int = 0) -> str:
    +        offset = self._offset + distance
    +        return "" if offset >= len(self._source) else self._source[offset]
    +
    +    def _advance(self) -> str:
    +        character = self._source[self._offset]
    +        self._offset += 1
    +        if character == "\n":
    +            self._line += 1
    +            self._column = 1
    +        else:
    +            self._column += 1
    +        return character
    +
    +    def _identifier(self, line: int, column: int) -> Token:
    +        start = self._offset
    +        while self._peek().isalnum() or self._peek() == "_":
    +            self._advance()
    +        lexeme = self._source[start : self._offset]
    +        kind = KEYWORDS.get(lexeme.upper(), TokenKind.IDENT)
    +        value = lexeme if kind is TokenKind.IDENT else None
    +        return Token(kind, lexeme, value, line, column)
    +
    +    def _number(self, line: int, column: int) -> Token:
    +        start = self._offset
    +        while self._peek().isdigit():
    +            self._advance()
    +        kind = TokenKind.INTEGER
    +        if self._peek() == "." and self._peek(1).isdigit():
    +            kind = TokenKind.FLOAT
    +            self._advance()
    +            while self._peek().isdigit():
    +                self._advance()
    +        lexeme = self._source[start : self._offset]
    +        if kind is TokenKind.INTEGER:
    +            value: int | float = int(lexeme)
    +        else:
    +            value = float(lexeme)
    +            if not math.isfinite(value):
    +                self._fail("floating-point literal is out of range", line, column)
    +        return Token(kind, lexeme, value, line, column)
    +
    +    def _string(self, line: int, column: int) -> Token:
    +        start = self._offset
    +        self._advance()
    +        decoded: list[str] = []
    +        while not self._at_end:
    +            character = self._advance()
    +            if character == "\x00":
    +                self._fail("NUL is not allowed in SQL text")
    +            if character != "'":
    +                decoded.append(character)
    +                continue
    +            if self._peek() == "'":
    +                self._advance()
    +                decoded.append("'")
    +                continue
    +            lexeme = self._source[start : self._offset]
    +            return Token(TokenKind.STRING, lexeme, "".join(decoded), line, column)
    +        self._fail("unterminated string literal", line, column)
    +
    +    def _symbol(self, line: int, column: int) -> Token:
    +        start = self._offset
    +        character = self._advance()
    +        single = {
    +            ",": TokenKind.COMMA,
    +            ".": TokenKind.DOT,
    +            ";": TokenKind.SEMICOLON,
    +            "(": TokenKind.LPAREN,
    +            ")": TokenKind.RPAREN,
    +            "*": TokenKind.STAR,
    +            "+": TokenKind.PLUS,
    +            "-": TokenKind.MINUS,
    +            "/": TokenKind.SLASH,
    +            "=": TokenKind.EQ,
    +        }
    +        if character in single:
    +            return Token(single[character], character, None, line, column)
    +        if character == "<":
    +            if self._peek() == "=":
    +                self._advance()
    +                kind = TokenKind.LTE
    +            elif self._peek() == ">":
    +                self._advance()
    +                kind = TokenKind.NEQ
    +            else:
    +                kind = TokenKind.LT
    +        elif character == ">":
    +            if self._peek() == "=":
    +                self._advance()
    +                kind = TokenKind.GTE
    +            else:
    +                kind = TokenKind.GT
    +        elif character == "!" and self._peek() == "=":
    +            self._advance()
    +            kind = TokenKind.NEQ
    +        else:
    +            self._fail(f"unexpected character {character!r}", line, column)
    +        return Token(
    +            kind,
    +            self._source[start : self._offset],
    +            None,
    +            line,
    +            column,
    +        )
    +
    +    def _fail(
    +        self,
    +        message: str,
    +        line: int | None = None,
    +        column: int | None = None,
    +    ) -> NoReturn:
    +        raise SqlSyntaxError(
    +            f"line {line or self._line}, column {column or self._column}: {message}"
    +        )
    +
    +
    +def lex(source: str) -> tuple[Token, ...]:
    +    """Tokenize one SQL string."""
    +
    +    return _Lexer(source).scan()
    ```

??? note "File diff: src/minipostgres/sql/tokens.py"
    ```diff
    diff --git a/src/minipostgres/sql/tokens.py b/src/minipostgres/sql/tokens.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..159c7574bcba8244b8b38aa0a154afc89bf56990
    --- /dev/null
    +++ b/src/minipostgres/sql/tokens.py
    @@ -0,0 +1,147 @@
    +"""Tokens for the frozen MiniPostgres SQL grammar."""
    +
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +from enum import Enum, auto
    +
    +from minipostgres.types import Scalar
    +
    +
    +class TokenKind(Enum):
    +    """Lexical categories; keywords have distinct kinds."""
    +
    +    IDENT = auto()
    +    INTEGER = auto()
    +    FLOAT = auto()
    +    STRING = auto()
    +
    +    CREATE = auto()
    +    TABLE = auto()
    +    INDEX = auto()
    +    UNIQUE = auto()
    +    ON = auto()
    +    INSERT = auto()
    +    INTO = auto()
    +    VALUES = auto()
    +    SELECT = auto()
    +    UPDATE = auto()
    +    SET = auto()
    +    DELETE = auto()
    +    FROM = auto()
    +    WHERE = auto()
    +    INNER = auto()
    +    JOIN = auto()
    +    AS = auto()
    +    GROUP = auto()
    +    BY = auto()
    +    ORDER = auto()
    +    ASC = auto()
    +    DESC = auto()
    +    NULLS = auto()
    +    FIRST = auto()
    +    LAST = auto()
    +    LIMIT = auto()
    +    EXPLAIN = auto()
    +    ANALYZE = auto()
    +    VACUUM = auto()
    +    BEGIN = auto()
    +    COMMIT = auto()
    +    ROLLBACK = auto()
    +
    +    AND = auto()
    +    OR = auto()
    +    NOT = auto()
    +    IS = auto()
    +    NULL = auto()
    +    TRUE = auto()
    +    FALSE = auto()
    +    PRIMARY = auto()
    +    KEY = auto()
    +
    +    INT = auto()
    +    INTEGER_TYPE = auto()
    +    BIGINT = auto()
    +    FLOAT_TYPE = auto()
    +    BOOLEAN = auto()
    +    TEXT = auto()
    +
    +    COMMA = auto()
    +    DOT = auto()
    +    SEMICOLON = auto()
    +    LPAREN = auto()
    +    RPAREN = auto()
    +    STAR = auto()
    +    PLUS = auto()
    +    MINUS = auto()
    +    SLASH = auto()
    +    EQ = auto()
    +    NEQ = auto()
    +    LT = auto()
    +    LTE = auto()
    +    GT = auto()
    +    GTE = auto()
    +    EOF = auto()
    +
    +
    +KEYWORDS: dict[str, TokenKind] = {
    +    "ANALYZE": TokenKind.ANALYZE,
    +    "AND": TokenKind.AND,
    +    "AS": TokenKind.AS,
    +    "ASC": TokenKind.ASC,
    +    "BEGIN": TokenKind.BEGIN,
    +    "BIGINT": TokenKind.BIGINT,
    +    "BOOLEAN": TokenKind.BOOLEAN,
    +    "BY": TokenKind.BY,
    +    "COMMIT": TokenKind.COMMIT,
    +    "CREATE": TokenKind.CREATE,
    +    "DELETE": TokenKind.DELETE,
    +    "DESC": TokenKind.DESC,
    +    "EXPLAIN": TokenKind.EXPLAIN,
    +    "FALSE": TokenKind.FALSE,
    +    "FIRST": TokenKind.FIRST,
    +    "FLOAT": TokenKind.FLOAT_TYPE,
    +    "FROM": TokenKind.FROM,
    +    "GROUP": TokenKind.GROUP,
    +    "INDEX": TokenKind.INDEX,
    +    "INNER": TokenKind.INNER,
    +    "INSERT": TokenKind.INSERT,
    +    "INT": TokenKind.INT,
    +    "INTEGER": TokenKind.INTEGER_TYPE,
    +    "INTO": TokenKind.INTO,
    +    "IS": TokenKind.IS,
    +    "JOIN": TokenKind.JOIN,
    +    "KEY": TokenKind.KEY,
    +    "LAST": TokenKind.LAST,
    +    "LIMIT": TokenKind.LIMIT,
    +    "NOT": TokenKind.NOT,
    +    "NULL": TokenKind.NULL,
    +    "NULLS": TokenKind.NULLS,
    +    "ON": TokenKind.ON,
    +    "OR": TokenKind.OR,
    +    "ORDER": TokenKind.ORDER,
    +    "PRIMARY": TokenKind.PRIMARY,
    +    "ROLLBACK": TokenKind.ROLLBACK,
    +    "SELECT": TokenKind.SELECT,
    +    "SET": TokenKind.SET,
    +    "TABLE": TokenKind.TABLE,
    +    "TEXT": TokenKind.TEXT,
    +    "TRUE": TokenKind.TRUE,
    +    "UNIQUE": TokenKind.UNIQUE,
    +    "UPDATE": TokenKind.UPDATE,
    +    "VACUUM": TokenKind.VACUUM,
    +    "VALUES": TokenKind.VALUES,
    +    "WHERE": TokenKind.WHERE,
    +}
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class Token:
    +    """One token with a decoded literal and source position."""
    +
    +    kind: TokenKind
    +    lexeme: str
    +    value: Scalar
    +    line: int
    +    column: int
    +
    ```

**What it is and why it appears**

The central mechanism is frozen sql lexer. Raw SQL must become bounded tokens with explicit keyword, literal, identifier, and error rules.

**Runtime role**

The lexer consumes every character or raises at its exact unsupported boundary.

**Statement understanding**

The durable boundary is this: the lexer consumes every character or raises at its exact unsupported boundary.

#### Package, fixture, and project support

Keep exports, test corpora, dependencies, and the runtime environment reproducible.

??? note "Supporting file diffs (1 file)"
    **`src/minipostgres/sql/__init__.py`**

    ```diff
    diff --git a/src/minipostgres/sql/__init__.py b/src/minipostgres/sql/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..45917cf18387b36336241ad7958ca73c95a0cbfc
    --- /dev/null
    +++ b/src/minipostgres/sql/__init__.py
    @@ -0,0 +1,7 @@
    +"""SQL front-end modules."""
    +
    +from minipostgres.sql.lexer import lex
    +from minipostgres.sql.tokens import Token, TokenKind
    +
    +__all__ = ["Token", "TokenKind", "lex"]
    +
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/03-sql-lexer/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: the lexer consumes every character or raises at its exact unsupported boundary.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/02-sql-frontend.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/03-sql-lexer/stage.patch)
