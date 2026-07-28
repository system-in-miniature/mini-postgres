from __future__ import annotations

import pytest

from minipostgres.errors import SqlSyntaxError
from minipostgres.sql.lexer import lex
from minipostgres.sql.tokens import TokenKind


def test_lexer_handles_keywords_identifiers_numbers_and_sql_strings() -> None:
    tokens = lex("SELECT name, 1.5 FROM users WHERE note = 'it''s ok';")

    assert [token.kind for token in tokens] == [
        TokenKind.SELECT,
        TokenKind.IDENT,
        TokenKind.COMMA,
        TokenKind.FLOAT,
        TokenKind.FROM,
        TokenKind.IDENT,
        TokenKind.WHERE,
        TokenKind.IDENT,
        TokenKind.EQ,
        TokenKind.STRING,
        TokenKind.SEMICOLON,
        TokenKind.EOF,
    ]
    assert tokens[3].value == 1.5
    assert tokens[9].value == "it's ok"


def test_lexer_is_case_insensitive_for_keywords_but_preserves_identifiers() -> None:
    tokens = lex("select MixedCase from Users")

    assert tokens[0].kind is TokenKind.SELECT
    assert tokens[1].value == "MixedCase"
    assert tokens[3].value == "Users"


def test_lexer_recognizes_frozen_operators_and_punctuation() -> None:
    tokens = lex("a<=1 AND b<>2 OR c!=3, d.* + -4 / (5)")

    assert [token.kind for token in tokens] == [
        TokenKind.IDENT,
        TokenKind.LTE,
        TokenKind.INTEGER,
        TokenKind.AND,
        TokenKind.IDENT,
        TokenKind.NEQ,
        TokenKind.INTEGER,
        TokenKind.OR,
        TokenKind.IDENT,
        TokenKind.NEQ,
        TokenKind.INTEGER,
        TokenKind.COMMA,
        TokenKind.IDENT,
        TokenKind.DOT,
        TokenKind.STAR,
        TokenKind.PLUS,
        TokenKind.MINUS,
        TokenKind.INTEGER,
        TokenKind.SLASH,
        TokenKind.LPAREN,
        TokenKind.INTEGER,
        TokenKind.RPAREN,
        TokenKind.EOF,
    ]


def test_lexer_tracks_line_and_column_for_errors() -> None:
    with pytest.raises(SqlSyntaxError, match=r"line 2, column 3.*unexpected"):
        lex("SELECT\n  @")


def test_lexer_rejects_unterminated_string_and_nul() -> None:
    with pytest.raises(SqlSyntaxError, match="unterminated string"):
        lex("SELECT 'broken")
    with pytest.raises(SqlSyntaxError, match="NUL"):
        lex("SELECT \x00")

