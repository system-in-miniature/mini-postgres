from minipostgres.engine import Database


def test_vacuum_marks_prior_statistics_stale(engine: Database) -> None:
    engine.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
    engine.execute("INSERT INTO users VALUES (1, 20)")
    engine.execute("ANALYZE users")
    before = engine.statistics.table(1)
    assert before is not None and not before.stale
    engine.execute("UPDATE users SET id = 2, age = 21 WHERE id = 1")

    engine.execute("VACUUM users")

    stale = engine.statistics.table(1)
    assert stale is not None and stale.stale
    assert stale.row_count == before.row_count
    engine.execute("ANALYZE users")
    refreshed = engine.statistics.table(1)
    assert refreshed is not None and not refreshed.stale
