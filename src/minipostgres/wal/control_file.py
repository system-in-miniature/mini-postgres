"""Small checksummed control file updated through atomic replacement."""

from __future__ import annotations

import os
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from minipostgres.errors import CorruptWal

_MAGIC = b"MPCF"
_VERSION = 1
_STRUCT = struct.Struct(">4sBBHQI")
_CHECKSUM_OFFSET = _STRUCT.size - 4


@dataclass(frozen=True, slots=True)
class ControlState:
    checkpoint_lsn: int
    clean_shutdown: bool


class ControlFile:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> ControlState:
        if not self.path.exists():
            return ControlState(0, False)
        encoded = self.path.read_bytes()
        if len(encoded) != _STRUCT.size:
            raise CorruptWal("invalid control file length")
        magic, version, clean, reserved, checkpoint_lsn, stored_crc = (
            _STRUCT.unpack(encoded)
        )
        mutable = bytearray(encoded)
        mutable[_CHECKSUM_OFFSET:] = b"\x00" * 4
        if (
            magic != _MAGIC
            or version != _VERSION
            or clean not in {0, 1}
            or reserved != 0
            or zlib.crc32(mutable) & 0xFFFFFFFF != stored_crc
        ):
            raise CorruptWal("control file checksum or header is invalid")
        return ControlState(checkpoint_lsn, bool(clean))

    def store(self, state: ControlState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = bytearray(
            _STRUCT.pack(
                _MAGIC,
                _VERSION,
                int(state.clean_shutdown),
                0,
                state.checkpoint_lsn,
                0,
            )
        )
        encoded[_CHECKSUM_OFFSET:] = (
            zlib.crc32(encoded) & 0xFFFFFFFF
        ).to_bytes(4, "big")
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            _write_all(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, self.path)
        directory = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _write_all(descriptor: int, data: bytes | bytearray) -> None:
    written = 0
    while written < len(data):
        count = os.write(descriptor, data[written:])
        if count <= 0:
            raise OSError("short control-file write")
        written += count

