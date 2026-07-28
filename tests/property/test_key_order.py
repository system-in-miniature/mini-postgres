from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from minipostgres.index.key import KeyCodec
from minipostgres.types import DataType

_INT_CODEC = KeyCodec((DataType.INT64,))
_FLOAT_CODEC = KeyCodec((DataType.FLOAT64,))
_TEXT_CODEC = KeyCodec((DataType.TEXT,))


@given(
    st.lists(
        st.integers(-(2**63), 2**63 - 1),
        max_size=100,
        unique=True,
    )
)
def test_encoded_int64_order_matches_numeric_order(values: list[int]) -> None:
    assert sorted(values, key=lambda value: _INT_CODEC.encode((value,))) == sorted(
        values
    )


@given(
    st.lists(
        st.floats(
            allow_nan=False,
            allow_infinity=True,
            width=64,
        ).filter(lambda value: value != 0.0),
        max_size=100,
        unique=True,
    )
)
def test_encoded_float64_order_matches_numeric_order(values: list[float]) -> None:
    assert sorted(
        values,
        key=lambda value: _FLOAT_CODEC.encode((value,)),
    ) == sorted(values)


@given(
    st.lists(
        st.text(
            alphabet=st.characters(blacklist_categories=("Cs",)),
            max_size=30,
        ),
        max_size=80,
        unique=True,
    )
)
def test_encoded_text_order_matches_unicode_order(values: list[str]) -> None:
    assert sorted(values, key=lambda value: _TEXT_CODEC.encode((value,))) == sorted(
        values
    )
