"""Synchronous in-process MiniPostgres query orchestration."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from types import TracebackType

from minipostgres.catalog.catalog import Catalog
from minipostgres.catalog.model import Column
from minipostgres.errors import BindError, DatabaseClosed
from minipostgres.executor.base import ExecutionContext, OutputSlot, collect
from minipostgres.executor.factory import build_executor
from minipostgres.executor.memory import MemoryTable
from minipostgres.planner.physical import PlanExplanation, explain_plan
from minipostgres.planner.planner import Planner
from minipostgres.sql.binder import Binder
from minipostgres.sql.bound import (
    BoundCreateTable,
    BoundDelete,
    BoundExplain,
    BoundInsert,
    BoundSelect,
    BoundStatement,
    BoundUpdate,
)
from minipostgres.sql.parser import parse
from minipostgres.types import DataType, Scalar


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Immutable public result for one statement."""

    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Scalar, ...], ...] = ()
    command_tag: str = ""
    plan: PlanExplanation | None = None


class Database:
    """Own the Phase A catalog, access methods, and query pipeline."""

    def __init__(self, root: Path, catalog: Catalog) -> None:
        self._root = root
        self._catalog = catalog
        self._context = ExecutionContext(
            {
                table.table_id: MemoryTable(table.table_id, table.schema)
                for table in catalog.tables()
            }
        )
        self._planner = Planner()
        self._lock = threading.RLock()
        self._closed = False

    @classmethod
    def open(cls, root: str | Path) -> Database:
        root_path = Path(root)
        return cls(root_path, Catalog.open(root_path))

    @property
    def catalog(self) -> Catalog:
        self._ensure_open()
        return self._catalog

    def execute(self, sql: str) -> QueryResult:
        with self._lock:
            self._ensure_open()
            syntax = parse(sql)
            bound = Binder(self._catalog).bind(syntax)
            if isinstance(bound, BoundCreateTable):
                return self._create_table(bound)
            if isinstance(bound, BoundExplain):
                return self._explain(bound)
            if isinstance(bound, (BoundSelect, BoundInsert, BoundUpdate, BoundDelete)):
                return self._execute_relational(bound)
            raise BindError(
                f"{type(syntax).__name__} is reserved for a later project phase"
            )

    def _explain(self, statement: BoundExplain) -> QueryResult:
        logical = self._planner.logical(statement.statement)
        physical = self._planner.physical(logical)
        if not statement.analyze:
            return QueryResult(
                command_tag="EXPLAIN",
                plan=explain_plan(physical),
            )
        started = perf_counter()
        rows = collect(build_executor(physical, self._context))
        elapsed_ms = (perf_counter() - started) * 1_000
        return QueryResult(
            command_tag="EXPLAIN ANALYZE",
            plan=explain_plan(
                physical,
                actual_rows=len(rows),
                elapsed_ms=elapsed_ms,
            ),
        )

    def _create_table(self, statement: BoundCreateTable) -> QueryResult:
        columns = tuple(
            Column(
                column.name,
                DataType[column.type_name],
                nullable=column.nullable,
                primary_key=column.primary_key,
                unique=column.unique,
            )
            for column in statement.columns
        )
        metadata = self._catalog.create_table(statement.name, columns)
        self._context.register_table(MemoryTable(metadata.table_id, metadata.schema))
        return QueryResult(command_tag="CREATE TABLE")

    def _execute_relational(
        self,
        statement: BoundStatement,
    ) -> QueryResult:
        logical = self._planner.logical(statement)
        physical = self._planner.physical(logical)
        rows = collect(build_executor(physical, self._context))
        if isinstance(statement, BoundSelect):
            materialized = tuple(
                tuple(
                    row.computed[OutputSlot(index)]
                    for index in range(len(statement.items))
                )
                for row in rows
            )
            return QueryResult(
                columns=tuple(item.name for item in statement.items),
                rows=materialized,
                command_tag=f"SELECT {len(materialized)}",
            )
        affected = 0 if not rows else rows[0].computed[OutputSlot(0)]
        assert isinstance(affected, int)
        if isinstance(statement, BoundInsert):
            tag = f"INSERT 0 {affected}"
        elif isinstance(statement, BoundUpdate):
            tag = f"UPDATE {affected}"
        else:
            tag = f"DELETE {affected}"
        return QueryResult(command_tag=tag)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise DatabaseClosed("database is closed")

    def __enter__(self) -> Database:
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
