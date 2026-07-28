from __future__ import annotations

import pytest

from minipostgres.engine import Database
from minipostgres.errors import MiniPostgresError


def test_failed_execution_closes_every_instrumented_node(
    engine: Database,
) -> None:
    engine.execute("CREATE TABLE values_table (value INT)")
    engine.execute("INSERT INTO values_table VALUES (0)")
    tracker = engine.instrumentation_tracker

    with pytest.raises(MiniPostgresError):
        engine.execute(
            "EXPLAIN ANALYZE "
            "SELECT 10 / value FROM values_table"
        )

    assert tracker.open_count > 0
    assert tracker.open_count == tracker.close_count
