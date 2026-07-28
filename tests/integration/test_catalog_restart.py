from __future__ import annotations

import json
from pathlib import Path

import pytest

from minipostgres.catalog.catalog import Catalog
from minipostgres.catalog.model import Column
from minipostgres.errors import CatalogError
from minipostgres.types import DataType


def test_catalog_assigns_stable_ids_and_survives_restart(tmp_path: Path) -> None:
    catalog = Catalog.open(tmp_path)
    users = catalog.create_table(
        "users",
        (
            Column("id", DataType.INT64, nullable=False),
            Column("name", DataType.TEXT),
        ),
    )
    orders = catalog.create_table(
        "orders",
        (Column("id", DataType.INT64, primary_key=True),),
    )

    reopened = Catalog.open(tmp_path)

    assert reopened.table("users") == users
    assert reopened.table(users.table_id).schema.column("name").column_id == 1
    assert orders.table_id == users.table_id + 1


def test_catalog_rejects_duplicate_names_case_insensitively(tmp_path: Path) -> None:
    catalog = Catalog.open(tmp_path)
    catalog.create_table("Users", (Column("id", DataType.INT64),))

    with pytest.raises(CatalogError, match="table already exists"):
        catalog.create_table("users", (Column("other", DataType.INT64),))


def test_catalog_json_is_versioned_and_deterministic(tmp_path: Path) -> None:
    catalog = Catalog.open(tmp_path)
    catalog.create_table("zeta", (Column("id", DataType.INT64),))
    catalog.create_table("alpha", (Column("id", DataType.INT64),))

    raw = (tmp_path / "catalog.json").read_text(encoding="utf-8")
    document = json.loads(raw)

    assert document["format_version"] == 1
    assert raw.endswith("\n")
    assert [table["name"] for table in document["tables"]] == ["zeta", "alpha"]
    assert not (tmp_path / "catalog.json.tmp").exists()


def test_catalog_fails_closed_on_invalid_metadata(tmp_path: Path) -> None:
    (tmp_path / "catalog.json").write_text('{"format_version": 99}\n')

    with pytest.raises(CatalogError, match="format version"):
        Catalog.open(tmp_path)

