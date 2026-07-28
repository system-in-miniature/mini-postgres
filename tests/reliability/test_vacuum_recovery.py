from minipostgres.engine import Database


def test_vacuum_state_and_index_rebuild_survive_unclean_restart(
    tmp_path,
) -> None:
    database = Database.open(tmp_path)
    database.execute("CREATE TABLE users (id INT PRIMARY KEY)")
    database.execute("INSERT INTO users VALUES (1)")
    database.execute("DELETE FROM users WHERE id = 1")
    database.execute("VACUUM users")
    database.execute("INSERT INTO users VALUES (2)")
    database._wal.close()
    database._disk.close()
    database._closed = True

    with Database.open(tmp_path) as recovered:
        assert recovered.execute("SELECT id FROM users").rows == ((2,),)
        assert (
            recovered.execute("VACUUM users").maintenance.dead_versions_removed
            == 0
        )
