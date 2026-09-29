"""Running lines: the stack, frames and the bar, sections, strands, ( ), blocks and `:`
definitions (draft2 §frames, §currying, §( ) rotates; draft1 blocks and node; draft3 effect)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_parse import spans

from fpl.ast_core import (
    EFFECTS,
    Call,
    Define,
    Effect,
    Listed,
    Push,
    Quotation,
    Run,
    Statement,
    Strand,
)
from fpl.ast_surface import Cell, Enclosure, Frame, Line, Pair, Program, Text
from fpl.desugar import START, desugar, listing, resugar, text
from fpl.driver import run
from fpl.errors import FplError
from fpl.eval import BUILTINS, CONTROLS, evaluate
from fpl.parse import parse
from fpl.print import render

CURRY = "curry : x q -- q'\n\tswap enclose swap ,\n"
LCURRY = "lcurry : x q -- q'\n\t[ swap ] swap , curry\n"
SLOTS = "app : x t: [] c: Code -- y\n"

items = st.recursive(
    st.integers(-9, 99).map(str)
    | st.sampled_from(sorted(BUILTINS))
    | st.sampled_from(["#a", "→a", "1 →a a", "{ k 1 }"]),
    lambda inner: (
        st.lists(inner, max_size=4).map(lambda xs: "[" + " ".join(xs) + "]")
        | st.lists(inner, min_size=1, max_size=4).map(lambda xs: "(" + " ".join(xs) + ")")
    ),
    max_leaves=12,
)
lines = st.lists(st.lists(items, min_size=1, max_size=4).map(" ".join), min_size=1, max_size=3)
programs = st.lists(lines.map(" | ".join), min_size=1, max_size=3).map("\n".join)


def core(source: str) -> tuple[Statement, ...] | str:
    """A program's statements, or its error's message without the position."""
    try:
        return desugar(parse(source))
    except FplError as error:
        return error.message


def outcome(source: str) -> str:
    """What a program prints, or its error's message without the position."""
    try:
        return run(source)
    except FplError as error:
        return f"ERROR {error.message}"


@pytest.mark.obligation("desugaring preserves meaning")
@given(st.sampled_from(["", CURRY, "nop : --\n", SLOTS]), programs)
def test_desugaring_preserves_meaning(head: str, body: str) -> None:
    """The core written back as source, with no bar, ( ) or block left, means what the source
    meant: bars and ( ) only sequence, a section is its quotation, a block its children."""
    source = head + body + "\n"
    assert outcome(render(resugar(desugar(parse(source))))) == outcome(source)


@given(programs)
def test_comments_change_no_statement(body: str) -> None:
    """A ;; line before each line and a note after it leave the core as it was: a comment is no
    code, and a ;; before no definition is no doc."""
    commented = "".join(f";; d\n{line} ; n\n" for line in body.split("\n"))
    assert core(commented) == core(body + "\n")


@pytest.mark.parametrize(
    ("commented", "plain"),
    [
        (";;; s\n; a\n; b\n\n1 ; n\n;; d\n2\n", "1\n2\n"),
        ("\n\n1\n", "1\n"),
        (
            CURRY.replace("\n\t", "\t; n\n\t") + "\t;; end\n1 [ + ] curry\n",
            CURRY + "1 [ + ] curry\n",
        ),
        (",\n\t1\n\t; c\n\t2\n", ",\n\t1\n\t2\n"),
        ("+ +\n\t1\n\t;; c\n\t2\n", "+ +\n\t1\n\t2\n"),
    ],
)
def test_a_line_with_no_code_is_no_statement(commented: str, plain: str) -> None:
    """A comment's line and the empty first line run nothing, at the top, in a block or in a
    body, and a block counts only the children that hold code: under + + two children leave it
    one short, so it is a section."""
    assert core(commented) == core(plain)


def test_a_bar_alone_is_code() -> None:
    """| holds two empty frames, so its line is code: no statement is dropped, and its block
    is children pushed before it, not refused."""
    assert desugar(parse("|\n\t1\n")) == (Run((Push(Quotation((Push(1),))),)),)


@pytest.mark.parametrize("source", ["", "\n", "\n\n", ";; d\n", "; a\n; b\n", "⍝ a\n\n;;;; f\n"])
def test_a_program_of_comments_or_blank_lines_prints_nothing(source: str) -> None:
    assert run(source) == ""


@pytest.mark.parametrize(("pair", "value"), [("quotation", Quotation(())), ("group", Listed(()))])
def test_an_empty_enclosure_means_what_no_frame_meant(
    pair: Pair, value: Quotation | Listed
) -> None:
    """[] and ⟨⟩ hold one empty frame, the base case of bars + 1 frames; they desugar to the
    empty quotation and the empty list, as an enclosure of no frames did."""

    def program(enclosure: Enclosure) -> Program:
        cell = Cell((enclosure,), START)
        return Program((Line((Frame((cell,), START),), (), START),), START)

    source = "[]\n" if pair == "quotation" else "⟨⟩\n"
    one = Enclosure(pair, (Frame((), START),), START)
    assert parse(source) == program(one)
    expected = (Run((Push(value),)),)
    assert desugar(program(one)) == desugar(program(Enclosure(pair, (), START))) == expected


def test_literals_strand_inside_a_frame_and_the_bar_applies_across() -> None:
    """[D2.1] 1 | 1 2 3 + gives 2 3 4: the strand takes the 1 the bar carries; + is pervasive."""
    assert run("1 | 1 2 3 +\n") == "2 3 4\n"


def test_an_unsaturated_frame_with_nothing_below_is_a_section() -> None:
    """[D2.2] 1 2 3 + is the section [1‿2‿3 +], as the printer writes a quotation."""
    assert run("1 2 3 +\n") == "[ 1 2 3 + ]\n"


def test_the_bar_supplies_what_a_frame_lacks() -> None:
    """[D2.3] 2 | 3 + gives 5."""
    assert run("2 | 3 +\n") == "5\n"


def test_a_number_meets_a_number_as_a_number() -> None:
    """[D2.3] 2 | 3 + leaves the number 5, not a strand of one."""
    assert evaluate(desugar(parse("2 | 3 +\n"))) == ((5,),)


def test_each_line_runs_on_a_fresh_stack() -> None:
    """draft2 examples/01-frames.fpl:2-4: one result per line; nothing a line leaves is below
    the next."""
    assert run("1 | 1 2 3 +\n1 2 3 +\n2 | 3 +\n") == "2 3 4\n[ 1 2 3 + ]\n5\n"


def test_curry_puts_the_value_before_the_code() -> None:
    """[D2.5] curry : x q -- q' gives [x q]."""
    assert run(CURRY + "1 [ + ] curry\n") == "[ 1 + ]\n"


def test_lcurry_puts_a_swap_between() -> None:
    """[D2.6] lcurry : x q -- q' gives [x swap q]; a word may be used above its definition."""
    assert run(LCURRY + CURRY + "1 [ - ] lcurry\n") == "[ 1 swap - ]\n"


def test_a_block_is_one_node_per_head() -> None:
    """[D1.4] one block per minimum-depth line: head and its subtree, each a result."""
    assert run(",\n\t1\n\t2\n,\n\t3\n\t4\n") == "[ 1 | 2 ]\n[ 3 | 4 ]\n"


def test_children_are_quotations_before_the_head() -> None:
    """[D1.5] node: children-quotations , head-tokens; quotations because , takes two code
    slots (S49 rule 5), not by their position."""
    assert run(",\n\t1 2\n\t+\n") == "[ 1 2 + ]\n"


@pytest.mark.parametrize(
    ("source", "printed"),
    [
        ("times\n\t1 | 2 +\n\t3 | 4 +\n", "21\n"),
        ("-\n\t10\n\t1\n", "9\n"),
        ("+ dup times\n\t1\n\t2\n", "9\n"),
        ("times\n\t+\n\t\t1\n\t\t2\n\t4\n", "12\n"),
        ("f : x -- y\n\t+\n\t\t1\n5 f\n", "6\n"),
        ("1 + +\n\t10\n\t20\n", "31\n"),
    ],
)
def test_a_child_under_a_value_slot_runs_at_once(source: str, printed: str) -> None:
    """[S49] rule 5 and S42 (children push, head consumes): each child fills an input of the
    head phrase, the first child the deepest; under a value slot it runs at once, top to bottom,
    on the stack its head then consumes."""
    assert run(source) == printed


@pytest.mark.parametrize(
    ("source", "printed"),
    [
        ("keep : t: [ -- x ] -- t\nkeep\n\t1 | 2 +\n", "[ 1 | 2 + ]\n"),
        ("look : c: Code -- c\nlook\n\t1 | 2 +\n", "[ 1 | 2 + ]\n"),
        ("pair : x t: [] -- x t\npair\n\t1 | 2 +\n\t3\n", "3 [ 3 ]\n"),
        ("1 | 2\n\t+\n", "[ + ] 1 | 2\n"),
        ("dup\n\t1\n\t2\n", "[ 1 ] 2 | 2\n"),
        ("dup\n\t+\n", "[ + ] [ + ]\n"),
        ("+ dup times\n\t1\n\t2\n\t3\n", "[ 1 ] 25\n"),
        ("mk : x --\nwrap : t: [] -- t\nmk wrap\n\t1 | 2 +\n\t3\n", "[ 1 | 2 + ] 3\n"),
        ("pair : x t: [] -- x t\n1 pair\n\t1 | 2 +\n", "3 | 1\n"),
    ],
)
def test_a_child_under_a_thunk_or_code_slot_is_pushed_as_a_quotation(
    source: str, printed: str
) -> None:
    """[S49] rule 5: a child is only ever run by its head; under a thunk or Code slot it is
    pushed as a quotation. A child past the head's inputs is one too (hole child-slots), and a
    value child that reaches below its balance is a section, as a frame is (decision f)."""
    assert run(source) == printed


def test_a_lone_literal_is_itself_and_literals_side_by_side_are_one_strand() -> None:
    """[D2.1] 1‿2 is one value; the 3 beside no other literal is not a strand."""
    assert desugar(parse("1 2 | 3 +\n")) == (
        Run((Push(Strand((1, 2))), Push(3), Call("+", START))),
    )


@pytest.mark.parametrize(
    ("source", "printed"),
    [
        ("1 | 2 + +\n", "1 [ 2 + + ]\n"),
        ("1 + | 2 swap\n", "2 [ 1 + ]\n"),
        ("1 + | swap\n", "[ 1 + ] [ swap ]\n"),
    ],
)
def test_a_frame_that_reaches_below_its_balance_is_a_section(source: str, printed: str) -> None:
    """[D2.2] the second + would take the 1 the bar carries and a value below it: the frame is
    pushed whole; a section counts as one value for the frames after it."""
    assert run(source) == printed


@pytest.mark.parametrize(
    "source",
    [
        "1 dup\n",
        "“a” “b”\n",
        "1.5 | -9 +\n",
        CURRY + "nop : --\n1 [ + ] curry\n",
        "#a #b\n",
        "1 →a a\n",
        "1 →a/b a/b a/b +\n",
        "{ k 1 }\n",
        SLOTS,
    ],
)
def test_core_without_sugar_writes_back_as_its_source(source: str) -> None:
    """A source with no bar but between two literals, no ( ) and no block but a definition's
    body is what resugar writes for its core; a slot is written bare, `t: []` or `c: Code`."""
    assert resugar(desugar(parse(source))) == parse(source)


def test_a_written_tree_points_at_the_start() -> None:
    """A tree desugar writes has no source of its own: every span is 1:1, where it refuses."""
    source = CURRY + SLOTS + "nop : --\n1 [ + ] curry\n“a” ⟨ 1 ⟩ 1.5\n#a { k 1 } 1 →a a\n"
    statements = desugar(parse(source))
    written = [*spans(resugar(statements)), *spans(listing(evaluate(statements)))]
    assert set(written) == {START}


def test_a_string_is_its_parts_in_order() -> None:
    assert text(Text("str", ("a", "b"), START)) == "ab"


def test_the_effect_line_is_kept_as_declared() -> None:
    """[D3.4] words/*/effect: the declared effect is kept as data (the query: hole
    effect-query)."""
    (definition,) = desugar(parse(CURRY))
    assert isinstance(definition, Define)
    assert definition.effect == Effect(("x", "q"), ("q'",))


def test_an_effect_takes_values_unless_its_slots_say_otherwise() -> None:
    """S49 rule 5: an input is a value, a thunk or code; an effect line with no slot given takes
    values, and a slot count other than one per input is refused."""
    assert Effect(("x", "y"), ("z",)).slots == ("value", "value")
    assert Effect(("q",), (), slots=("thunk",)).slots == ("thunk",)
    assert Effect(("x",), ()) == Effect(("x",), (), slots=("value",))
    with pytest.raises(ValueError, match=r"^one slot per input$"):
        Effect(("x",), (), slots=("code", "code"))


def test_a_typed_effect_line_declares_its_slots() -> None:
    """[S49] name: Type per slot: a type spelled [ ] makes a thunk, Code a code slot, any other
    a value; a bare name is an untyped value; an output's type is read past."""
    source = "f : t: [ -- x ]  c: Code  l: ⟨ a b ⟩  n: Int  m -- z: Int\n"
    (definition,) = desugar(parse(source))
    assert isinstance(definition, Define)
    assert definition.effect == Effect(
        ("t", "c", "l", "n", "m"), ("z",), slots=("thunk", "code", "value", "value", "value")
    )


def test_a_slot_name_is_every_character_before_its_colon() -> None:
    """[S49] `name: Type`: the slot is named all of `name`; a lone `:` is a bare name, an
    untyped value (hole bare-slot-names), not the colon of a slot with no name."""
    (typed,) = desugar(parse("f : xs: Int  q: [] -- y\n"))
    assert isinstance(typed, Define)
    assert typed.effect == Effect(("xs", "q"), ("y",), slots=("value", "thunk"))
    (bare,) = desugar(parse("f : a : b -- c\n"))
    assert isinstance(bare, Define)
    assert bare.effect == Effect(("a", ":", "b"), ("c",))


def test_a_slot_type_is_not_a_slot() -> None:
    """[S49] f : x: Int  y: Int -- z: Int takes two values, not four: 1 | 2 f runs f."""
    assert run("f : x: Int  y: Int -- z: Int\n\t+\n1 | 2 f\n") == "3\n"


def test_parentheses_rotate_the_head_to_the_end() -> None:
    """draft2 examples/09-rotates.fpl:2-3: (+ 1 2) is 1 | 2 + = 3, (+ (times 2 3) 4) is 10."""
    assert run("(+ 1 2)\n(+ (times 2 3) 4)\n") == "3\n10\n"


@pytest.mark.parametrize(
    ("source", "printed"),
    [
        ("1 | 2 swap\n", "2 | 1\n"),
        ("1 dup\n", "1 | 1\n"),
        ("1 | 2 drop\n", "1\n"),
        ("1\t2 +\n", "3\n"),
        ("1.5 | 2 +\n", "3.5\n"),
        ("10 | 1 2 -\n", "9 8\n"),
        ("“a” 「b」\n", "“a” “b”\n"),
        ("⟨ 1 [ 2 ] ⟩ ⟨⟩ ,\n", "⟨ 1 [ 2 ] ⟩\n"),
        ("[ ]\n", "[]\n"),
        ("⟨⟩\n", "⟨⟩\n"),
        ("0.0000001\n", "0.0000001\n"),
        ("123456789012345 | 123456789012345 times\n", "15241578753238669120562399025\n"),
        ("1 2 | 10 times\n", "10 20\n"),
        (": : --\n1\t2 : 3\n", "1 | 2 | 3\n"),
    ],
)
def test_stack_words_and_literals(source: str, printed: str) -> None:
    assert run(source) == printed


@pytest.mark.parametrize(
    ("source", "error"),
    [
        ("[ ] 1 +\n", "ERROR: 1:7 arithmetic on a non-number"),
        ("1 | [ ] +\n", "ERROR: 1:9 arithmetic on a non-number"),
        ("1 2 | 1 2 3 +\n", "ERROR: 1:13 strands of unequal length"),
        ("1 | 2 ,\n", "ERROR: 1:7 , joins two quotations or two lists"),
        ("f : -- y z\n1 | f +\n", "ERROR: 2:7 stack underflow"),
    ],
)
def test_a_word_refuses_at_its_position(source: str, error: str) -> None:
    with pytest.raises(FplError) as caught:
        run(source)
    assert str(caught.value) == error


@pytest.mark.parametrize(
    "source",
    [
        *("∞\n", "#1\n", "$1\n", "1\u00b4\n", "a/b\n", "{ 1 }\n", "()\n", "“⟨1⟩”\n"),
        *(";;; s\n\t1\n", "\n\t1\n", "1\n\t; c\n\t\t2\n"),
        *("⟨ (+ 1 2) ⟩\n", "f : x\n", "f : x -- y | 1\n", "f : #x -- y\n", "1 2 3 sqrt\n"),
        *("f : x: -- y\n", "f : -- y:\n", "#f : --\n", "f : t: -- x -- y\n"),
    ],
)
def test_what_no_part_implements_is_refused_before_running(source: str) -> None:
    with pytest.raises(FplError) as caught:
        run(source)
    assert str(caught.value) == "ERROR: 1:1 no evaluator yet"


def test_join_takes_code_and_enclose_a_value() -> None:
    """[S49] , inspects its operands, never runs them: two code slots; enclose quotes the value
    it is given (hole quotation-slot-words)."""
    assert EFFECTS[","].slots == ("code", "code")
    assert EFFECTS["enclose"].slots == ("value",)


def test_every_declared_builtin_has_an_implementation() -> None:
    assert set(EFFECTS) == set(BUILTINS) | set(CONTROLS)
