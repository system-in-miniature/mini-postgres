# Stage 03 · 冻结 SQL 词法器

### 目标

实现冻结 SQL 词法器，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minipostgres/sql/__init__.py`
    - `src/minipostgres/sql/lexer.py`
    - `src/minipostgres/sql/tokens.py`
    - `tests/property/test_lexer_literals.py`
    - `tests/unit/sql/test_lexer.py`

### 当前遇到的问题

原始 SQL 必须按显式的关键字、字面量、标识符与错误规则变成有界 Token。

### 测试契约

#### 先看会坏在哪里

聚焦测试让冻结 SQL 词法器经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/property/test_lexer_literals.py"
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

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让冻结 SQL 词法器经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert token.kind is TokenKind.STRING
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/sql/test_lexer.py"
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

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让冻结 SQL 词法器经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert token.kind is TokenKind.STRING
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是冻结 SQL 词法器。原始 SQL 必须按显式的关键字、字面量、标识符与错误规则变成有界 Token。

### 为什么需要这个机制

原始 SQL 必须按显式的关键字、字面量、标识符与错误规则变成有界 Token。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Lexer 要么消费每个字符，要么在确切的不支持边界报错。

### 机制板块

#### 冻结 SQL 词法器机制

Lexer 要么消费每个字符，要么在确切的不支持边界报错。

??? note "文件差异：src/minipostgres/sql/lexer.py"
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

??? note "文件差异：src/minipostgres/sql/tokens.py"
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

**是什么，为什么现在需要**

核心机制是冻结 SQL 词法器。原始 SQL 必须按显式的关键字、字面量、标识符与错误规则变成有界 Token。

**在运行时做什么**

Lexer 要么消费每个字符，要么在确切的不支持边界报错。

**关键语句理解**

真正要守住的边界是：Lexer 要么消费每个字符，要么在确切的不支持边界报错。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（1 个文件）"
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


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/03-sql-lexer/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Lexer 要么消费每个字符，要么在确切的不支持边界报错。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 2 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/02-sql-frontend.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/03-sql-lexer/stage.patch)
