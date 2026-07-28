from minipostgres.maintenance.hot import hot_eligible


def test_hot_requires_unchanged_index_columns_and_same_page_space() -> None:
    assert hot_eligible({2}, {0}, 500, 200)
    assert not hot_eligible({0}, {0}, 500, 200)
    assert not hot_eligible({2}, {0}, 100, 200)
