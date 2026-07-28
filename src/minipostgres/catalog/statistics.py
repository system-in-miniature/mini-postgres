"""Immutable planner statistics and atomic versioned persistence."""

from __future__ import annotations

import json
import math
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import cast

from minipostgres.errors import CatalogError
from minipostgres.types import Scalar, infer_type

STATISTICS_FORMAT_VERSION = 1


@dataclass(frozen=True, slots=True)
class ColumnStatistics:
    """One exact educational column distribution."""

    null_fraction: float
    distinct_count: int
    min_value: Scalar
    max_value: Scalar
    most_common_values: tuple[tuple[Scalar, float], ...]
    histogram_bounds: tuple[Scalar, ...]

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.null_fraction)
            or not 0.0 <= self.null_fraction <= 1.0
        ):
            raise CatalogError("statistics fraction must be between zero and one")
        if type(self.distinct_count) is not int or self.distinct_count < 0:
            raise CatalogError("statistics distinct count must be nonnegative")
        frequencies = [frequency for _, frequency in self.most_common_values]
        if any(
            not math.isfinite(frequency) or frequency <= 0 or frequency > 1
            for frequency in frequencies
        ) or sum(frequencies) > 1.0 + 1e-12:
            raise CatalogError("MCV frequencies must total no more than one")
        values = [
            value
            for value in (
                self.min_value,
                self.max_value,
                *(value for value, _ in self.most_common_values),
                *self.histogram_bounds,
            )
            if value is not None
        ]
        types = {infer_type(value) for value in values}
        if len(types) > 1:
            raise CatalogError("statistics values have incompatible types")
        if (self.min_value is None) != (self.max_value is None):
            raise CatalogError("statistics extrema must both be present or absent")
        try:
            if (
                self.min_value is not None
                and self.max_value is not None
                and self.min_value > self.max_value  # type: ignore[operator]
            ):
                raise CatalogError("statistics extrema are not ordered")
            if any(
                left > right  # type: ignore[operator]
                for left, right in zip(
                    self.histogram_bounds,
                    self.histogram_bounds[1:],
                    strict=False,
                )
            ):
                raise CatalogError("statistics histogram is not ordered")
        except TypeError as error:
            raise CatalogError("statistics values are not order-compatible") from error

    @property
    def mcv_fraction(self) -> float:
        return sum(frequency for _, frequency in self.most_common_values)

    @property
    def mcv_count(self) -> int:
        return len(self.most_common_values)


@dataclass(frozen=True, slots=True)
class TableStatistics:
    """Immutable statistics for one stable catalog table ID."""

    table_id: int
    row_count: int
    page_count: int
    columns: Mapping[int, ColumnStatistics]

    def __post_init__(self) -> None:
        if type(self.table_id) is not int or self.table_id <= 0:
            raise CatalogError("statistics table ID must be positive")
        if type(self.row_count) is not int or self.row_count < 0:
            raise CatalogError("statistics row count must be nonnegative")
        if type(self.page_count) is not int or self.page_count < 0:
            raise CatalogError("statistics page count must be nonnegative")
        columns = dict(self.columns)
        if any(type(column_id) is not int or column_id < 0 for column_id in columns):
            raise CatalogError("statistics column IDs must be nonnegative")
        object.__setattr__(self, "columns", MappingProxyType(columns))


class StatisticsStore:
    """Thread-safe atomic store separate from authoritative catalog metadata."""

    def __init__(
        self,
        root: Path,
        tables: Mapping[int, TableStatistics] | None = None,
    ) -> None:
        self._root = root
        self._path = root / "statistics.json"
        self._tables = dict(tables or {})
        self._lock = threading.RLock()

    @classmethod
    def open(cls, root: str | Path) -> StatisticsStore:
        root_path = Path(root)
        root_path.mkdir(parents=True, exist_ok=True)
        (root_path / "statistics.json.tmp").unlink(missing_ok=True)
        path = root_path / "statistics.json"
        if not path.exists():
            return cls(root_path)
        try:
            loaded: object = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise CatalogError("statistics root must be an object")
            document = cast(dict[str, object], loaded)
            if _required_int(document, "format_version") != STATISTICS_FORMAT_VERSION:
                raise CatalogError("unsupported statistics format version")
            raw_tables = document["tables"]
            if not isinstance(raw_tables, list):
                raise CatalogError("statistics tables must be a list")
            table_documents = cast(list[object], raw_tables)
            tables = tuple(
                _table_from_document(cast(dict[str, object], item))
                for item in table_documents
                if isinstance(item, dict)
            )
            if len(tables) != len(table_documents):
                raise CatalogError("invalid table statistics entry")
            mapping = {table.table_id: table for table in tables}
            if len(mapping) != len(tables):
                raise CatalogError("duplicate table statistics")
            return cls(root_path, mapping)
        except (
            CatalogError,
            KeyError,
            OSError,
            UnicodeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            if isinstance(error, CatalogError):
                raise
            raise CatalogError("invalid statistics metadata") from error

    def table(self, table_id: int) -> TableStatistics | None:
        with self._lock:
            return self._tables.get(table_id)

    def replace(self, statistics: TableStatistics) -> None:
        """Atomically replace one complete table-statistics snapshot."""

        with self._lock:
            previous = self._tables.get(statistics.table_id)
            self._tables[statistics.table_id] = statistics
            try:
                self._persist()
            except BaseException:
                if previous is None:
                    del self._tables[statistics.table_id]
                else:
                    self._tables[statistics.table_id] = previous
                raise

    def _persist(self) -> None:
        document = {
            "format_version": STATISTICS_FORMAT_VERSION,
            "tables": [
                _table_to_document(table)
                for _, table in sorted(self._tables.items())
            ],
        }
        encoded = (
            json.dumps(
                document,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode()
        temporary = self._root / "statistics.json.tmp"
        try:
            with temporary.open("wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
            directory = os.open(self._root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise CatalogError("failed to persist statistics") from error


def _required_int(document: dict[str, object], key: str) -> int:
    value = document[key]
    if type(value) is not int:
        raise CatalogError(f"invalid statistics integer field: {key}")
    return value


def _required_float(document: dict[str, object], key: str) -> float:
    value = document[key]
    if type(value) is int:
        return float(value)
    if type(value) is float:
        return value
    raise CatalogError(f"invalid statistics float field: {key}")


def _scalar_to_document(value: Scalar) -> dict[str, object]:
    if value is None:
        return {"type": "null"}
    if type(value) is bool:
        return {"type": "boolean", "value": value}
    if type(value) is int:
        return {"type": "int64", "value": str(value)}
    if type(value) is float:
        return {"type": "float64", "value": repr(value)}
    return {"type": "text", "value": value}


def _scalar_from_document(document: object) -> Scalar:
    if not isinstance(document, dict):
        raise CatalogError("invalid typed statistics scalar")
    typed = cast(dict[str, object], document)
    scalar_type = typed.get("type")
    if scalar_type == "null":
        return None
    value = typed.get("value")
    if scalar_type == "boolean" and type(value) is bool:
        return value
    if scalar_type == "int64" and isinstance(value, str):
        return int(value)
    if scalar_type == "float64" and isinstance(value, str):
        return float(value)
    if scalar_type == "text" and isinstance(value, str):
        return value
    raise CatalogError("invalid typed statistics scalar")


def _table_to_document(table: TableStatistics) -> dict[str, object]:
    return {
        "columns": [
            {
                "column_id": column_id,
                "distinct_count": statistics.distinct_count,
                "histogram_bounds": [
                    _scalar_to_document(value)
                    for value in statistics.histogram_bounds
                ],
                "max_value": _scalar_to_document(statistics.max_value),
                "min_value": _scalar_to_document(statistics.min_value),
                "most_common_values": [
                    {
                        "frequency": frequency,
                        "value": _scalar_to_document(value),
                    }
                    for value, frequency in statistics.most_common_values
                ],
                "null_fraction": statistics.null_fraction,
            }
            for column_id, statistics in sorted(table.columns.items())
        ],
        "page_count": table.page_count,
        "row_count": table.row_count,
        "table_id": table.table_id,
    }


def _table_from_document(document: dict[str, object]) -> TableStatistics:
    raw_columns = document["columns"]
    if not isinstance(raw_columns, list):
        raise CatalogError("statistics columns must be a list")
    columns: dict[int, ColumnStatistics] = {}
    for item in cast(list[object], raw_columns):
        if not isinstance(item, dict):
            raise CatalogError("invalid column statistics")
        column = cast(dict[str, object], item)
        column_id = _required_int(column, "column_id")
        raw_mcv = column["most_common_values"]
        raw_histogram = column["histogram_bounds"]
        if not isinstance(raw_mcv, list) or not isinstance(raw_histogram, list):
            raise CatalogError("invalid distribution statistics")
        mcv: list[tuple[Scalar, float]] = []
        for raw_entry in cast(list[object], raw_mcv):
            if not isinstance(raw_entry, dict):
                raise CatalogError("invalid MCV statistics")
            entry = cast(dict[str, object], raw_entry)
            mcv.append(
                (
                    _scalar_from_document(entry["value"]),
                    _required_float(entry, "frequency"),
                )
            )
        columns[column_id] = ColumnStatistics(
            _required_float(column, "null_fraction"),
            _required_int(column, "distinct_count"),
            _scalar_from_document(column["min_value"]),
            _scalar_from_document(column["max_value"]),
            tuple(mcv),
            tuple(
                _scalar_from_document(value)
                for value in cast(list[object], raw_histogram)
            ),
        )
    return TableStatistics(
        _required_int(document, "table_id"),
        _required_int(document, "row_count"),
        _required_int(document, "page_count"),
        columns,
    )
