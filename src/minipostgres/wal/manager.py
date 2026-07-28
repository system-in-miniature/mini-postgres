"""Append, durability, and repair policy for the WAL byte stream."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from minipostgres.errors import CorruptWal
from minipostgres.wal.records import (
    HEADER_SIZE,
    DecodedWalRecord,
    WalRecord,
    decode_record,
    encode_record,
    record_length_from_header,
)


class WalManager:
    def __init__(
        self,
        path: Path,
        descriptor: int,
        entries: list[DecodedWalRecord],
        end_lsn: int,
    ) -> None:
        self.path = path
        self._descriptor = descriptor
        self._entries = entries
        self._end_lsn = end_lsn
        self._flushed_lsn = 0
        self._closed = False
        self._lock = threading.RLock()

    @classmethod
    def open(cls, path: Path) -> WalManager:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            entries, valid_end = cls._scan_descriptor(descriptor)
            size = os.fstat(descriptor).st_size
            if valid_end != size:
                os.ftruncate(descriptor, valid_end)
                os.fsync(descriptor)
            manager = cls(path, descriptor, entries, valid_end)
            manager._flushed_lsn = valid_end
            return manager
        except BaseException:
            os.close(descriptor)
            raise

    @property
    def end_lsn(self) -> int:
        with self._lock:
            return self._end_lsn

    @property
    def flushed_lsn(self) -> int:
        with self._lock:
            return self._flushed_lsn

    def append(self, xid: int, record: WalRecord) -> int:
        with self._lock:
            self._ensure_open()
            lsn = self._end_lsn
            encoded = encode_record(lsn, xid, record)
            self._pwrite_all(encoded, lsn)
            decoded = decode_record(encoded)
            self._entries.append(decoded)
            self._end_lsn = decoded.end_lsn
            return lsn

    def flush(self, required_lsn: int | None = None) -> None:
        """Make the stream durable through the record starting at required_lsn."""

        with self._lock:
            self._ensure_open()
            if required_lsn is not None and required_lsn > self._end_lsn:
                raise ValueError("cannot flush beyond the WAL end")
            if self._flushed_lsn < self._end_lsn:
                os.fsync(self._descriptor)
                self._flushed_lsn = self._end_lsn

    def scan(self, start_lsn: int = 0) -> tuple[DecodedWalRecord, ...]:
        with self._lock:
            self._ensure_open()
            return tuple(entry for entry in self._entries if entry.lsn >= start_lsn)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            os.close(self._descriptor)
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("WAL manager is closed")

    def _pwrite_all(self, data: bytes, offset: int) -> None:
        written = 0
        while written < len(data):
            count = os.pwrite(self._descriptor, data[written:], offset + written)
            if count <= 0:
                raise OSError("short WAL write")
            written += count

    @staticmethod
    def _scan_descriptor(
        descriptor: int,
    ) -> tuple[list[DecodedWalRecord], int]:
        size = os.fstat(descriptor).st_size
        cursor = 0
        entries: list[DecodedWalRecord] = []
        while cursor < size:
            if size - cursor < HEADER_SIZE:
                break
            header = os.pread(descriptor, HEADER_SIZE, cursor)
            try:
                total_length = record_length_from_header(header)
            except CorruptWal:
                if cursor + HEADER_SIZE == size:
                    break
                raise
            if cursor + total_length > size:
                break
            encoded = os.pread(descriptor, total_length, cursor)
            try:
                entry = decode_record(encoded)
            except CorruptWal:
                if cursor + total_length == size:
                    break
                raise
            if entry.lsn != cursor:
                raise CorruptWal("WAL record LSN does not match file position")
            entries.append(entry)
            cursor += total_length
        return entries, cursor
