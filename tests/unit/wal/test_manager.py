from __future__ import annotations

import os

import pytest

from minipostgres.errors import MiniPostgresError
from minipostgres.wal.manager import WalManager
from minipostgres.wal.records import AbortRecord, BeginRecord, CommitRecord


def test_append_flush_and_reopen_preserve_monotonic_lsn(tmp_path) -> None:
    path = tmp_path / "wal.log"
    wal = WalManager.open(path)
    first = wal.append(3, BeginRecord())
    second = wal.append(3, CommitRecord())
    assert first < second
    assert wal.flushed_lsn < wal.end_lsn
    wal.flush(wal.end_lsn)
    assert wal.flushed_lsn == wal.end_lsn
    wal.close()

    reopened = WalManager.open(path)
    assert [entry.record for entry in reopened.scan()] == [
        BeginRecord(),
        CommitRecord(),
    ]
    assert reopened.end_lsn > second
    reopened.close()


def test_scan_truncates_an_incomplete_tail(tmp_path) -> None:
    path = tmp_path / "wal.log"
    wal = WalManager.open(path)
    wal.append(4, BeginRecord())
    wal.append(4, CommitRecord())
    valid_end = wal.end_lsn
    wal.close()
    with path.open("ab") as stream:
        stream.write(b"partial")

    reopened = WalManager.open(path)
    assert reopened.end_lsn == valid_end
    assert os.path.getsize(path) == valid_end
    reopened.close()


def test_scan_rejects_corruption_before_a_later_record(tmp_path) -> None:
    path = tmp_path / "wal.log"
    wal = WalManager.open(path)
    wal.append(5, BeginRecord())
    second = wal.append(5, CommitRecord())
    wal.append(5, AbortRecord())
    wal.close()
    with path.open("r+b") as stream:
        stream.seek(second + 12)
        byte = stream.read(1)
        stream.seek(second + 12)
        stream.write(bytes([byte[0] ^ 0xFF]))

    with pytest.raises(MiniPostgresError, match="WAL"):
        WalManager.open(path)
