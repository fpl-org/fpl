"""FON data reads what it writes, within its bounds, and refuses everything else in place."""

import math
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.errors import FplError
from fpl.fon import (
    Absent,
    Bool,
    Cell,
    Code,
    Dict,
    Flt,
    Hash,
    Json,
    Leaf,
    List,
    Num,
    Str,
    Sym,
    Tagged,
    Value,
    embed,
    read,
    write,
)

SPECIALS = r"\s\[\]()“”「」⟦⟧⟨⟩{}|⍝¶"
NAMES = ("true", "false", "∞", "-∞", "nan", "-nan")

symbol = st.from_regex(r"[a-z][a-z0-9-]{0,7}", fullmatch=True).map(Sym)
token = (
    st.from_regex(rf"[^{SPECIALS}$#&_0-9-][^{SPECIALS}]{{0,7}}", fullmatch=True)
    .filter(lambda name: name not in NAMES)
    .map(Sym)
)
number = st.decimals(allow_nan=False, allow_infinity=False, places=3).map(
    lambda d: Num(Decimal(format(d, "f")))
)
text = st.text(alphabet=st.characters(exclude_characters="“”"), max_size=12)
string = st.one_of(
    text.map(Str),
    st.text(alphabet=st.characters(exclude_characters="「」"), max_size=12).map(
        lambda raw: Str(raw, raw=True)
    ),
)
floats = st.one_of(st.floats(allow_nan=False), st.sampled_from([math.nan, -math.nan])).map(Flt.of)
leaf: st.SearchStrategy[Leaf] = st.one_of(
    st.just(Absent()),
    st.booleans().map(Bool),
    number,
    floats,
    symbol,
    token,
    string,
    symbol.map(lambda s: Cell(s.name)),
    st.from_regex(r"[0-9a-f]{6,12}", fullmatch=True).map(Hash),
)
key: st.SearchStrategy[Leaf] = st.one_of(symbol, number, string)


def nested(inner: st.SearchStrategy[Value]) -> st.SearchStrategy[Value]:
    """Lists, tagged tuples, code and dicts of `inner`."""
    items = st.lists(inner, max_size=4).map(tuple)
    entries = st.lists(st.tuples(key, inner), max_size=4, unique_by=lambda entry: entry[0])
    return st.one_of(
        items.map(List), items.map(Tagged), items.map(Code), entries.map(lambda e: Dict(tuple(e)))
    )


value: st.SearchStrategy[Value] = st.recursive(leaf, nested, max_leaves=12)
json: st.SearchStrategy[Json] = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
        text,
    ),
    lambda inner: st.one_of(st.lists(inner, max_size=4), st.dictionaries(text, inner, max_size=4)),
    max_leaves=12,
)


def refusal(document: str, **bounds: int) -> str:
    """The error line reading gives."""
    with pytest.raises(FplError) as caught:
        read(document, **bounds)
    return str(caught.value)


@given(value)
def test_read_after_write_is_the_identity(v: Value) -> None:
    """read ∘ write = id on values, and write is idempotent on the text it gives."""
    written = write(v)
    assert read(written) == v
    assert write(read(written)) == written


@given(json)
def test_json_embeds_and_reads_back(j: Json) -> None:
    """A JSON value holding no “ or ” in its texts embeds and reads back (HOLES.md:
    fon-unwritable)."""
    embedded = embed(j)
    assert read(write(embedded)) == embedded


@pytest.mark.parametrize(
    ("document", "error"),
    [
        ("{ a 1 a 2 }", "ERROR: 1:7 repeated key a"),
        ("⟨ 1 ⟨ 2 ⟩", "ERROR: 1:1 ⟨ never closed"),
        ("“a 「b” c」", "ERROR: 1:9 」 closes nothing"),
        ("&zz", "ERROR: 1:1 malformed hash reference &zz"),
        ("⟨" * 70 + "⟩" * 70, "ERROR: 1:65 nesting too deep"),
        ("01", "ERROR: 1:1 non-canonical number 01"),
        ("1e5", "ERROR: 1:1 non-canonical number 1e5"),
        ("“a", "ERROR: 1:1 “ never closed"),
        ("⟨ a }\n⟩", "ERROR: 1:5 unexpected input"),
        ("a | b", "ERROR: 1:3 unexpected input"),
    ],
)
def test_the_profile_refuses_in_place(document: str, error: str) -> None:
    assert refusal(document) == error


def test_the_bounds_are_parameters() -> None:
    assert refusal("⟨ ⟨ ⟩ ⟩", max_depth=1) == "ERROR: 1:3 nesting too deep"
    assert refusal("a\nabcd", max_token=3) == "ERROR: 2:1 token too long"
    assert refusal("abc", max_size=2) == "ERROR: 1:3 input too large"
    assert read("“" + "a" * 10 + "”", max_token=3) == Str("a" * 10)


@pytest.mark.parametrize(
    ("x", "spelled"),
    [
        (12.0, "0x1.8p3"),
        (-0.0, "-0x0p0"),
        (5e-324, "0x0.0000000000001p-1022"),
        (math.inf, "∞"),
        (-math.inf, "-∞"),
        (math.nan, "nan"),
        (-math.nan, "-nan"),
    ],
)
def test_a_float_is_its_bits(x: float, spelled: str) -> None:
    assert write(Flt.of(x)) == spelled
    assert read(spelled) == Flt.of(x)


def test_the_reader_is_inert() -> None:
    """Names, references, tuples and code are data; nothing is resolved or called."""
    assert read("( p { class “x” } 「r」 $c &abcdef #s )") == Tagged(
        (
            Sym("p"),
            Dict(((Sym("class"), Str("x")),)),
            Str("r", raw=True),
            Cell("c"),
            Hash("abcdef"),
            Sym("s"),
        )
    )
    assert read("[ dup + →k ; ]") == Code((Sym("dup"), Sym("+"), Sym("→k"), Sym(";")))
    assert read("  a\n\t_ ") == List((Sym("a"), Absent()))
    assert read("") == List(())


def test_empty_enclosures_are_written_canonically() -> None:
    assert [write(v) for v in (List(()), Tagged(()), Code(()), Dict(()))] == [
        "⟨⟩",
        "( )",
        "[ ]",
        "{ }",
    ]


def test_json_keys_are_symbols_where_they_can_be() -> None:
    assert embed({"name": "Ada", "a b": None, "1": [1.5, True]}) == Dict(
        (
            (Sym("name"), Str("Ada")),
            (Str("a b"), Absent()),
            (Str("1"), List((Num(Decimal("1.5")), Bool(True)))),
        )
    )
