"""Surface AST to core AST, and core back to surface for the printer. All sugar is erased here.

A line runs on a fresh stack. Its frames join into one postfix sequence: the bar carries the
running arity balance across, and a frame whose words would reach below the balance it starts
on is a section, pushed whole as a quotation (decision f). Literals side by side in a cell
strand. The lines of a block are quotations pushed before the tokens of their head; the block of
a `:` head is its body, whose balance starts at the effect line's inputs and runs on from line
to line. ( ) puts its head after its arguments. Quotation bodies are code, never sections.
A line with no code, a comment's or the empty first line, is no statement and no child; its
comment is not carried into the core. Anything outside the implemented set is refused before
evaluation (hole unimplemented-words).
"""

from collections.abc import Mapping
from decimal import Decimal
from itertools import groupby
from typing import NoReturn, assert_never

from fpl.ast_core import (
    EFFECTS,
    Atom,
    Call,
    Define,
    Effect,
    Listed,
    Node,
    Number,
    Push,
    Quotation,
    Run,
    Statement,
    Strand,
    Value,
)
from fpl.ast_surface import Cell, Enclosure, Frame, Item, Line, Program, Text, Word
from fpl.errors import FplError, Span

START = Span(1, 1)


def unimplemented() -> NoReturn:
    """Refuse what no part implements yet, at the source's start."""
    raise FplError(START, "no evaluator yet")


def desugar(program: Program) -> tuple[Statement, ...]:
    """The program's lines as statements, in order. Every effect is known before any line is
    read, so a word may be used above its definition; a later definition shadows."""
    lines = coded(program.lines)
    effects = dict(EFFECTS)
    for line in lines:
        head = definition(line)
        if head is not None:
            effects[head[0]] = head[1]
    return tuple(_Desugar(effects).statement(line) for line in lines)


def coded(lines: tuple[Line, ...]) -> tuple[Line, ...]:
    """The lines that hold code: a bar, or an item in a frame. A line with none is a comment's
    or the empty first line, and heading a block it is refused (holes comment-heads-block,
    empty-first-line)."""
    kept: list[Line] = []
    for line in lines:
        if len(line.frames) > 1 or any(frame.cells for frame in line.frames):
            kept.append(line)
        elif line.block:
            unimplemented()
    return tuple(kept)


def definition(line: Line) -> tuple[str, Effect] | None:
    """The name and effect of a `name : ins -- outs` line; None for a line that is not one."""
    cells = line.frames[0].cells
    if [plain(item) for cell in cells[:1] for item in cell.items[1:2]] != [":"]:
        return None
    if len(line.frames) + len(cells) > 2:
        unimplemented()
    return effect_line(cells[0].items)


def effect_line(items: tuple[Item, ...]) -> tuple[str, Effect]:
    """name : ins -- outs, every one a plain name."""
    names = [name for name in map(plain, items) if name is not None]
    if len(names) < len(items) or "--" not in names:
        unimplemented()
    cut = names.index("--")
    return names[0], Effect(tuple(names[2:cut]), tuple(names[cut + 1 :]))


def plain(item: Item) -> str | None:
    """A name with no sigil or modifier, or None."""
    if isinstance(item, Word) and item.kind == "name" and not (item.prefix or item.mods):
        return item.body[0]
    return None


def atom(item: Item) -> Atom:
    """The value of a literal."""
    return text(item) if isinstance(item, Text) else number(item)


def text(item: Text) -> str:
    """A string without islands."""
    texts = [part for part in item.parts if isinstance(part, str)]
    if len(texts) < len(item.parts):
        unimplemented()
    return "".join(texts)


def number(item: Item) -> Number:
    """An integer or a decimal, kept exact as written; ∞, π and a sigil or modifier are
    refused."""
    if not isinstance(item, Word) or item.prefix or item.mods or not item.body[0][-1].isdigit():
        unimplemented()
    numeral = item.body[0]
    return Decimal(numeral) if "." in numeral else int(numeral)


def literal(item: Item) -> bool:
    """A number or a string: what strands."""
    return isinstance(item, Text) or (isinstance(item, Word) and item.kind == "number")


class _Desugar:
    """Lines to code, with the effect of every word known."""

    def __init__(self, effects: Mapping[str, Effect]) -> None:
        self.effects = effects

    def statement(self, line: Line) -> Statement:
        """A definition, or a line to run."""
        head = definition(line)
        if head is None:
            return Run(self.body((line,), 0))
        name, effect = head
        return Define(name, effect, self.body(line.block, len(effect.ins)))

    def body(self, lines: tuple[Line, ...], balance: int) -> tuple[Node, ...]:
        """Lines on one stack in turn, each starting on the balance the one before left."""
        code: list[Node] = []
        for line in coded(lines):
            children = self.children(line)
            code.extend(children)
            balance += len(children)
            for frame in line.frames:
                nodes = self.frame(frame)
                after = self.balance(nodes, balance)
                if after is None:
                    nodes, after = (Push(Quotation(nodes)),), balance + 1
                code.extend(nodes)
                balance = after
        return tuple(code)

    def balance(self, nodes: tuple[Node, ...], balance: int) -> int | None:
        """The balance after the nodes run on `balance` values; None if one reaches below."""
        for node in nodes:
            takes, leaves = (0, 1) if isinstance(node, Push) else self.arity(node)
            if balance < takes:
                return None
            balance += leaves - takes
        return balance

    def arity(self, call: Call) -> tuple[int, int]:
        """How many values a word takes and leaves, from its effect."""
        effect = self.effects[call.name]
        return len(effect.ins), len(effect.outs)

    def children(self, line: Line) -> tuple[Node, ...]:
        """Each line of the block as a quotation, in order."""
        return tuple(Push(Quotation(self.later(child))) for child in coded(line.block))

    def later(self, line: Line) -> tuple[Node, ...]:
        """A line as code to run later: its children, then its frames joined."""
        return self.children(line) + self.frames(line.frames)

    def frames(self, frames: tuple[Frame, ...]) -> tuple[Node, ...]:
        """Frames joined, with no saturation."""
        return tuple(node for frame in frames for node in self.frame(frame))

    def frame(self, frame: Frame) -> tuple[Node, ...]:
        """Cells in turn; within a cell, literals side by side strand."""
        code: list[Node] = []
        for cell in frame.cells:
            for strands, run in groupby(cell.items, key=literal):
                items = tuple(run)
                if strands and len(items) > 1:
                    code.append(Push(Strand(tuple(map(atom, items)))))
                else:
                    code.extend(node for item in items for node in self.item(item))
        return tuple(code)

    def item(self, item: Item) -> tuple[Node, ...]:
        """One item's code."""
        match item:
            case Word() if item.kind == "number":
                return (Push(number(item)),)
            case Word():
                return (self.call(item),)
            case Text():
                return (Push(text(item)),)
            case Enclosure():
                return self.enclosure(item)
            case _:
                assert_never(item)

    def call(self, word: Word) -> Call:
        """A word with a known effect."""
        name = plain(word)
        if name is None or name not in self.effects:
            unimplemented()
        return Call(name, word.span)

    def enclosure(self, enclosure: Enclosure) -> tuple[Node, ...]:
        """[ ] a quotation, ( ) its head last, ⟨ ⟩ a list of literals."""
        match enclosure.pair:
            case "quotation":
                return (Push(Quotation(self.frames(enclosure.frames))),)
            case "prefix":
                return self.prefix(enclosure)
            case "group":
                items = [i for f in enclosure.frames for c in f.cells for i in c.items]
                return (Push(Listed(tuple(map(self.element, items)))),)
            case "dict":
                unimplemented()
            case _:
                assert_never(enclosure.pair)

    def prefix(self, enclosure: Enclosure) -> tuple[Node, ...]:
        """( head args ): each argument's code, then the head's; arguments never strand."""
        cells = [cell for frame in enclosure.frames for cell in frame.cells]
        if len(cells) != 1:
            unimplemented()
        head, *args = cells[0].items
        return tuple(node for item in (*args, head) for node in self.item(item))

    def element(self, item: Item) -> Value:
        """A list element: an item that pushes one value."""
        nodes = self.item(item)
        if len(nodes) == 1 and isinstance(nodes[0], Push):
            return nodes[0].value
        unimplemented()


def resugar(statements: tuple[Statement, ...]) -> Program:
    """Core as source that desugars to the same code: no bar but between two literals, which
    would otherwise strand, no ( ), no block but a definition's one-line body."""
    return Program(tuple(map(written, statements)), START)


def listing(stacks: tuple[tuple[Value, ...], ...]) -> Program:
    """One line per stack, each a program that pushes that stack."""
    return Program(tuple(Line(sugared(tuple(map(Push, s))), (), START) for s in stacks), START)


def written(statement: Statement) -> Line:
    """One statement as a line."""
    match statement:
        case Run():
            return Line(sugared(statement.code), (), START)
        case Define():
            effect = statement.effect
            names = (statement.name, ":", *effect.ins, "--", *effect.outs)
            body = (Line(sugared(statement.code), (), START),) if statement.code else ()
            return Line((framed(tuple(map(named, names))),), body, START)
        case _:
            assert_never(statement)


def sugared(code: tuple[Node, ...]) -> tuple[Frame, ...]:
    """Code as frames, a bar wherever a literal follows a literal."""
    frames: list[list[Item]] = [[]]
    before: Node | None = None
    for node in code:
        if stranding(before) and stranding(node):
            frames.append([])
        frames[-1].extend(shown(node.value) if isinstance(node, Push) else (named(node.name),))
        before = node
    return tuple(framed(tuple(items)) for items in frames)


def stranding(node: Node | None) -> bool:
    """A push of a number, a string or a strand."""
    return isinstance(node, Push) and not isinstance(node.value, Listed | Quotation)


def framed(items: tuple[Item, ...]) -> Frame:
    """Items as a frame of one cell, or of none."""
    return Frame((Cell(items, START),) if items else (), START)


def named(name: str) -> Word:
    """A name as written."""
    return Word("", "name", (name,), "", START)


def shown(value: Value) -> tuple[Item, ...]:
    """A value as the items that push it."""
    match value:
        case str():
            return (Text("str", (value,), START),)
        case Strand():
            return spread(value.items)
        case Listed():
            return (Enclosure("group", (framed(spread(value.items)),), START),)
        case Quotation():
            return (Enclosure("quotation", sugared(value.code), START),)
        case _:
            numeral = format(value, "f") if isinstance(value, Decimal) else str(value)
            return (Word("", "number", (numeral,), "", START),)


def spread(values: tuple[Value, ...]) -> tuple[Item, ...]:
    """Values side by side."""
    return tuple(item for value in values for item in shown(value))
