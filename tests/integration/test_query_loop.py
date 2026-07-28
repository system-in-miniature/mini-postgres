from __future__ import annotations

from minipostgres.engine import Database


def test_insert_update_delete_and_expression_select(engine: Database) -> None:
    engine.execute("CREATE TABLE users (id INT NOT NULL, name TEXT, age INT)")
    engine.execute("INSERT INTO users VALUES (1, 'A', 20), (2, 'B', 30)")

    updated = engine.execute("UPDATE users SET age = age + 1 WHERE id = 2")
    deleted = engine.execute("DELETE FROM users WHERE id = 1")
    selected = engine.execute("SELECT name, age FROM users")

    assert updated.command_tag == "UPDATE 1"
    assert deleted.command_tag == "DELETE 1"
    assert selected.rows == (("B", 31),)


def test_catalog_and_rows_survive_reopen_with_persistent_heap_storage(
    tmp_path,
) -> None:
    with Database.open(tmp_path) as db:
        db.execute("CREATE TABLE users (id INT)")
        db.execute("INSERT INTO users VALUES (1)")

    with Database.open(tmp_path) as reopened:
        assert reopened.execute("SELECT COUNT(*) FROM users").rows == ((1,),)
