"""Execution context and lifecycle-safe Volcano executor base classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import TracebackType

from minipostgres.executor.memory import TableAccess
from minipostgres.row import ExecutionRow


@dataclass(frozen=True, slots=True)
class OutputSlot:
    """Positional value emitted by Values or Project."""

    index: int


class ExecutionContext:
    """Runtime dependencies shared by one executor tree."""

    def __init__(self, tables: dict[int, TableAccess]) -> None:
        self._tables = dict(tables)

    def table(self, table_id: int) -> TableAccess:
        try:
            return self._tables[table_id]
        except KeyError as error:
            raise KeyError(
                f"no table access registered for table {table_id}"
            ) from error

    def register_table(self, table: TableAccess) -> None:
        if table.table_id in self._tables:
            raise ValueError(f"table access already registered: {table.table_id}")
        self._tables[table.table_id] = table


class Executor(ABC):
    """One demand-pull operator with an idempotent lifecycle."""

    def __init__(self) -> None:
        self._opened = False
        self._closed = False

    @property
    def opened(self) -> bool:
        return self._opened

    @property
    def closed(self) -> bool:
        return self._closed

    def open(self) -> None:
        if self._opened:
            return
        if self._closed:
            raise RuntimeError("cannot reopen a closed executor")
        try:
            self._open()
        except BaseException:
            try:
                self._close()
            finally:
                self._closed = True
            raise
        self._opened = True

    def next(self) -> ExecutionRow | None:
        if not self._opened or self._closed:
            raise RuntimeError("executor is not open")
        return self._next()

    def close(self) -> None:
        if self._closed:
            return
        try:
            if self._opened:
                self._close()
        finally:
            self._closed = True

    def __enter__(self) -> Executor:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _open(self) -> None:
        """Optional subclass hook."""
        return None

    @abstractmethod
    def _next(self) -> ExecutionRow | None:
        raise NotImplementedError

    def _close(self) -> None:
        """Optional subclass hook."""
        return None


def collect(executor: Executor) -> list[ExecutionRow]:
    """Materialize an executor while guaranteeing closure."""

    rows: list[ExecutionRow] = []
    with executor:
        while (row := executor.next()) is not None:
            rows.append(row)
    return rows
