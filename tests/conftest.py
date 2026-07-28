from __future__ import annotations

from collections.abc import Iterator

import pytest

from minipostgres.engine import Database


@pytest.fixture
def engine(tmp_path) -> Iterator[Database]:
    with Database.open(tmp_path) as database:
        yield database
