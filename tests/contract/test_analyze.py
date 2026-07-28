from __future__ import annotations

from pathlib import Path

import pytest

from minipostgres.engine import Database


def test_analyze_collects_null_distinct_mcv_and_histogram(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute(
            "CREATE TABLE events (kind TEXT, score INT, note TEXT)"
        )
        for start in range(0, 100, 20):
            values = []
            for value in range(start, start + 20):
                kind = "hot" if value < 40 else f"kind-{value}"
                note = "NULL" if value < 10 else f"'note-{value}'"
                values.append(f"('{kind}', {value}, {note})")
            database.execute(f"INSERT INTO events VALUES {', '.join(values)}")

        result = database.execute("ANALYZE events")
        statistics = database.statistics.table(
            database.catalog.table("events").table_id
        )

        assert result.command_tag == "ANALYZE"
        assert statistics is not None
        assert statistics.row_count == 100
        assert statistics.page_count > 0
        assert statistics.columns[2].null_fraction == pytest.approx(0.1)
        assert statistics.columns[0].most_common_values[0] == ("hot", 0.4)
        assert statistics.columns[1].distinct_count == 100
        assert statistics.columns[1].histogram_bounds == tuple(
            sorted(statistics.columns[1].histogram_bounds)
        )


def test_analyze_without_table_refreshes_every_catalog_table(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE a (id INT)")
        database.execute("CREATE TABLE b (id INT)")
        database.execute("INSERT INTO a VALUES (1), (2)")
        database.execute("INSERT INTO b VALUES (3)")

        database.execute("ANALYZE")

        assert database.statistics.table(1).row_count == 2  # type: ignore[union-attr]
        assert database.statistics.table(2).row_count == 1  # type: ignore[union-attr]


def test_analyze_statistics_survive_restart_but_remain_stale_until_refreshed(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE items (id INT)")
        database.execute("INSERT INTO items VALUES (1)")
        database.execute("ANALYZE items")
        database.execute("INSERT INTO items VALUES (2)")

    with Database.open(tmp_path) as reopened:
        assert reopened.statistics.table(1).row_count == 1  # type: ignore[union-attr]
        reopened.execute("ANALYZE items")
        assert reopened.statistics.table(1).row_count == 2  # type: ignore[union-attr]

