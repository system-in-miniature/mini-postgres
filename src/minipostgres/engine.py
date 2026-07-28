"""Synchronous in-process MiniPostgres query orchestration."""

from __future__ import annotations

import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from types import TracebackType

from minipostgres.catalog.catalog import Catalog
from minipostgres.catalog.model import Column, IndexMetadata, TableMetadata
from minipostgres.errors import BindError, ConstraintViolation, DatabaseClosed
from minipostgres.executor.base import ExecutionContext, OutputSlot, collect
from minipostgres.executor.factory import build_executor
from minipostgres.index.btree import BTree
from minipostgres.index.key import KeyCodec
from minipostgres.planner.physical import PlanExplanation, explain_plan
from minipostgres.planner.planner import Planner
from minipostgres.sql.binder import Binder
from minipostgres.sql.bound import (
    BoundCreateIndex,
    BoundCreateTable,
    BoundDelete,
    BoundExplain,
    BoundInsert,
    BoundSelect,
    BoundStatement,
    BoundUpdate,
)
from minipostgres.sql.parser import parse
from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.disk import DiskManager, relation_path
from minipostgres.storage.heap import HeapTable
from minipostgres.storage.identifiers import btree_relation, heap_relation
from minipostgres.storage.indexed import IndexBinding, IndexedTableAccess
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

    def __init__(
        self,
        root: Path,
        catalog: Catalog,
        *,
        buffer_frames: int,
    ) -> None:
        self._root = root
        self._catalog = catalog
        self._disk = DiskManager.open(root)
        self._buffer_pool = BufferPool(self._disk, buffer_frames)
        self._accesses: dict[int, IndexedTableAccess] = {}
        try:
            for table in catalog.tables():
                self._accesses[table.table_id] = IndexedTableAccess(
                    HeapTable.open(self._buffer_pool, table)
                )
            for index in catalog.indexes():
                self._accesses[index.table_id].add_index(
                    self._open_index_binding(index)
                )
        except BaseException:
            self._disk.close()
            raise
        self._context = ExecutionContext(dict(self._accesses))
        self._planner = Planner()
        self._lock = threading.RLock()
        self._closed = False

    @classmethod
    def open(
        cls,
        root: str | Path,
        *,
        buffer_frames: int = 16,
    ) -> Database:
        root_path = Path(root)
        return cls(
            root_path,
            Catalog.open(root_path),
            buffer_frames=buffer_frames,
        )

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
            if isinstance(bound, BoundCreateIndex):
                return self._create_index(bound)
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
        metadata = self._catalog.prepare_table(statement.name, columns)
        relation = heap_relation(metadata.table_id)
        self._disk.page_count(relation)
        self._disk.sync_relation(relation)
        self._catalog.publish_table(metadata)
        access = IndexedTableAccess(HeapTable.open(self._buffer_pool, metadata))
        self._accesses[metadata.table_id] = access
        self._context.register_table(access)
        for column in metadata.schema.columns:
            if column.unique:
                self._create_constraint_index(metadata, column, access)
        return QueryResult(command_tag="CREATE TABLE")

    def _create_constraint_index(
        self,
        table: TableMetadata,
        column: Column,
        access: IndexedTableAccess,
    ) -> None:
        """Back accepted PRIMARY KEY/UNIQUE syntax with a durable B+Tree."""

        suffix = "pkey" if column.primary_key else "key"
        name = f"{table.name}_{column.name}_{suffix}"
        metadata = self._catalog.prepare_index(
            name,
            table.table_id,
            (column.column_id,),
            unique=True,
        )
        tree = BTree.open(self._buffer_pool, metadata.index_id)
        self._buffer_pool.flush_all()
        self._disk.sync_relation(tree.relation)
        self._catalog.publish_index(metadata)
        access.add_index(
            IndexBinding(
                metadata,
                tree,
                KeyCodec((column.data_type,)),
            )
        )

    def _create_index(self, statement: BoundCreateIndex) -> QueryResult:
        metadata = self._catalog.prepare_index(
            statement.name,
            statement.table.table_id,
            tuple(column.column_id for column in statement.columns),
            unique=statement.unique,
        )
        codec = KeyCodec(
            tuple(column.data_type for column in statement.columns)
        )
        source = self._accesses[metadata.table_id]
        build_root = self._root / f".index-build-{metadata.index_id}"
        shutil.rmtree(build_root, ignore_errors=True)
        build_disk = DiskManager.open(build_root)
        try:
            build_pool = BufferPool(build_disk, frame_count=8)
            tree = BTree.open(build_pool, metadata.index_id)
            seen: set[bytes] = set()
            for tid, values in source.scan():
                try:
                    key = codec.encode(
                        tuple(
                            values[column_id]
                            for column_id in metadata.column_ids
                        )
                    )
                except Exception as error:
                    raise ConstraintViolation(str(error)) from error
                if metadata.unique and key in seen:
                    raise ConstraintViolation(
                        f"unique index {metadata.name} rejects duplicate key"
                    )
                seen.add(key)
                tree.insert(key, tid)
            build_pool.flush_all()
            build_disk.sync_relation(tree.relation)
            build_disk.close()

            source_path = relation_path(
                build_root,
                btree_relation(metadata.index_id),
            )
            target_path = relation_path(
                self._root,
                btree_relation(metadata.index_id),
            )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source_path, target_path)
            directory = os.open(target_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            try:
                self._catalog.publish_index(metadata)
            except BaseException:
                target_path.unlink(missing_ok=True)
                raise
        finally:
            build_disk.close()
            shutil.rmtree(build_root, ignore_errors=True)

        binding = self._open_index_binding(metadata)
        source.add_index(binding)
        return QueryResult(command_tag="CREATE INDEX")

    def _open_index_binding(self, metadata: IndexMetadata) -> IndexBinding:
        table = self._catalog.table(metadata.table_id)
        codec = KeyCodec(
            tuple(
                table.schema.column(column_id).data_type
                for column_id in metadata.column_ids
            )
        )
        return IndexBinding(
            metadata,
            BTree.open(self._buffer_pool, metadata.index_id),
            codec,
        )

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
            try:
                self._buffer_pool.flush_all()
                for table in self._catalog.tables():
                    self._disk.sync_relation(heap_relation(table.table_id))
                for index in self._catalog.indexes():
                    self._disk.sync_relation(btree_relation(index.index_id))
            finally:
                self._disk.close()

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
