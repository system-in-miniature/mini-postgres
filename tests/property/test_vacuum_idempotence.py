from minipostgres.engine import Database


def test_vacuum_twice_is_physically_idempotent(engine: Database) -> None:
    engine.execute("CREATE TABLE items (id INT PRIMARY KEY)")
    engine.execute("INSERT INTO items VALUES (1)")
    engine.execute("DELETE FROM items WHERE id = 1")
    first = engine.execute("VACUUM items")
    access = engine._accesses[1]
    once = tuple(access._mvcc_heap().scan_versions())

    second = engine.execute("VACUUM items")

    assert first.maintenance is not None
    assert first.maintenance.dead_versions_removed == 1
    assert second.maintenance is not None
    assert second.maintenance.dead_versions_removed == 0
    assert tuple(access._mvcc_heap().scan_versions()) == once
