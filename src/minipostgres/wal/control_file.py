"""Checksummed recovery metadata published through atomic replacement."""

from __future__ import annotations

import json
import os
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from minipostgres.errors import CorruptWal
from minipostgres.transaction.status import TransactionStatus

_MAGIC = b"MPCF"
_VERSION = 1
_HEADER = struct.Struct(">4sB3xII")


@dataclass(frozen=True, slots=True)
class ControlState:
    checkpoint_lsn: int
    clean_shutdown: bool
    next_xid: int = 2
    statuses: tuple[tuple[int, TransactionStatus], ...] = ()


class ControlFile:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @property
    def temporary_path(self) -> Path:
        return self.path.with_name(f".{self.path.name}.tmp")

    def load(self) -> ControlState:
        if not self.path.exists():
            return ControlState(0, False)
        encoded = self.path.read_bytes()
        if len(encoded) < _HEADER.size:
            raise CorruptWal("invalid control file length")
        magic, version, payload_length, stored_crc = _HEADER.unpack_from(encoded)
        payload = encoded[_HEADER.size :]
        if (
            magic != _MAGIC
            or version != _VERSION
            or payload_length != len(payload)
            or zlib.crc32(payload) & 0xFFFFFFFF != stored_crc
        ):
            raise CorruptWal("control file checksum or header is invalid")
        try:
            document = json.loads(payload.decode("utf-8"))
            statuses = tuple(
                (int(xid), TransactionStatus(status))
                for xid, status in document["statuses"]
            )
            return ControlState(
                checkpoint_lsn=int(document["checkpoint_lsn"]),
                clean_shutdown=bool(document["clean_shutdown"]),
                next_xid=int(document["next_xid"]),
                statuses=statuses,
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError) as error:
            raise CorruptWal("control file payload is invalid") from error

    def store(self, state: ControlState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "checkpoint_lsn": state.checkpoint_lsn,
                "clean_shutdown": state.clean_shutdown,
                "next_xid": state.next_xid,
                "statuses": [
                    [xid, status.value] for xid, status in state.statuses
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        header = _HEADER.pack(
            _MAGIC,
            _VERSION,
            len(payload),
            zlib.crc32(payload) & 0xFFFFFFFF,
        )
        descriptor = os.open(
            self.temporary_path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            _write_all(descriptor, header + payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(self.temporary_path, self.path)
        directory = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _write_all(descriptor: int, data: bytes) -> None:
    written = 0
    while written < len(data):
        count = os.write(descriptor, data[written:])
        if count <= 0:
            raise OSError("short control-file write")
        written += count
