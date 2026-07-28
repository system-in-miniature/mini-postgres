"""Phase A Volcano query operators."""

from __future__ import annotations

from collections import defaultdict
from functools import cmp_to_key
from typing import cast

from minipostgres.catalog.model import Column, TableMetadata
from minipostgres.errors import CatalogError, ConstraintViolation
from minipostgres.executor.base import (
    ExecutionContext,
    Executor,
    OutputSlot,
)
from minipostgres.executor.expressions import evaluate
from minipostgres.row import TID, ColumnBinding, ExecutionRow
from minipostgres.sql.bound import (
    BoundAssignment,
    BoundExpr,
    BoundFunction,
    BoundOrderItem,
    BoundSelectItem,
)
from minipostgres.storage.indexed import IndexedTableAccess
from minipostgres.types import Scalar


def _table_row(
    table_id: int,
    columns: tuple[Column, ...],
    tid: TID,
    values: tuple[Scalar, ...],
) -> ExecutionRow:
    cells = {
        ColumnBinding(table_id, column.column_id): value
        for column, value in zip(columns, values, strict=True)
    }
    return ExecutionRow(cells, {table_id: tid})


class ValuesExecutor(Executor):
    def __init__(
        self,
        rows: tuple[tuple[BoundExpr, ...], ...],
        context: ExecutionContext,
    ) -> None:
        super().__init__()
        self._rows = rows
        self._context = context
        self._index = 0

    def _next(self) -> ExecutionRow | None:
        if self._index >= len(self._rows):
            return None
        expressions = self._rows[self._index]
        self._index += 1
        base = ExecutionRow({}, {})
        computed: dict[object, Scalar] = {}
        for index, expression in enumerate(expressions):
            value = evaluate(expression, base)
            computed[OutputSlot(index)] = value
            computed[cast(object, expression)] = value
        return ExecutionRow({}, {}, computed)


class SeqScanExecutor(Executor):
    def __init__(self, table_id: int, context: ExecutionContext) -> None:
        super().__init__()
        self._table_id = table_id
        self._context = context
        self._iterator = None

    def _open(self) -> None:
        access = self._context.table(self._table_id)
        if isinstance(access, IndexedTableAccess) and _has_mvcc(self._context):
            assert self._context.snapshot is not None
            assert self._context.transaction is not None
            assert self._context.statuses is not None
            self._iterator = access.scan_mvcc(
                self._context.snapshot,
                self._context.transaction.xid,
                self._context.statuses,
            )
        else:
            self._iterator = access.scan()

    def _next(self) -> ExecutionRow | None:
        assert self._iterator is not None
        try:
            tid, values = next(self._iterator)
        except StopIteration:
            return None
        table = self._context.table(self._table_id)
        return _table_row(self._table_id, table.schema.columns, tid, values)

    def _close(self) -> None:
        self._iterator = None


class IndexScanExecutor(Executor):
    """Fetch index candidates from the heap and recheck the full predicate."""

    def __init__(
        self,
        table_id: int,
        index_id: int,
        lower_key: bytes,
        upper_key: bytes,
        predicate: BoundExpr | None,
        context: ExecutionContext,
    ) -> None:
        super().__init__()
        self._table_id = table_id
        self._index_id = index_id
        self._lower_key = lower_key
        self._upper_key = upper_key
        self._predicate = predicate
        self._context = context
        self._iterator = None
        self._seen_visible: set[TID] = set()

    def _open(self) -> None:
        access = self._access()
        binding = next(
            (
                candidate
                for candidate in access.indexes
                if candidate.metadata.index_id == self._index_id
            ),
            None,
        )
        if binding is None:
            raise ConstraintViolation(f"unknown runtime index: {self._index_id}")
        if self._lower_key == self._upper_key:
            self._iterator = iter(
                (self._lower_key, tid)
                for tid in binding.tree.search(self._lower_key)
            )
        else:
            self._iterator = binding.tree.range(
                self._lower_key,
                self._upper_key,
            )

    def _next(self) -> ExecutionRow | None:
        assert self._iterator is not None
        access = self._access()
        for _, tid in self._iterator:
            if _has_mvcc(self._context):
                assert self._context.snapshot is not None
                assert self._context.transaction is not None
                assert self._context.statuses is not None
                resolved = access.resolve_mvcc(
                    tid,
                    self._context.snapshot,
                    self._context.transaction.xid,
                    self._context.statuses,
                )
                if resolved is None:
                    continue
                visible_tid, values = resolved
                if visible_tid in self._seen_visible:
                    continue
                self._seen_visible.add(visible_tid)
                tid = visible_tid
            else:
                values = access.fetch(tid)
            if values is None:
                continue
            row = _table_row(
                self._table_id,
                access.schema.columns,
                tid,
                values,
            )
            if self._predicate is None or evaluate(self._predicate, row) is True:
                return row
        return None

    def _close(self) -> None:
        close = getattr(self._iterator, "close", None)
        if callable(close):
            close()
        self._iterator = None
        self._seen_visible.clear()

    def _access(self) -> IndexedTableAccess:
        access = self._context.table(self._table_id)
        if not isinstance(access, IndexedTableAccess):
            raise ConstraintViolation("index scan requires indexed table access")
        return access


class UnaryExecutor(Executor):
    def __init__(self, child: Executor) -> None:
        super().__init__()
        self.child = child

    def _open(self) -> None:
        self.child.open()

    def _close(self) -> None:
        self.child.close()


class FilterExecutor(UnaryExecutor):
    def __init__(
        self,
        child: Executor,
        predicate: BoundExpr,
    ) -> None:
        super().__init__(child)
        self._predicate = predicate

    def _next(self) -> ExecutionRow | None:
        while (row := self.child.next()) is not None:
            if evaluate(self._predicate, row) is True:
                return row
        return None


class ProjectExecutor(UnaryExecutor):
    def __init__(
        self,
        child: Executor,
        items: tuple[BoundSelectItem, ...],
    ) -> None:
        super().__init__(child)
        self._items = items

    def _next(self) -> ExecutionRow | None:
        row = self.child.next()
        if row is None:
            return None
        computed = dict(row.computed)
        for index, item in enumerate(self._items):
            value = evaluate(item.expression, row)
            computed[OutputSlot(index)] = value
            computed[cast(object, item.expression)] = value
        return ExecutionRow(dict(row.cells), dict(row.tids), computed)


class NestedLoopJoinExecutor(Executor):
    def __init__(
        self,
        left: Executor,
        right: Executor,
        condition: BoundExpr,
        context: ExecutionContext,
    ) -> None:
        super().__init__()
        self._left = left
        self._right = right
        self._condition = condition
        self._context = context
        self._right_rows: list[ExecutionRow] = []
        self._left_row: ExecutionRow | None = None
        self._right_index = 0

    def _open(self) -> None:
        self._left.open()
        self._right_rows = _drain_opened(self._right)

    def _next(self) -> ExecutionRow | None:
        while True:
            if self._left_row is None:
                self._left_row = self._left.next()
                self._right_index = 0
                if self._left_row is None:
                    return None
            while self._right_index < len(self._right_rows):
                right = self._right_rows[self._right_index]
                self._right_index += 1
                merged = self._left_row.merge(right)
                if evaluate(self._condition, merged) is True:
                    return merged
            self._left_row = None

    def _close(self) -> None:
        self._left.close()
        self._right.close()
        self._right_rows.clear()


class HashJoinExecutor(Executor):
    def __init__(
        self,
        left: Executor,
        right: Executor,
        left_key: BoundExpr,
        right_key: BoundExpr,
        context: ExecutionContext,
        condition: BoundExpr | None = None,
    ) -> None:
        super().__init__()
        self._left = left
        self._right = right
        self._left_key = left_key
        self._right_key = right_key
        self._context = context
        self._condition = condition
        self._hash: dict[Scalar, list[ExecutionRow]] = defaultdict(list)
        self._matches: list[ExecutionRow] = []
        self._match_index = 0

    def _open(self) -> None:
        self._left.open()
        self._right.open()
        while (row := self._right.next()) is not None:
            key = evaluate(self._right_key, row)
            if key is not None:
                self._hash[key].append(row)

    def _next(self) -> ExecutionRow | None:
        while True:
            if self._match_index < len(self._matches):
                row = self._matches[self._match_index]
                self._match_index += 1
                return row
            left = self._left.next()
            if left is None:
                return None
            key = evaluate(self._left_key, left)
            candidates = () if key is None else self._hash.get(key, ())
            self._matches = []
            for right in candidates:
                merged = left.merge(right)
                if self._condition is None or evaluate(self._condition, merged) is True:
                    self._matches.append(merged)
            self._match_index = 0

    def _close(self) -> None:
        self._left.close()
        self._right.close()
        self._hash.clear()
        self._matches.clear()


class AggregateExecutor(UnaryExecutor):
    def __init__(
        self,
        child: Executor,
        group_by: tuple[BoundExpr, ...],
        aggregates: tuple[BoundFunction, ...],
        context: ExecutionContext,
    ) -> None:
        super().__init__(child)
        self._group_by = group_by
        self._aggregates = aggregates
        self._context = context
        self._results: list[ExecutionRow] = []
        self._index = 0

    def _open(self) -> None:
        super()._open()
        groups: dict[tuple[Scalar, ...], list[ExecutionRow]] = {}
        while (row := self.child.next()) is not None:
            key = tuple(evaluate(expression, row) for expression in self._group_by)
            groups.setdefault(key, []).append(row)
        if not self._group_by and not groups:
            groups[()] = []
        for key, rows in groups.items():
            computed: dict[object, Scalar] = {
                cast(object, expression): value
                for expression, value in zip(self._group_by, key, strict=True)
            }
            for aggregate in self._aggregates:
                computed[cast(object, aggregate)] = _aggregate_value(aggregate, rows)
            self._results.append(ExecutionRow({}, {}, computed))

    def _next(self) -> ExecutionRow | None:
        if self._index >= len(self._results):
            return None
        row = self._results[self._index]
        self._index += 1
        return row

    def _close(self) -> None:
        super()._close()
        self._results.clear()


class SortExecutor(UnaryExecutor):
    def __init__(
        self,
        child: Executor,
        order_by: tuple[BoundOrderItem, ...],
        context: ExecutionContext,
    ) -> None:
        super().__init__(child)
        self._order_by = order_by
        self._context = context
        self._rows: list[ExecutionRow] = []
        self._index = 0

    def _open(self) -> None:
        super()._open()
        while (row := self.child.next()) is not None:
            self._rows.append(row)
        self._rows.sort(key=cmp_to_key(self._compare))

    def _compare(self, left: ExecutionRow, right: ExecutionRow) -> int:
        for item in self._order_by:
            comparison = _compare_order_values(
                evaluate(item.expression, left),
                evaluate(item.expression, right),
                direction=item.direction,
                nulls=item.nulls,
            )
            if comparison:
                return comparison
        return 0

    def _next(self) -> ExecutionRow | None:
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def _close(self) -> None:
        super()._close()
        self._rows.clear()


class LimitExecutor(UnaryExecutor):
    def __init__(self, child: Executor, limit: int) -> None:
        super().__init__(child)
        self._limit = limit
        self._emitted = 0

    def _next(self) -> ExecutionRow | None:
        if self._emitted >= self._limit:
            return None
        row = self.child.next()
        if row is not None:
            self._emitted += 1
        return row


class ModificationExecutor(Executor):
    def __init__(self, child: Executor) -> None:
        super().__init__()
        self.child = child
        self._affected = 0
        self._emitted = False

    def _next(self) -> ExecutionRow | None:
        if self._emitted:
            return None
        self._emitted = True
        return ExecutionRow({}, {}, {OutputSlot(0): self._affected})

    def _close(self) -> None:
        self.child.close()


class InsertExecutor(ModificationExecutor):
    def __init__(
        self,
        child: Executor,
        table: TableMetadata,
        target_columns: tuple[Column, ...],
        context: ExecutionContext,
    ) -> None:
        super().__init__(child)
        self._table = table
        self._target_columns = target_columns
        self._context = context

    def _open(self) -> None:
        candidates: list[tuple[Scalar, ...]] = []
        self.child.open()
        try:
            while (row := self.child.next()) is not None:
                values: list[Scalar] = [None] * len(self._table.schema.columns)
                for index, column in enumerate(self._target_columns):
                    values[column.column_id] = row.computed[OutputSlot(index)]
                candidates.append(self._validate(tuple(values)))
        finally:
            self.child.close()
        access = self._context.table(self._table.table_id)
        inserted: list[TID] = []
        try:
            for candidate in candidates:
                if _has_mvcc(self._context) and isinstance(
                    access,
                    IndexedTableAccess,
                ):
                    assert self._context.transaction is not None
                    assert self._context.snapshot is not None
                    assert self._context.statuses is not None
                    inserted.append(
                        access.insert_mvcc(
                            self._context.transaction.xid,
                            self._context.snapshot,
                            self._context.statuses,
                            candidate,
                        )
                    )
                else:
                    inserted.append(access.insert(candidate))
        except BaseException:
            for tid in reversed(inserted):
                access.delete(tid)
            raise
        self._affected = len(candidates)

    def _validate(self, values: tuple[Scalar, ...]) -> tuple[Scalar, ...]:
        try:
            return self._table.schema.validate_row(values)
        except CatalogError as error:
            raise ConstraintViolation(str(error)) from error


class UpdateExecutor(ModificationExecutor):
    def __init__(
        self,
        child: Executor,
        table: TableMetadata,
        assignments: tuple[BoundAssignment, ...],
        context: ExecutionContext,
    ) -> None:
        super().__init__(child)
        self._table = table
        self._assignments = assignments
        self._context = context

    def _open(self) -> None:
        candidates: list[tuple[TID, tuple[Scalar, ...]]] = []
        self.child.open()
        try:
            while (row := self.child.next()) is not None:
                try:
                    tid = row.tids[self._table.table_id]
                except KeyError as error:
                    raise ConstraintViolation(
                        "UPDATE input row has no source TID"
                    ) from error
                values = [
                    row.cells[ColumnBinding(self._table.table_id, column.column_id)]
                    for column in self._table.schema.columns
                ]
                for assignment in self._assignments:
                    values[assignment.column.column_id] = evaluate(
                        assignment.expression,
                        row,
                    )
                try:
                    validated = self._table.schema.validate_row(tuple(values))
                except CatalogError as error:
                    raise ConstraintViolation(str(error)) from error
                candidates.append((tid, validated))
        finally:
            self.child.close()
        access = self._context.table(self._table.table_id)
        affected = 0
        applied: list[tuple[TID, tuple[Scalar, ...]]] = []
        try:
            for tid, values in candidates:
                if _has_mvcc(self._context) and isinstance(
                    access,
                    IndexedTableAccess,
                ):
                    assert self._context.transaction is not None
                    assert self._context.snapshot is not None
                    assert self._context.statuses is not None
                    old_values = access.fetch_mvcc(
                        tid,
                        self._context.snapshot,
                        self._context.transaction.xid,
                        self._context.statuses,
                    )
                else:
                    old_values = access.fetch(tid)
                if old_values is None:
                    raise ConstraintViolation("UPDATE source tuple disappeared")
                if _has_mvcc(self._context) and isinstance(
                    access,
                    IndexedTableAccess,
                ):
                    assert self._context.transaction is not None
                    assert self._context.snapshot is not None
                    assert self._context.statuses is not None
                    replacement = access.replace_mvcc(
                        tid,
                        self._context.transaction.xid,
                        self._context.snapshot,
                        self._context.statuses,
                        values,
                    )
                else:
                    replacement = access.replace(tid, values)
                if replacement is None:
                    raise ConstraintViolation("UPDATE source tuple disappeared")
                applied.append((replacement, old_values))
                affected += 1
        except BaseException as error:
            for replacement, old_values in reversed(applied):
                if access.replace(replacement, old_values) is None:
                    raise RuntimeError(
                        "failed to roll back partial UPDATE"
                    ) from error
            raise
        self._affected = affected


class DeleteExecutor(ModificationExecutor):
    def __init__(
        self,
        child: Executor,
        table: TableMetadata,
        context: ExecutionContext,
    ) -> None:
        super().__init__(child)
        self._table = table
        self._context = context

    def _open(self) -> None:
        tids: list[TID] = []
        self.child.open()
        try:
            while (row := self.child.next()) is not None:
                try:
                    tids.append(row.tids[self._table.table_id])
                except KeyError as error:
                    raise ConstraintViolation(
                        "DELETE input row has no source TID"
                    ) from error
        finally:
            self.child.close()
        access = self._context.table(self._table.table_id)
        if _has_mvcc(self._context) and isinstance(access, IndexedTableAccess):
            assert self._context.transaction is not None
            self._affected = sum(
                access.delete_mvcc(tid, self._context.transaction.xid)
                for tid in tids
            )
        else:
            self._affected = sum(access.delete(tid) for tid in tids)


def _has_mvcc(context: ExecutionContext) -> bool:
    return (
        context.transaction is not None
        and context.snapshot is not None
        and context.statuses is not None
    )


def _drain_opened(executor: Executor) -> list[ExecutionRow]:
    executor.open()
    rows: list[ExecutionRow] = []
    while (row := executor.next()) is not None:
        rows.append(row)
    return rows


def _aggregate_value(
    aggregate: BoundFunction,
    rows: list[ExecutionRow],
) -> Scalar:
    if aggregate.star:
        values: list[Scalar] = [1 for _ in rows]
    else:
        argument = aggregate.arguments[0]
        values = [
            value for row in rows if (value := evaluate(argument, row)) is not None
        ]
    if aggregate.name == "COUNT":
        return len(values)
    if not values:
        return None
    if aggregate.name == "SUM":
        return sum(cast(list[int | float], values))
    if aggregate.name == "AVG":
        return float(sum(cast(list[int | float], values))) / len(values)
    if aggregate.name == "MIN":
        return _extreme(values, maximum=False)
    if aggregate.name == "MAX":
        return _extreme(values, maximum=True)
    raise ValueError(f"unsupported aggregate: {aggregate.name}")


def _extreme(values: list[Scalar], *, maximum: bool) -> Scalar:
    result = values[0]
    for value in values[1:]:
        if maximum:
            if value > result:  # type: ignore[operator]
                result = value
        elif value < result:  # type: ignore[operator]
            result = value
    return result


def _compare_order_values(
    left: Scalar,
    right: Scalar,
    *,
    direction: str,
    nulls: str | None,
) -> int:
    nulls_first = nulls == "FIRST" if nulls is not None else direction == "DESC"
    if left is None or right is None:
        if left is None and right is None:
            return 0
        if left is None:
            return -1 if nulls_first else 1
        return 1 if nulls_first else -1
    if left < right:  # type: ignore[operator]
        comparison = -1
    elif left > right:  # type: ignore[operator]
        comparison = 1
    else:
        comparison = 0
    return -comparison if direction == "DESC" else comparison
