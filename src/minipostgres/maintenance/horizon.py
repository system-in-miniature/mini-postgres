"""Conservative global tuple-version reclamation proofs."""

from __future__ import annotations

from enum import Enum

from minipostgres.storage.tuple import SYSTEM_XID, TupleVersion
from minipostgres.transaction.model import Transaction
from minipostgres.transaction.status import (
    TransactionStatus,
    TransactionStatusTable,
)


class VersionDisposition(Enum):
    KEEP = "keep"
    DEAD = "dead"


def cleanup_horizon(
    active_transactions: tuple[Transaction, ...],
    *,
    next_xid: int,
) -> int:
    candidates = [next_xid]
    for transaction in active_transactions:
        snapshot = transaction.repeatable_snapshot
        if snapshot is None:
            candidates.append(transaction.xid)
            continue
        candidates.append(snapshot.xmax)
        candidates.extend(snapshot.active_xids)
    return min(candidates)


def classify_version(
    version: TupleVersion,
    *,
    horizon: int,
    statuses: TransactionStatusTable,
) -> VersionDisposition:
    creator_status = (
        TransactionStatus.COMMITTED
        if version.xmin == SYSTEM_XID
        else statuses.get(version.xmin)
    )
    if (
        version.xmin < horizon
        and creator_status is TransactionStatus.ABORTED
    ):
        return VersionDisposition.DEAD
    if (
        version.xmax != 0
        and version.xmin < horizon
        and version.xmax < horizon
        and creator_status is TransactionStatus.COMMITTED
        and statuses.get(version.xmax) is TransactionStatus.COMMITTED
    ):
        return VersionDisposition.DEAD
    return VersionDisposition.KEEP
