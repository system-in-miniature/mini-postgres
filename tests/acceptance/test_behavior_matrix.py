from pathlib import Path

from minipostgres.acceptance import load_behavior_matrix


def test_every_graduation_requirement_has_direct_evidence() -> None:
    matrix = load_behavior_matrix(Path("BEHAVIOR_MATRIX.md"))
    required = {
        "query_path",
        "slotted_page",
        "buffer_pool",
        "btree",
        "optimizer",
        "mvcc",
        "locks",
        "wal_before_data",
        "durable_commit",
        "redo",
        "vacuum",
        "hot",
    }
    assert matrix.keys() >= required
    for evidence in matrix.values():
        for source in evidence.source_paths:
            assert Path(source).is_file(), source
        for nodeid in evidence.test_nodeids:
            test_path, separator, test_name = nodeid.partition("::")
            assert separator and Path(test_path).is_file(), nodeid
            assert f"def {test_name}(" in Path(test_path).read_text(
                encoding="utf-8"
            ), nodeid
