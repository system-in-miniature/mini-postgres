"""Tokens for the frozen MiniPostgres SQL grammar."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from minipostgres.types import Scalar


class TokenKind(Enum):
    """Lexical categories; keywords have distinct kinds."""

    IDENT = auto()
    INTEGER = auto()
    FLOAT = auto()
    STRING = auto()

    CREATE = auto()
    TABLE = auto()
    INDEX = auto()
    UNIQUE = auto()
    ON = auto()
    INSERT = auto()
    INTO = auto()
    VALUES = auto()
    SELECT = auto()
    UPDATE = auto()
    SET = auto()
    DELETE = auto()
    FROM = auto()
    WHERE = auto()
    INNER = auto()
    JOIN = auto()
    AS = auto()
    GROUP = auto()
    BY = auto()
    ORDER = auto()
    ASC = auto()
    DESC = auto()
    NULLS = auto()
    FIRST = auto()
    LAST = auto()
    LIMIT = auto()
    EXPLAIN = auto()
    ANALYZE = auto()
    VACUUM = auto()
    BEGIN = auto()
    COMMIT = auto()
    ROLLBACK = auto()

    AND = auto()
    OR = auto()
    NOT = auto()
    IS = auto()
    NULL = auto()
    TRUE = auto()
    FALSE = auto()
    PRIMARY = auto()
    KEY = auto()

    INT = auto()
    INTEGER_TYPE = auto()
    BIGINT = auto()
    FLOAT_TYPE = auto()
    BOOLEAN = auto()
    TEXT = auto()

    COMMA = auto()
    DOT = auto()
    SEMICOLON = auto()
    LPAREN = auto()
    RPAREN = auto()
    STAR = auto()
    PLUS = auto()
    MINUS = auto()
    SLASH = auto()
    EQ = auto()
    NEQ = auto()
    LT = auto()
    LTE = auto()
    GT = auto()
    GTE = auto()
    EOF = auto()


KEYWORDS: dict[str, TokenKind] = {
    "ANALYZE": TokenKind.ANALYZE,
    "AND": TokenKind.AND,
    "AS": TokenKind.AS,
    "ASC": TokenKind.ASC,
    "BEGIN": TokenKind.BEGIN,
    "BIGINT": TokenKind.BIGINT,
    "BOOLEAN": TokenKind.BOOLEAN,
    "BY": TokenKind.BY,
    "COMMIT": TokenKind.COMMIT,
    "CREATE": TokenKind.CREATE,
    "DELETE": TokenKind.DELETE,
    "DESC": TokenKind.DESC,
    "EXPLAIN": TokenKind.EXPLAIN,
    "FALSE": TokenKind.FALSE,
    "FIRST": TokenKind.FIRST,
    "FLOAT": TokenKind.FLOAT_TYPE,
    "FROM": TokenKind.FROM,
    "GROUP": TokenKind.GROUP,
    "INDEX": TokenKind.INDEX,
    "INNER": TokenKind.INNER,
    "INSERT": TokenKind.INSERT,
    "INT": TokenKind.INT,
    "INTEGER": TokenKind.INTEGER_TYPE,
    "INTO": TokenKind.INTO,
    "IS": TokenKind.IS,
    "JOIN": TokenKind.JOIN,
    "KEY": TokenKind.KEY,
    "LAST": TokenKind.LAST,
    "LIMIT": TokenKind.LIMIT,
    "NOT": TokenKind.NOT,
    "NULL": TokenKind.NULL,
    "NULLS": TokenKind.NULLS,
    "ON": TokenKind.ON,
    "OR": TokenKind.OR,
    "ORDER": TokenKind.ORDER,
    "PRIMARY": TokenKind.PRIMARY,
    "ROLLBACK": TokenKind.ROLLBACK,
    "SELECT": TokenKind.SELECT,
    "SET": TokenKind.SET,
    "TABLE": TokenKind.TABLE,
    "TEXT": TokenKind.TEXT,
    "TRUE": TokenKind.TRUE,
    "UNIQUE": TokenKind.UNIQUE,
    "UPDATE": TokenKind.UPDATE,
    "VACUUM": TokenKind.VACUUM,
    "VALUES": TokenKind.VALUES,
    "WHERE": TokenKind.WHERE,
}


@dataclass(frozen=True, slots=True)
class Token:
    """One token with a decoded literal and source position."""

    kind: TokenKind
    lexeme: str
    value: Scalar
    line: int
    column: int

