from __future__ import annotations

import math

from hypothesis import given
from hypothesis import strategies as st

from minipostgres.catalog.model import Column, Schema
from minipostgres.row import TID
from minipostgres.storage.tuple import TupleCodec, TupleVersion
from minipostgres.types import DataType

_SCHEMA = Schema.create(
    (
        Column("number", DataType.INT64),
        Column("ratio", DataType.FLOAT64),
        Column("flag", DataType.BOOLEAN),
        Column("text", DataType.TEXT),
    )
)
_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    max_size=128,
)


@given(
    integer=st.one_of(st.none(), st.integers(-(2**63), 2**63 - 1)),
    floating=st.one_of(
        st.none(),
        st.floats(allow_nan=False, allow_infinity=False, width=64),
    ),
    boolean=st.one_of(st.none(), st.booleans()),
    text=st.one_of(st.none(), _TEXT),
    xmin=st.integers(0, 2**64 - 1),
    xmax=st.integers(0, 2**64 - 1),
    next_page=st.integers(0, 100),
    next_slot=st.integers(0, 100),
)
def test_tuple_codec_round_trips_supported_scalar_domains(
    integer: int | None,
    floating: float | None,
    boolean: bool | None,
    text: str | None,
    xmin: int,
    xmax: int,
    next_page: int,
    next_slot: int,
) -> None:
    version = TupleVersion(
        xmin=xmin,
        xmax=xmax,
        next_tid=TID(next_page, next_slot),
        values=(integer, floating, boolean, text),
    )

    decoded = TupleCodec(_SCHEMA).decode(TupleCodec(_SCHEMA).encode(version))

    assert decoded == version
    if floating is not None:
        assert math.copysign(1.0, decoded.values[1]) == math.copysign(
            1.0, floating
        )
