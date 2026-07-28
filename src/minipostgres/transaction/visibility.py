from __future__ import annotations

from minipostgres.storage.tuple import SYSTEM_XID, TupleVersion
from minipostgres.transaction.snapshot import Snapshot
from minipostgres.transaction.status import TransactionStatus, TransactionStatusTable


def is_visible(
    version: TupleVersion,
    snapshot: Snapshot,
    current_xid: int,
    statuses: TransactionStatusTable,
) -> bool:
    if version.xmin == current_xid:
        return version.xmax != current_xid
    creator = (
        TransactionStatus.COMMITTED
        if version.xmin == SYSTEM_XID
        else statuses.get(version.xmin)
    )
    if (
        creator is not TransactionStatus.COMMITTED
        or version.xmin >= snapshot.xmax
        or version.xmin in snapshot.active_xids
    ):
        return False
    if version.xmax == 0:
        return True
    if version.xmax == current_xid:
        return False
    deleter = statuses.get(version.xmax)
    return (
        deleter is not TransactionStatus.COMMITTED
        or version.xmax >= snapshot.xmax
        or version.xmax in snapshot.active_xids
    )
