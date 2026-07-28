from __future__ import annotations

import pytest

from minipostgres.engine import Database
from minipostgres.errors import BindError, TransactionAborted


def test_begin_commit_and_rollback_are_session_owned(engine: Database) -> None:
    session = engine.session()
    assert session.execute("BEGIN").command_tag == "BEGIN"
    assert session.execute("SELECT 1").rows == ((1,),)
    assert session.execute("COMMIT").command_tag == "COMMIT"
    assert session.execute("BEGIN").command_tag == "BEGIN"
    assert session.execute("ROLLBACK").command_tag == "ROLLBACK"


def test_failed_explicit_transaction_accepts_only_rollback(
    engine: Database,
) -> None:
    engine.execute("CREATE TABLE users (id INT)")
    session = engine.session()
    session.execute("BEGIN")
    with pytest.raises(BindError):
        session.execute("SELECT missing FROM users")
    with pytest.raises(TransactionAborted):
        session.execute("SELECT 1")
    assert session.execute("ROLLBACK").command_tag == "ROLLBACK"
