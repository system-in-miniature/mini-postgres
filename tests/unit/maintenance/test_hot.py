from minipostgres.maintenance.hot import hot_eligible


def test_hot_requires_unchanged_index_keys_and_same_page_result() -> None:
    old_keys = (b"primary-key", b"secondary-key")

    assert hot_eligible(
        same_heap_page=True,
        old_index_keys=old_keys,
        new_index_keys=old_keys,
    )
    assert not hot_eligible(
        same_heap_page=False,
        old_index_keys=old_keys,
        new_index_keys=old_keys,
    )
    assert not hot_eligible(
        same_heap_page=True,
        old_index_keys=old_keys,
        new_index_keys=(b"new-primary-key", b"secondary-key"),
    )
