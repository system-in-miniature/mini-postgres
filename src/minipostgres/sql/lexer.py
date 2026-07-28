"""Position-aware lexer for the frozen SQL subset."""

from __future__ import annotations

import math
from typing import NoReturn

from minipostgres.errors import SqlSyntaxError
from minipostgres.sql.tokens import KEYWORDS, Token, TokenKind


class _Lexer:
    def __init__(self, source: str) -> None:
        self._source = source
        self._offset = 0
        self._line = 1
        self._column = 1

    def scan(self) -> tuple[Token, ...]:
        tokens: list[Token] = []
        while not self._at_end:
            character = self._peek()
            if character == "\x00":
                self._fail("NUL is not allowed in SQL text")
            if character.isspace():
                self._advance()
                continue
            line, column = self._line, self._column
            if character.isalpha() or character == "_":
                tokens.append(self._identifier(line, column))
            elif character.isdigit():
                tokens.append(self._number(line, column))
            elif character == "'":
                tokens.append(self._string(line, column))
            else:
                tokens.append(self._symbol(line, column))
        tokens.append(Token(TokenKind.EOF, "", None, self._line, self._column))
        return tuple(tokens)

    @property
    def _at_end(self) -> bool:
        return self._offset >= len(self._source)

    def _peek(self, distance: int = 0) -> str:
        offset = self._offset + distance
        return "" if offset >= len(self._source) else self._source[offset]

    def _advance(self) -> str:
        character = self._source[self._offset]
        self._offset += 1
        if character == "\n":
            self._line += 1
            self._column = 1
        else:
            self._column += 1
        return character

    def _identifier(self, line: int, column: int) -> Token:
        start = self._offset
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        lexeme = self._source[start : self._offset]
        kind = KEYWORDS.get(lexeme.upper(), TokenKind.IDENT)
        value = lexeme if kind is TokenKind.IDENT else None
        return Token(kind, lexeme, value, line, column)

    def _number(self, line: int, column: int) -> Token:
        start = self._offset
        while self._peek().isdigit():
            self._advance()
        kind = TokenKind.INTEGER
        if self._peek() == "." and self._peek(1).isdigit():
            kind = TokenKind.FLOAT
            self._advance()
            while self._peek().isdigit():
                self._advance()
        lexeme = self._source[start : self._offset]
        if kind is TokenKind.INTEGER:
            value: int | float = int(lexeme)
        else:
            value = float(lexeme)
            if not math.isfinite(value):
                self._fail("floating-point literal is out of range", line, column)
        return Token(kind, lexeme, value, line, column)

    def _string(self, line: int, column: int) -> Token:
        start = self._offset
        self._advance()
        decoded: list[str] = []
        while not self._at_end:
            character = self._advance()
            if character == "\x00":
                self._fail("NUL is not allowed in SQL text")
            if character != "'":
                decoded.append(character)
                continue
            if self._peek() == "'":
                self._advance()
                decoded.append("'")
                continue
            lexeme = self._source[start : self._offset]
            return Token(TokenKind.STRING, lexeme, "".join(decoded), line, column)
        self._fail("unterminated string literal", line, column)

    def _symbol(self, line: int, column: int) -> Token:
        start = self._offset
        character = self._advance()
        single = {
            ",": TokenKind.COMMA,
            ".": TokenKind.DOT,
            ";": TokenKind.SEMICOLON,
            "(": TokenKind.LPAREN,
            ")": TokenKind.RPAREN,
            "*": TokenKind.STAR,
            "+": TokenKind.PLUS,
            "-": TokenKind.MINUS,
            "/": TokenKind.SLASH,
            "=": TokenKind.EQ,
        }
        if character in single:
            return Token(single[character], character, None, line, column)
        if character == "<":
            if self._peek() == "=":
                self._advance()
                kind = TokenKind.LTE
            elif self._peek() == ">":
                self._advance()
                kind = TokenKind.NEQ
            else:
                kind = TokenKind.LT
        elif character == ">":
            if self._peek() == "=":
                self._advance()
                kind = TokenKind.GTE
            else:
                kind = TokenKind.GT
        elif character == "!" and self._peek() == "=":
            self._advance()
            kind = TokenKind.NEQ
        else:
            self._fail(f"unexpected character {character!r}", line, column)
        return Token(
            kind,
            self._source[start : self._offset],
            None,
            line,
            column,
        )

    def _fail(
        self,
        message: str,
        line: int | None = None,
        column: int | None = None,
    ) -> NoReturn:
        raise SqlSyntaxError(
            f"line {line or self._line}, column {column or self._column}: {message}"
        )


def lex(source: str) -> tuple[Token, ...]:
    """Tokenize one SQL string."""

    return _Lexer(source).scan()
