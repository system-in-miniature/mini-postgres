from pathlib import Path

import pytest

from minipostgres.engine import Database
from minipostgres.errors import BindError


def test_self_join_is_rejected_until_relation_instances_have_distinct_ids(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE users (id INT PRIMARY KEY)")

        with pytest.raises(
            BindError,
            match="self-joins are not supported",
        ):
            database.execute(
                "SELECT left_user.id "
                "FROM users AS left_user "
                "JOIN users AS right_user "
                "ON left_user.id = right_user.id"
            )

