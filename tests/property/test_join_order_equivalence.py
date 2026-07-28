from __future__ import annotations

from collections import Counter
from tempfile import TemporaryDirectory

from hypothesis import given, settings
from hypothesis import strategies as st

from minipostgres.engine import Database


@given(
    st.lists(
        st.integers(min_value=0, max_value=5),
        min_size=1,
        max_size=8,
    ),
    st.lists(
        st.integers(min_value=0, max_value=5),
        min_size=1,
        max_size=8,
    ),
    st.lists(
        st.integers(min_value=0, max_value=5),
        min_size=1,
        max_size=8,
    ),
)
@settings(max_examples=20, deadline=None)
def test_three_way_reordering_preserves_join_multiset(
    left_values: list[int],
    middle_values: list[int],
    right_values: list[int],
) -> None:
    with TemporaryDirectory() as directory, Database.open(directory) as database:
        database.execute("CREATE TABLE a (id INT)")
        database.execute("CREATE TABLE b (id INT)")
        database.execute("CREATE TABLE c (id INT)")
        for table, values in (
            ("a", left_values),
            ("b", middle_values),
            ("c", right_values),
        ):
            database.execute(
                f"INSERT INTO {table} VALUES "
                + ", ".join(f"({value})" for value in values)
            )
        database.execute("ANALYZE")

        rows = database.execute(
            "SELECT a.id, b.id, c.id FROM a "
            "JOIN b ON a.id = b.id "
            "JOIN c ON b.id = c.id"
        ).rows

        expected = Counter(
            (left, middle, right)
            for left in left_values
            for middle in middle_values
            for right in right_values
            if left == middle == right
        )
        assert Counter(rows) == expected
