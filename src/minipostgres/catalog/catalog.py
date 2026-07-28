"""Durable, atomically replaced MiniPostgres catalog."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import cast

from minipostgres.catalog.model import (
    Column,
    IndexMetadata,
    Schema,
    TableMetadata,
)
from minipostgres.errors import CatalogError

CATALOG_FORMAT_VERSION = 1


def _catalog_int(document: dict[str, object], key: str) -> int:
    try:
        value = document[key]
    except KeyError as error:
        raise CatalogError(f"missing catalog field: {key}") from error
    if type(value) is not int:
        raise CatalogError(f"invalid catalog integer field: {key}")
    return value


class Catalog:
    """Own stable catalog identities and deterministic JSON persistence."""

    def __init__(
        self,
        root: Path,
        *,
        next_table_id: int = 1,
        next_index_id: int = 1,
        tables: tuple[TableMetadata, ...] = (),
        indexes: tuple[IndexMetadata, ...] = (),
    ) -> None:
        self._root = root
        self._path = root / "catalog.json"
        self._next_table_id = next_table_id
        self._next_index_id = next_index_id
        self._tables_by_id = {table.table_id: table for table in tables}
        self._table_names = {
            table.normalized_name: table.table_id for table in tables
        }
        self._indexes_by_id = {index.index_id: index for index in indexes}
        self._index_names = {
            index.normalized_name: index.index_id for index in indexes
        }
        self._lock = threading.RLock()
        if len(self._tables_by_id) != len(tables) or len(self._table_names) != len(
            tables
        ):
            raise CatalogError("duplicate table metadata")
        if len(self._indexes_by_id) != len(indexes) or len(
            self._index_names
        ) != len(indexes):
            raise CatalogError("duplicate index metadata")
        for index in indexes:
            table = self._tables_by_id.get(index.table_id)
            if table is None:
                raise CatalogError("index refers to an unknown table")
            if not index.column_ids or any(
                column_id < 0 or column_id >= len(table.schema.columns)
                for column_id in index.column_ids
            ):
                raise CatalogError("index refers to an unknown column")

    @classmethod
    def open(cls, root: str | Path) -> Catalog:
        root_path = Path(root)
        root_path.mkdir(parents=True, exist_ok=True)
        temporary = root_path / "catalog.json.tmp"
        temporary.unlink(missing_ok=True)
        path = root_path / "catalog.json"
        if not path.exists():
            return cls(root_path)
        try:
            loaded: object = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CatalogError("invalid catalog JSON") from error
        if not isinstance(loaded, dict):
            raise CatalogError("catalog root must be an object")
        document = cast(dict[str, object], loaded)
        version = _catalog_int(document, "format_version")
        if version != CATALOG_FORMAT_VERSION:
            raise CatalogError(f"unsupported catalog format version: {version}")
        try:
            raw_tables = document["tables"]
            raw_indexes = document["indexes"]
            if not isinstance(raw_tables, list) or not isinstance(raw_indexes, list):
                raise CatalogError("catalog tables and indexes must be lists")
            table_documents = cast(list[object], raw_tables)
            index_documents = cast(list[object], raw_indexes)
            tables_list: list[TableMetadata] = []
            indexes_list: list[IndexMetadata] = []
            for item in table_documents:
                if not isinstance(item, dict):
                    raise CatalogError("invalid table metadata")
                tables_list.append(
                    TableMetadata.from_document(cast(dict[str, object], item))
                )
            for item in index_documents:
                if not isinstance(item, dict):
                    raise CatalogError("invalid index metadata")
                indexes_list.append(
                    IndexMetadata.from_document(cast(dict[str, object], item))
                )
            return cls(
                root_path,
                next_table_id=_catalog_int(document, "next_table_id"),
                next_index_id=_catalog_int(document, "next_index_id"),
                tables=tuple(tables_list),
                indexes=tuple(indexes_list),
            )
        except (CatalogError, KeyError) as error:
            raise CatalogError("invalid catalog metadata") from error

    def table(self, name_or_id: str | int) -> TableMetadata:
        with self._lock:
            if isinstance(name_or_id, str):
                table_id = self._table_names.get(name_or_id.casefold())
                if table_id is None:
                    raise CatalogError(f"unknown table: {name_or_id}")
            else:
                table_id = name_or_id
            try:
                return self._tables_by_id[table_id]
            except KeyError as error:
                raise CatalogError(f"unknown table ID: {table_id}") from error

    def tables(self) -> tuple[TableMetadata, ...]:
        with self._lock:
            return tuple(self._tables_by_id.values())

    def index(self, name_or_id: str | int) -> IndexMetadata:
        """Resolve one published index by case-insensitive name or stable ID."""

        with self._lock:
            if isinstance(name_or_id, str):
                index_id = self._index_names.get(name_or_id.casefold())
                if index_id is None:
                    raise CatalogError(f"unknown index: {name_or_id}")
            else:
                index_id = name_or_id
            try:
                return self._indexes_by_id[index_id]
            except KeyError as error:
                raise CatalogError(f"unknown index ID: {index_id}") from error

    def indexes(self, table_id: int | None = None) -> tuple[IndexMetadata, ...]:
        """Return published indexes, optionally restricted to one table."""

        with self._lock:
            return tuple(
                index
                for index in self._indexes_by_id.values()
                if table_id is None or index.table_id == table_id
            )

    def prepare_table(
        self,
        name: str,
        columns: tuple[Column, ...],
    ) -> TableMetadata:
        """Validate and assign the next table ID without publishing metadata."""

        normalized = name.casefold()
        if not name or "\x00" in name:
            raise CatalogError("table name must be non-empty and contain no NUL")
        with self._lock:
            if normalized in self._table_names:
                raise CatalogError(f"table already exists: {name}")
            return TableMetadata(
                table_id=self._next_table_id,
                name=name,
                schema=Schema.create(columns),
            )

    def publish_table(self, metadata: TableMetadata) -> None:
        """Atomically publish physically prepared table metadata."""

        normalized = metadata.normalized_name
        with self._lock:
            if metadata.table_id != self._next_table_id:
                raise CatalogError("table publication uses a stale table ID")
            if normalized in self._table_names:
                raise CatalogError(f"table already exists: {metadata.name}")
            self._tables_by_id[metadata.table_id] = metadata
            self._table_names[normalized] = metadata.table_id
            self._next_table_id += 1
            try:
                self._persist()
            except Exception:
                self._next_table_id -= 1
                del self._tables_by_id[metadata.table_id]
                del self._table_names[normalized]
                raise

    def create_table(
        self,
        name: str,
        columns: tuple[Column, ...],
    ) -> TableMetadata:
        metadata = self.prepare_table(name, columns)
        self.publish_table(metadata)
        return metadata

    def prepare_index(
        self,
        name: str,
        table_id: int,
        column_ids: tuple[int, ...],
        *,
        unique: bool,
    ) -> IndexMetadata:
        """Validate and assign an index ID without publishing metadata."""

        normalized = name.casefold()
        if not name or "\x00" in name:
            raise CatalogError("index name must be non-empty and contain no NUL")
        with self._lock:
            if normalized in self._index_names:
                raise CatalogError(f"index already exists: {name}")
            table = self.table(table_id)
            if not column_ids:
                raise CatalogError("index requires at least one column")
            if len(set(column_ids)) != len(column_ids):
                raise CatalogError("index columns must be distinct")
            for column_id in column_ids:
                table.schema.column(column_id)
            return IndexMetadata(
                self._next_index_id,
                table_id,
                name,
                column_ids,
                unique,
            )

    def publish_index(self, metadata: IndexMetadata) -> None:
        """Atomically publish a fully built and synced physical index."""

        normalized = metadata.normalized_name
        with self._lock:
            if metadata.index_id != self._next_index_id:
                raise CatalogError("index publication uses a stale index ID")
            if normalized in self._index_names:
                raise CatalogError(f"index already exists: {metadata.name}")
            self.table(metadata.table_id)
            self._indexes_by_id[metadata.index_id] = metadata
            self._index_names[normalized] = metadata.index_id
            self._next_index_id += 1
            try:
                self._persist()
            except Exception:
                self._next_index_id -= 1
                del self._indexes_by_id[metadata.index_id]
                del self._index_names[normalized]
                raise

    def _document(self) -> dict[str, object]:
        return {
            "format_version": CATALOG_FORMAT_VERSION,
            "indexes": [
                index.to_document() for index in self._indexes_by_id.values()
            ],
            "next_index_id": self._next_index_id,
            "next_table_id": self._next_table_id,
            "tables": [table.to_document() for table in self._tables_by_id.values()],
        }

    def _persist(self) -> None:
        temporary = self._root / "catalog.json.tmp"
        encoded = (
            json.dumps(
                self._document(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()
        try:
            with temporary.open("wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
            directory_fd = os.open(self._root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise CatalogError("failed to persist catalog") from error
