from __future__ import annotations

from pathlib import Path

from minipostgres.catalog.catalog import Catalog
from minipostgres.catalog.model import Column
from minipostgres.executor.base import ExecutionContext, collect
from minipostgres.executor.factory import build_executor
from minipostgres.executor.operators import (
    AggregateExecutor,
    FilterExecutor,
    HashJoinExecutor,
    LimitExecutor,
    SeqScanExecutor,
    SortExecutor,
    ValuesExecutor,
)
from minipostgres.planner.planner import Planner
from minipostgres.row import ColumnBinding
from minipostgres.sql.binder import Binder
from minipostgres.sql.bound import (
    BoundColumn,
    BoundFunction,
    BoundOrderItem,
    BoundSelect,
)
from minipostgres.sql.parser import parse
from minipostgres.types import DataType


def _seed_context(context: ExecutionContext) -> None:
    users = context.table(1)
    orders = context.table(2)
    users.insert((1, "A", True))
    users.insert((1, "B", None))
    users.insert((2, "C", False))
    orders.insert((1, 10))
    orders.insert((1, 20))
    orders.insert((2, None))


def test_filter_drops_false_and_unknown_rows(
    execution_context: ExecutionContext,
) -> None:
    _seed_context(execution_context)
    active = BoundColumn(
        ColumnBinding(1, 2),
        "active",
        DataType.BOOLEAN,
        nullable=True,
    )

    rows = collect(FilterExecutor(SeqScanExecutor(1, execution_context), active))

    assert [row.cells[ColumnBinding(1, 1)] for row in rows] == ["A"]


def test_hash_join_preserves_duplicate_matches(
    execution_context: ExecutionContext,
) -> None:
    _seed_context(execution_context)
    user_id = BoundColumn(ColumnBinding(1, 0), "id", DataType.INT64, True)
    order_user_id = BoundColumn(
        ColumnBinding(2, 0),
        "user_id",
        DataType.INT64,
        True,
    )

    rows = collect(
        HashJoinExecutor(
            SeqScanExecutor(1, execution_context),
            SeqScanExecutor(2, execution_context),
            user_id,
            order_user_id,
            execution_context,
        )
    )

    assert len(rows) == 5


def test_global_aggregate_emits_one_row_for_empty_input(
    execution_context: ExecutionContext,
) -> None:
    count = BoundFunction("COUNT", (), DataType.INT64, False, star=True)
    aggregate = AggregateExecutor(
        ValuesExecutor((), execution_context),
        (),
        (count,),
        execution_context,
    )

    rows = collect(aggregate)

    assert len(rows) == 1
    assert rows[0].computed[count] == 0


def test_grouped_aggregate_applies_null_rules(
    execution_context: ExecutionContext,
) -> None:
    _seed_context(execution_context)
    user_id = BoundColumn(ColumnBinding(2, 0), "user_id", DataType.INT64, True)
    total = BoundColumn(ColumnBinding(2, 1), "total", DataType.INT64, True)
    count = BoundFunction("COUNT", (total,), DataType.INT64, False)
    summed = BoundFunction("SUM", (total,), DataType.INT64, True)
    aggregate = AggregateExecutor(
        SeqScanExecutor(2, execution_context),
        (user_id,),
        (count, summed),
        execution_context,
    )

    rows = collect(aggregate)

    results = [
        (row.computed[user_id], row.computed[count], row.computed[summed])
        for row in rows
    ]
    assert results == [
        (1, 2, 30),
        (2, 0, None),
    ]


def test_sort_limit_respects_direction_and_null_order(
    execution_context: ExecutionContext,
) -> None:
    _seed_context(execution_context)
    total = BoundColumn(ColumnBinding(2, 1), "total", DataType.INT64, True)
    sorted_rows = SortExecutor(
        SeqScanExecutor(2, execution_context),
        (BoundOrderItem(total, "DESC", None),),
        execution_context,
    )

    rows = collect(LimitExecutor(sorted_rows, 2))

    assert [row.cells[total.binding] for row in rows] == [None, 20]


def test_factory_executes_a_recursively_planned_query(
    execution_context: ExecutionContext,
    tmp_path: Path,
) -> None:
    _seed_context(execution_context)

    catalog = Catalog.open(tmp_path)
    catalog.create_table(
        "users",
        (
            Column("id", DataType.INT64),
            Column("name", DataType.TEXT),
            Column("active", DataType.BOOLEAN),
        ),
    )
    bound = Binder(catalog).bind(parse("SELECT name FROM users WHERE active = TRUE"))
    assert isinstance(bound, BoundSelect)
    planner = Planner()
    executor = build_executor(
        planner.physical(planner.logical(bound)),
        execution_context,
    )

    rows = collect(executor)

    assert [row.computed[bound.items[0].expression] for row in rows] == ["A"]
