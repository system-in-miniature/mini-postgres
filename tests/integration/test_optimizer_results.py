from __future__ import annotations

from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, settings
from hypothesis import strategies as st

from minipostgres.catalog.catalog import Catalog
from minipostgres.catalog.model import Column
from minipostgres.catalog.statistics import StatisticsStore
from minipostgres.executor.base import ExecutionContext, OutputSlot, collect
from minipostgres.executor.factory import build_executor
from minipostgres.executor.memory import MemoryTable
from minipostgres.maintenance.analyze import analyze_table
from minipostgres.planner.optimizer import CostBasedOptimizer
from minipostgres.planner.planner import Planner
from minipostgres.sql.binder import Binder
from minipostgres.sql.parser import parse
from minipostgres.storage.indexed import IndexedTableAccess
from minipostgres.types import DataType


@given(
    st.lists(st.integers(0, 4), min_size=1, max_size=7),
    st.lists(st.integers(0, 4), min_size=1, max_size=7),
    st.lists(st.integers(0, 4), min_size=1, max_size=7),
)
@settings(max_examples=20, deadline=None)
def test_optimized_and_baseline_plans_return_same_multiset(
    left_values: list[int],
    middle_values: list[int],
    right_values: list[int],
) -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        catalog = Catalog.open(root)
        accesses: dict[int, IndexedTableAccess] = {}
        for name, values in (
            ("a", left_values),
            ("b", middle_values),
            ("c", right_values),
        ):
            metadata = catalog.create_table(
                name,
                (Column("id", DataType.INT64),),
            )
            access = IndexedTableAccess(
                MemoryTable(metadata.table_id, metadata.schema)
            )
            for value in values:
                access.insert((value,))
            accesses[metadata.table_id] = access

        statistics = StatisticsStore.open(root)
        for metadata in catalog.tables():
            statistics.replace(
                analyze_table(
                    metadata,
                    accesses[metadata.table_id],
                    page_count=1,
                )
            )
        statement = Binder(catalog).bind(
            parse(
                "SELECT a.id, b.id, c.id FROM a "
                "JOIN b ON a.id = b.id "
                "JOIN c ON b.id = c.id"
            )
        )
        logical = Planner().logical(statement)
        baseline = Planner().physical(logical)
        optimized = CostBasedOptimizer(
            catalog,
            statistics,
            accesses,
        ).optimize(logical)
        context = ExecutionContext(accesses)

        def result(plan) -> Counter[tuple[object, ...]]:
            rows = collect(build_executor(plan, context))
            return Counter(
                tuple(
                    row.computed[OutputSlot(index)]
                    for index in range(3)
                )
                for row in rows
            )

        assert result(optimized) == result(baseline)
