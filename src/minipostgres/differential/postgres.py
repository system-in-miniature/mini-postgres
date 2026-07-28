"""Explicit PostgreSQL 18 differential adapter."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Postgres18:
    connection: Any

    @classmethod
    def connect(cls, dsn: str) -> Postgres18:
        psycopg = importlib.import_module("psycopg")
        connection = psycopg.connect(dsn)
        with connection.cursor() as cursor:
            cursor.execute("SHOW server_version_num")
            row = cursor.fetchone()
        version = 0 if row is None else int(row[0])
        if not 180000 <= version <= 189999:
            connection.close()
            raise RuntimeError(
                f"PostgreSQL 18 required; server_version_num={version}"
            )
        return cls(connection)

    def execute(self, sql: str) -> tuple[tuple[object, ...], ...]:
        with self.connection.cursor() as cursor:
            cursor.execute(sql)
            if cursor.description is None:
                self.connection.commit()
                return ()
            return tuple(tuple(row) for row in cursor.fetchall())

    def close(self) -> None:
        self.connection.close()
