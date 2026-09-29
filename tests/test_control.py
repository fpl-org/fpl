"""Control words over quotations: ! forces, if chooses, swap-args commutes, repeat iterates,
each, scan and fold run a quotation over the items of a strand or a list (draft1; draft2
§frames, §operatives, §( ) rotates; combined draft row 14)."""

from itertools import accumulate

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fpl.driver import run
from fpl.errors import FplError

numbers = st.lists(st.integers(-99, 99), min_size=2, max_size=8)


def test_swap_args_fills_the_right_slot_from_outside() -> None:
    """[D2.4] 1 | 1 2 3 [-] swap-args is 1 2 3 - 1."""
    assert run("1 | 1 2 3 [-] swap-args\n") == "0 1 2\n"


def test_plus_folded_over_a_strand_is_its_sum() -> None:
    """[D2.13] variadic + is a fold over a strand."""
    assert run("1 2 3 [+] fold\n") == "6\n"


@given(numbers)
def test_fold_and_scan_thread_a_state_through_the_items(xs: list[int]) -> None:
    """[D2.13] [+] fold is the sum; [+] scan is each running sum, the last of them the fold."""
    strand = " ".join(map(str, xs))
    assert run(f"{strand} [+] fold\n") == f"{sum(xs)}\n"
    assert run(f"{strand} [+] scan\n") == " ".join(map(str, accumulate(xs))) + "\n"


def test_a_scan_then_a_fold_counts_the_leading_run() -> None:
    """[D1.2] depth: leading tabs, as tab = [and] scan [+] fold; times is and on 0 and 1."""
    assert run("1 1 0 1 [times] scan [+] fold\n") == "2\n"


@pytest.mark.parametrize(
    ("source", "printed"),
    [
        ("[1 | 2 +] !\n", "3\n"),
        ("2 [dup +] !\n", "4\n"),
        ("1 [2] [3] if\n", "2\n"),
        ("0 [2] [3] if\n", "3\n"),
        ("my-if : c t --\n\tswap ! [ ! ] [ drop ] if\n[1] [5] my-if\n[0] [5] my-if\n", "5\n\n"),
        ("f : c -- x\n\tif\n\t\t2\n\t\t3\n1 f\n0 f\n", "2\n3\n"),
        ("0 [1 +] 3 repeat\n", "3\n"),
        ("f : x -- x\n\t3 repeat\n\t\t2 times\n1 f\n", "8\n"),
        ("0 [1 +] 0 repeat\n", "0\n"),
        ("1 2 3 [dup times] each\n", "1 4 9\n"),
        ("1 2 [enclose] each\n", "⟨ [ 1 ] [ 2 ] ⟩\n"),
        ("⟨ 1 2 ⟩ [1 +] each\n", "⟨ 2 3 ⟩\n"),
        ("⟨⟩ [1 +] each\n", "⟨⟩\n"),
        ("⟨⟩ [+] scan\n", "⟨⟩\n"),
        ("⟨ [1] [2] ⟩ [,] fold\n", "[ 1 | 2 ]\n"),
        ("1 2 [+] fold\n", "3\n"),
    ],
)
def test_control_words_run_the_quotations_they_take(source: str, printed: str) -> None:
    """! runs a quotation in place; if runs t on 1 and e on 0, children first giving the
    branches (combined draft row 14: if : c t e --); swap-args runs q on the two values below
    it swapped; repeat runs q n times, its block giving q (draft1 shortest-paths, draft2 take);
    each maps, scan and fold thread a state, each step on a fresh stack, a strand staying one
    while every result is a number or a string."""
    assert run(source) == printed


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("1 !\n", "ERROR: 1:3 a quotation is expected"),
        ("2 [2] [3] if\n", "ERROR: 1:11 if takes 0 or 1"),
        ("[1] [2] [3] if\n", "ERROR: 1:13 if takes 0 or 1"),
        ("1 [2] 3 if\n", "ERROR: 1:9 a quotation is expected"),
        ("0 [1 +] -1 repeat\n", "ERROR: 1:12 repeat takes a count"),
        ("[1] [2] repeat\n", "ERROR: 1:9 repeat takes a count"),
        ("1 2 [dup] each\n", "ERROR: 1:11 each step leaves one value"),
        ("1 2 [drop drop] fold\n", "ERROR: 1:17 each step leaves one value"),
        ("3 [1 +] each\n", "ERROR: 1:9 a strand or a list is expected"),
        ("⟨⟩ [+] fold\n", "ERROR: 1:8 fold over nothing"),
        ("1 | 2 | 3 swap-args\n", "ERROR: 1:11 a quotation is expected"),
        ("1 | 2 [3] if\n", "ERROR: 1:11 a quotation is expected"),
        ("1 2 | 3 each\n", "ERROR: 1:9 a quotation is expected"),
        ("1 | 3 repeat\n", "ERROR: 1:7 a quotation is expected"),
        ("1 2 | 3 scan\n", "ERROR: 1:9 a quotation is expected"),
        ("3 [+] fold\n", "ERROR: 1:7 a strand or a list is expected"),
    ],
)
def test_control_words_refuse_what_they_cannot_run(source: str, message: str) -> None:
    """A quotation where one is run, 0 or 1 for if, a count for repeat, a sequence for each,
    scan and fold, one value from each step, and an item for fold to start from."""
    with pytest.raises(FplError) as caught:
        run(source)
    assert str(caught.value) == message
