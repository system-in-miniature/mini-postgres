from minipostgres.transaction.deadlock import WaitForGraph


def test_detector_returns_highest_xid_in_cycle() -> None:
    graph = WaitForGraph({7: {9}, 9: {12}, 12: {7}})
    assert graph.deadlock_victim() == 12


def test_acyclic_graph_has_no_victim() -> None:
    assert WaitForGraph({7: {9}, 9: {12}}).deadlock_victim() is None
