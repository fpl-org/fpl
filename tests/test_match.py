"""match: one-way, first row wins, patterns the inverses of injective constructors (draft4 §1-5;
the campaign's 06-match scope)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.driver import run
from fpl.errors import FplError, Span

SHAPES = (
    "circle : r -- shape\n\t#circle swap pair\n"
    "rect : w h -- shape\n\t#rect swap pair pair\n"
    "nonzero : x -- b\n\tmatch\n\t\t0\t0\n\t\t_\t1\n"
    "area : shape -- n\n\tmatch\n"
    "\t\t( circle r ∈ nonzero )\tr dup times\n"
    "\t\t( circle 0 )\t#empty\n"
    "\t\t( rect w h )\tw h times\n"
)


def test_rotation_puts_the_head_after_its_arguments() -> None:
    """[D2.11] [D2.12] (+ 1 2) is 1 | 2 +, and (+ (times 2 3) 4) is 2 | 3 times | 4 +."""
    assert run("(+ 1 2)\n(+ (times 2 3) 4)\n") == "3\n10\n"


def test_a_constructor_runs_backwards_through_its_composition() -> None:
    """[D4.1] circle and rect are #tag swap pair (pair): their patterns undo the pairs, the
    swap and the tag, binding the arguments for the row's body."""
    assert run(f"{SHAPES}3 circle area\n2 | 3 rect area\n") == "9\n6\n"


def test_a_guard_is_an_ascription_and_a_literal_matches_by_equality() -> None:
    """[D4.1] [D4.2] r ∈ nonzero guards the first row, so 0 falls to ( circle 0 ), which
    matches the literal by equality."""
    assert run(f"{SHAPES}0 circle area\n") == "#empty\n"


def test_a_constructor_value_is_its_pair() -> None:
    """pair builds a two-item list (hole pair-shape); cons puts an item before a list, and
    refuses anything else."""
    assert run(f"{SHAPES}3 circle\n1 ⟨ 2 ⟩ cons\n") == "⟨ #circle 3 ⟩\n⟨ 1 2 ⟩\n"
    with pytest.raises(FplError) as refused:
        run("1 | 2 cons\n")
    assert (refused.value.span, refused.value.message) == (Span(1, 7), "cons takes a list")


def test_a_relation_succeeds_on_a_row_and_fails_off_every_row() -> None:
    """[D4.7] [D4.8] two pattern cells and an empty body: outside a space the match is one-way
    and deterministic; a row that matches succeeds and leaves nothing, none raises +fail."""
    family = "family/\n\tparent : x y --\n\t\tmatch\n\t\t\t#tom\t#bob\n\t\t\t#bob\t#ann\n"
    assert run(f"{family}#bob #ann family/parent\n") == ""
    with pytest.raises(FplError) as failed:
        run(f"{family}#ann #bob family/parent\n")
    assert (failed.value.span, failed.value.message) == (Span(3, 3), "no row matches")


def test_a_symmetric_case_delegates() -> None:
    """[D4.4] patterns on every argument, each guarded; the swapped case calls the word again.
    The match takes its arguments, so the delegating row names them (the Draft's swap collide
    reads values the match took: a decision relayed to design)."""
    source = (
        "ship : x -- b\n\tmatch\n\t\t#ship\t1\n\t\t_\t0\n"
        "rock : x -- b\n\tmatch\n\t\t#rock\t1\n\t\t_\t0\n"
        "collide : a b -- o\n\tmatch\n"
        "\t\t( _ ∈ rock )\t( _ ∈ ship )\t#boom\n"
        "\t\t( a ∈ ship )\t( b ∈ rock )\tb a collide\n"
        "\t\t_\t_\t#miss\n"
        "#rock #ship collide\n#ship #rock collide\n#ship #ship collide\n"
    )
    assert run(source) == "#boom\n#boom\n#miss\n"


def test_a_pinned_name_matches_its_current_value() -> None:
    """[D4.6] $y matches the value y names, here bound by the row's first cell; ( cons _ rest )
    undoes cons."""
    has = (
        "has : x xs -- b\n\tmatch\n"
        "\t\t_\t⟨⟩\t0\n"
        "\t\ty\t( cons $y _ )\t1\n"
        "\t\ty\t( cons _ rest )\ty rest has\n"
    )
    assert run(f"{has}2 ⟨ 1 2 3 ⟩ has\n4 ⟨ 1 2 3 ⟩ has\n") == "1\n0\n"


@pytest.mark.parametrize(
    ("pattern", "col"), [("( dup x )", 5), ("( twice x )", 5), ("( loop x )", 5)]
)
def test_only_an_invertible_word_is_a_pattern(pattern: str, col: int) -> None:
    """A constructor is a composition of invertible primitives; any other word as a pattern is
    refused where it is written, when its row is tried."""
    source = (
        "twice : x -- y\n\tdup +\nloop : x -- y\n\tloop\n"
        f"f : x -- y\n\tmatch\n\t\t{pattern}\tx\n1 f\n"
    )
    with pytest.raises(FplError) as refused:
        run(source)
    assert refused.value.span == Span(7, col)
    assert refused.value.message.endswith("is not invertible")


def test_a_binder_before_a_match_reaches_its_pins_and_bodies() -> None:
    """→k names the top for the match after it: $k pins it, a row that binds k anew shadows
    it from that pattern on."""
    source = (
        "nonzero : x -- b\n\tmatch\n\t\t0\t0\n\t\t_\t1\n"
        "near : x y -- b\n\t→k\n\tmatch\n"
        "\t\t( cons $k _ )\t#head\n"
        "\t\t( k ∈ nonzero )\tk\n"
        "\t\t_\t#no\n"
        "⟨ 3 4 ⟩ | 3 near\n⟨ 5 ⟩ | 3 near\n0 | 3 near\n"
    )
    assert run(source) == "#head\n⟨ 5 ⟩\n#no\n"


def test_a_match_is_not_written_back_as_code() -> None:
    """A shadowed body holding a match is refused when printed (hole resugar-match)."""
    twice = "f : x -- y\n\tmatch\n\t\t_\t1\n"
    with pytest.raises(FplError, match="no evaluator yet"):
        run(f"{twice}{twice}f/history\n")


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ("_\t_\t1", "a row is 1 patterns and a body"),
        ("_ | 1", "a row is 1 patterns and a body"),
        ("_\t1\n\t\t\t2", "a row is 1 patterns and a body"),
        ("( cons _ )", "cons takes 2 patterns"),
        ("( cons )", "cons takes 2 patterns"),
    ],
)
def test_a_row_holds_one_pattern_per_value_and_a_constructor_one_per_input(
    row: str, message: str
) -> None:
    """A row with more cells than the values and a body, more than one frame or a block, or a
    constructor pattern with other than one pattern per input, is refused where it is written."""
    with pytest.raises(FplError, match=message):
        run(f"f : x -- y\n\tmatch\n\t\t{row}\n")


cells = st.lists(st.one_of(st.just("_"), st.integers(0, 3).map(str)), min_size=1, max_size=6)


@given(cells, st.integers(0, 3))
def test_the_row_chosen_is_the_first_whose_patterns_match(patterns: list[str], value: int) -> None:
    """The first row whose pattern matches runs; with none, the match raises +fail."""
    rows = "".join(f"\t\t{p}\t{i} #row\n" for i, p in enumerate(patterns))
    first = next((i for i, p in enumerate(patterns) if p in ("_", str(value))), None)
    source = f"f : x -- y\n\tmatch\n{rows}{value} f\n"
    if first is None:
        with pytest.raises(FplError, match="no row matches"):
            run(source)
    else:
        assert run(source) == f"{first} #row\n"


rows = st.lists(
    st.lists(st.sampled_from(["_", "v", "0", "#a", "( cons _ _ )"]), min_size=2, max_size=2),
    min_size=1,
    max_size=4,
)


@given(rows)
def test_a_match_is_exhaustive_exactly_when_its_effect_has_no_fail(table: list[list[str]]) -> None:
    """[D4.5] a row of wildcards and names catches all; without one the match is partial and
    the word's effect carries +fail, as f/effect shows."""
    body = "".join("\t\t" + "\t".join(r) + "\n" for r in table)
    caught = any(all(p in ("_", "v") for p in r) for r in table)
    effect = "⟨ “a” “b” “--” “c” ⟩" if caught else "⟨ “a” “b” “--” “c” “+fail” ⟩"
    assert run(f"f : a b -- c\n\tmatch\n{body}f/effect\n") == run(f"{effect}\n")


@pytest.mark.parametrize(
    ("row", "span", "message"),
    [
        ("_ _\t1", Span(1, 1), "no evaluator yet"),
        ("( _ ∈ )\t1", Span(1, 1), "no evaluator yet"),
        ("{ a 1 }\t1", Span(1, 1), "no evaluator yet"),
        ("( [ 1 ] x )\t1", Span(1, 1), "no evaluator yet"),
        ("( bound ∈ )\t1", Span(1, 1), "no evaluator yet"),
        ("_\t_", Span(1, 1), "no evaluator yet"),
        ("( bound x )\t1", Span(5, 5), "a constructor is words and literals: not invertible"),
    ],
)
def test_what_is_no_pattern_is_refused(row: str, span: Span, message: str) -> None:
    """A cell holds one pattern; a dict is no literal; ∈ needs its test; _ names nothing in the
    body; a constructor is a word whose body is words and literals, never a binder, refused
    where the pattern names it."""
    with pytest.raises(FplError) as refused:
        run(f"bound : x -- y\n\t→v v\nf : x -- y\n\tmatch\n\t\t{row}\n1 f\n")
    assert (refused.value.span, refused.value.message) == (span, message)


def test_a_constructor_that_cannot_have_built_the_value_falls_through() -> None:
    """rect undoes one pair of a circle, not the second; #t swap cannot undo on one value."""
    kind = "sw : x -- y\n\t#t swap\nkind : s -- k\n\tmatch\n\t\t( rect w h )\t#rect\n"
    kind += "\t\t( sw x )\t#sw\n\t\t_\t#other\n"
    assert run(f"{SHAPES}{kind}3 circle kind\n") == "#other\n"


def test_a_match_reached_through_a_quotation_counts_its_values() -> None:
    """A quotation's body is not balanced ahead, so the match finds too few values when run."""
    with pytest.raises(FplError) as short:
        run("f : x -- y\n\tmatch\n\t\t_\t1\n[ f ] !\n")
    assert (short.value.span, short.value.message) == (Span(2, 2), "stack underflow")


def test_a_partial_match_under_a_binder_still_fails() -> None:
    """[D4.5] +fail reaches a match inside a binder's scope, and is raised at the match."""
    source = "g : x y -- c\n\t→k\n\tmatch\n\t\t0\tk\n"
    assert run(f"{source}g/effect\n") == run("⟨ “x” “y” “--” “c” “+fail” ⟩\n")
    with pytest.raises(FplError) as failed:
        run(f"{source}1 | 2 g\n")
    assert (failed.value.span, failed.value.message) == (Span(3, 2), "no row matches")


def test_a_row_name_shadows_the_binder_from_its_pattern_on() -> None:
    """[D4.6] →k reaches every row: $k after a name the row binds pins the binder's value, k
    bound anew pins its own, and a body that binds no k reads the binder's."""
    source = (
        "g : a b c -- r\n\t→k\n\tmatch\n"
        "\t\tk\t$k\t#same\n"
        "\t\ty\t$k\t#pinned\n"
        "\t\t_\t_\tk\n"
        "1 | 1 | 9 g\n1 | 9 | 9 g\n1 | 2 | 9 g\n"
    )
    assert run(source) == "#same\n#pinned\n9\n"


def test_guards_nest_and_a_guarded_pin_reads_its_name() -> None:
    """[D4.1] a guarded pattern may be guarded again; $y inside a guard is the value y bound
    earlier in the row."""
    nonzero = "nonzero : x -- b\n\tmatch\n\t\t0\t0\n\t\t_\t1\n"
    twice = "f : x -- y\n\tmatch\n\t\t( x ∈ nonzero ∈ nonzero )\tx\n\t\t_\t#zero\n"
    same = "g : a b -- c\n\tmatch\n\t\ty\t( $y ∈ nonzero )\t#same\n\t\t_\t_\t#diff\n"
    runs = "3 f\n0 f\n2 | 2 g\n2 | 3 g\n0 | 0 g\n"
    assert run(f"{nonzero}{twice}{same}{runs}") == "3\n#zero\n#same\n#diff\n#diff\n"


@pytest.mark.parametrize(
    ("pattern", "span", "message"),
    [
        ("( x ∈ + )", Span(5, 9), "stack underflow"),
        ("( twice x )", Span(5, 7), "+ is not invertible"),
    ],
)
def test_a_pattern_after_a_bound_name_is_refused_where_written(
    pattern: str, span: Span, message: str
) -> None:
    """A guard whose test fails, or a constructor that is not invertible, is reported at the
    pattern, also once a name bound before it is pinned in."""
    source = f"twice : x -- y\n\tdup +\nf : a b -- c\n\tmatch\n\t\ty\t{pattern}\tx\n1 | 2 f\n"
    with pytest.raises(FplError) as refused:
        run(source)
    assert (refused.value.span, refused.value.message) == (span, message)


def test_a_line_after_a_match_counts_from_nothing() -> None:
    """A match takes the values before it; what its rows leave is not counted, so a match on a
    later line takes only what the lines between push."""
    source = "f : x -- y z\n\tmatch\n\t\t_\t1\n\t2\n\tmatch\n\t\t2\t#two\n1 f\n"
    assert run(source) == "1 #two\n"


def test_a_wildcard_row_whose_body_is_a_goal_waits_for_goals() -> None:
    """[D4.3] _ ? is a wildcard row whose body is a goal the elaborator reports; goals are not
    implemented (hole goal-placeholder), so the program is refused before it runs."""
    with pytest.raises(FplError) as refused:
        run("f : x -- y\n\tmatch\n\t\t0\t1\n\t\t_\t?\n1 f\n")
    assert (refused.value.span, refused.value.message) == (Span(1, 1), "no evaluator yet")


def test_a_record_pattern_in_a_head_waits_for_defaults() -> None:
    """[D4.11] { sep “ ” end newline } in join's head binds sep and end, the caller's record
    unioned over the defaults; not implemented (hole effect-head-defaults), so refused."""
    with pytest.raises(FplError) as refused:
        run("join : xs { sep “ ” end newline } -- s\n\txs sep interleave end ,\n")
    assert (refused.value.span, refused.value.message) == (Span(1, 1), "no evaluator yet")
