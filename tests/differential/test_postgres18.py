from __future__ import annotations

import os

import pytest

from minipostgres.differential.postgres import Postgres18


def test_configured_postgres18_profile_reports_literal_semantics() -> None:
    dsn = os.environ.get("MINIPOSTGRES_PG18_DSN")
    if dsn is None:
        pytest.skip("MINIPOSTGRES_PG18_DSN is not configured")
    try:
        postgres = Postgres18.connect(dsn)
    except ModuleNotFoundError:
        pytest.skip("install the postgres18 dependency group")
    try:
        assert postgres.execute(
            "SELECT 1 + 2, NULL IS NULL ORDER BY 1"
        ) == ((3, True),)
    finally:
        postgres.close()
