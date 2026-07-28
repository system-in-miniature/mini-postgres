"""Typed public errors raised by MiniPostgres."""

from __future__ import annotations


class MiniPostgresError(Exception):
    """Base class for errors intended to cross the public API."""


class SqlSyntaxError(MiniPostgresError):
    """SQL text is outside the accepted grammar."""


class BindError(MiniPostgresError):
    """A syntactically valid name or expression cannot be bound."""


class TypeMismatch(MiniPostgresError):
    """A scalar or expression has an incompatible SQL type."""


class NumericOverflow(MiniPostgresError):
    """An integer result is outside the signed INT64 range."""


class ConstraintViolation(MiniPostgresError):
    """A row violates an accepted schema constraint."""


class SerializationConflict(MiniPostgresError):
    """A concurrent write cannot be serialized at the selected isolation."""


class DeadlockDetected(MiniPostgresError):
    """The current transaction was selected as a deadlock victim."""


class TransactionAborted(MiniPostgresError):
    """The transaction is failed and must be rolled back."""


class RowTooLarge(MiniPostgresError):
    """A tuple cannot fit in one heap page."""


class CorruptPage(MiniPostgresError):
    """A page failed structural or checksum validation."""


class CorruptWal(MiniPostgresError):
    """A non-tail WAL record failed structural or checksum validation."""


class CatalogError(MiniPostgresError):
    """Catalog metadata is invalid or conflicts with existing metadata."""


class DatabaseClosed(MiniPostgresError):
    """An operation was attempted on a closed database."""

