from minipostgres.transaction.status import TransactionStatus, TransactionStatusTable


def test_status_defaults_and_terminal_transition() -> None:
    statuses = TransactionStatusTable()
    assert statuses.get(99) is TransactionStatus.IN_PROGRESS
    statuses.set(99, TransactionStatus.COMMITTED)
    assert statuses.get(99) is TransactionStatus.COMMITTED
