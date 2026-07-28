from concurrent.futures import ThreadPoolExecutor

from minipostgres.engine import Database


def test_tuple_writer_waits_then_updates_latest_version(engine: Database) -> None:
    engine.execute("CREATE TABLE counters (id INT PRIMARY KEY, value INT)")
    engine.execute("INSERT INTO counters VALUES (1, 10)")
    first = engine.session()
    second = engine.session()
    first.execute("BEGIN")
    second.execute("BEGIN")
    first.execute("UPDATE counters SET value = 11 WHERE id = 1")

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            second.execute,
            "UPDATE counters SET value = 12 WHERE id = 1",
        )
        first.execute("COMMIT")
        assert pending.result(timeout=2).command_tag == "UPDATE 1"

    second.execute("COMMIT")
    assert engine.execute("SELECT value FROM counters WHERE id = 1").rows == (
        (12,),
    )
