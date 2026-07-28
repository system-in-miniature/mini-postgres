from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from minipostgres.sql.lexer import lex
from minipostgres.sql.tokens import TokenKind


@given(
    st.text(
        alphabet=st.characters(
            blacklist_categories=("Cs",),
            blacklist_characters="'\x00",
        )
    )
)
def test_quoted_string_round_trips(value: str) -> None:
    escaped = value.replace("'", "''")
    token = lex(f"'{escaped}'")[0]

    assert token.kind is TokenKind.STRING
    assert token.value == value


@given(st.integers(min_value=-(2**63), max_value=2**63 - 1))
def test_integer_literal_round_trips_magnitude(value: int) -> None:
    tokens = lex(str(value))

    if value < 0:
        assert tokens[0].kind is TokenKind.MINUS
        assert tokens[1].value == abs(value)
    else:
        assert tokens[0].kind is TokenKind.INTEGER
        assert tokens[0].value == value

