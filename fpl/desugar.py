"""Surface AST to core AST, and core back to surface for the printer. All sugar is erased here.

A line runs on a fresh stack. Its frames join into one postfix sequence: the bar carries the
running arity balance across, and a frame whose words would reach below the balance it starts
on is a section, pushed whole as a quotation (decision f). Literals side by side in a cell
strand. The lines of a block fill the inputs of their head, before its tokens: a child under a
value slot is its code, run at once; under a thunk or code slot, a quotation (S49 rule 5). The
block of a `:` head is its body, whose balance starts at the effect line's inputs and runs on
from line to line. ( ) puts its head after its arguments. Quotation bodies are code, never sections.
→x names the top for the rest of its line, body or quotation, where x pushes it (decision f);
#x is a symbol; { } pairs literal keys with one item each.
A line with no code, a comment's or the empty first line, is no statement and no child; its
comment is not carried into the core. Anything outside the implemented set is refused before
evaluation (hole unimplemented-words).
"""

from collections import ChainMap
from collections.abc import Callable, Iterator, Mapping
from decimal import Decimal
from functools import partial
from itertools import groupby
from typing import NoReturn, assert_never

from fpl.ast_core import (
    EFFECTS,
    Atom,
    Bind,
    Call,
    Define,
    Dict,
    Effect,
    Keyed,
    Listed,
    Node,
    Number,
    Push,
    Quotation,
    Run,
    Slot,
    Statement,
    Strand,
    Symbol,
    Value,
)
from fpl.ast_surface import Cell, Enclosure, Frame, Item, Line, Program, Text, Word
from fpl.errors import FplError, Span

START = Span(1, 1)
ARROWS = ("→", "->")
LOCAL = Effect((), ("x",))


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
    """name : ins -- outs, each a plain name or `name: Type` (S49); an output's type is read
    past."""
    name = plain(items[0])
    declared = typed(items[2:])
    names = [pair[0] for pair in declared]
    if name is None or "--" not in names:
        unimplemented()
    cut = names.index("--")
    slots: tuple[Slot, ...] = tuple(pair[1] for pair in declared[:cut])
    return name, Effect(tuple(names[:cut]), tuple(names[cut + 1 :]), slots=slots)


def typed(items: tuple[Item, ...]) -> list[tuple[str, Slot]]:
    """Each plain name with its slot: `name: Type` has the slot its type makes, a bare name is
    an untyped value (hole bare-slot-names)."""
    declared: list[tuple[str, Slot]] = []
    rest = iter(items)
    for item in rest:
        name = plain(item)
        if name is None:
            unimplemented()
        if len(name) > 1 and name.endswith(":"):
            declared.append((name[:-1], slot(next(rest, None))))
        else:
            declared.append((name, "value"))
    return declared


def slot(kind: Item | None) -> Slot:
    """The slot a type makes (S49 rule 5): [ ] a thunk, Code code, any other a value; a `name:`
    with no type after it is refused."""
    if kind is None or plain(kind) == "--":
        unimplemented()
    if isinstance(kind, Enclosure) and kind.pair == "quotation":
        return "thunk"
    return "code" if plain(kind) == "Code" else "value"


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


def bare(word: Word) -> str:
    """The name after a sigil; a path or a modifier is refused."""
    if word.kind != "name" or word.mods:
        unimplemented()
    return word.body[0]


def contents(enclosure: Enclosure) -> list[Item]:
    """The items of an enclosure, bars and tabs aside."""
    return [item for frame in enclosure.frames for cell in frame.cells for item in cell.items]


def scoped(code: tuple[Node, ...]) -> tuple[Node, ...]:
    """Code with each binder holding the rest of it as its body."""
    out: list[Node] = []
    for node in reversed(code):
        if isinstance(node, Bind):
            out = [Bind(node.name, node.body + tuple(reversed(out)), node.span)]
        else:
            out.append(node)
    return tuple(reversed(out))


def literal(item: Item) -> bool:
    """A number or a string: what strands."""
    return isinstance(item, Text) or (isinstance(item, Word) and item.kind == "number")


class _Desugar:
    """Lines to code, with the effect of every word known."""

    def __init__(self, effects: Mapping[str, Effect]) -> None:
        self.effects = ChainMap(dict(effects))

    def statement(self, line: Line) -> Statement:
        """A definition, or a line to run."""
        head = definition(line)
        if head is None:
            return Run(self.body((line,), 0))
        name, effect = head
        return Define(name, effect, self.body(line.block, len(effect.ins)))

    def body(self, lines: tuple[Line, ...], balance: int) -> tuple[Node, ...]:
        """Lines on one stack in turn, each starting on the balance the one before left. A name
        bound in them dies with them, and one bound in a section with the section."""
        outer = self.effects
        code: list[Node] = []
        for line in coded(lines):
            parts = (
                *(partial(self.child, child, kind) for child, kind in self.filled(line)),
                *(partial(self.frame, frame) for frame in line.frames),
            )
            for part in parts:
                before = self.effects
                nodes = part()
                after = self.balance(nodes, balance)
                if after is None:
                    self.effects = before
                    nodes, after = (Push(Quotation(scoped(nodes))),), balance + 1
                code.extend(nodes)
                balance = after
        self.effects = outer
        return scoped(tuple(code))

    def balance(self, nodes: tuple[Node, ...], balance: int) -> int | None:
        """The balance after the nodes run on `balance` values; None if one reaches below."""
        for node in nodes:
            takes, leaves = self.arity(node)
            if balance < takes:
                return None
            balance += leaves - takes
        return balance

    def arity(self, node: Node) -> tuple[int, int]:
        """How many values a node takes and leaves; a word's from its effect."""
        match node:
            case Push() | Keyed():
                return 0, 1
            case Bind():
                return 1, 0
            case Call():
                effect = self.effects[node.name]
                return len(effect.ins), len(effect.outs)
            case _:
                assert_never(node)

    def quote(self, build: Callable[[], tuple[Node, ...]]) -> Push:
        """Code built in a scope of its own, pushed as a quotation."""
        outer = self.effects
        code = build()
        self.effects = outer
        return Push(Quotation(scoped(code)))

    def children(self, line: Line) -> tuple[tuple[Node, ...], ...]:
        """Each line of the block in order, filling the head's inputs, the last child the top
        one: under a value slot its code, run at once; under a thunk or code slot, or past the
        head's inputs, a quotation (hole child-slots)."""
        return tuple(self.child(child, kind) for child, kind in self.filled(line))

    def filled(self, line: Line) -> tuple[tuple[Line, Slot | None], ...]:
        """Each child with the slot it fills, None past the head's inputs; the head is read in a
        scope thrown away, so its binders reach neither the children nor its own reading."""
        block = coded(line.block)
        outer = self.effects
        inputs = self.inputs(self.frames(line.frames))
        self.effects = outer
        kinds: list[Slot | None] = [None] * len(block)
        kinds += inputs
        return tuple(zip(block, kinds[len(inputs) :], strict=True))

    def child(self, line: Line, kind: Slot | None) -> tuple[Node, ...]:
        """A child's code, or its quotation, in a scope of its own, when it fills no value slot."""
        if kind == "value":
            return self.later(line)
        return (self.quote(partial(self.later, line)),)

    def inputs(self, code: tuple[Node, ...]) -> tuple[Slot, ...]:
        """The slots code takes from below it, deepest first: the head phrase as a whole, so the
        inputs a word's code before it does not supply lie under those already taken (hole
        multi-word-head). A binder's input is a value."""
        taken: tuple[Slot, ...] = ()
        held = 0
        for node in code:
            takes, leaves = self.arity(node)
            effect = (
                self.effects[node.name] if isinstance(node, Call) else Effect(("x",) * takes, ())
            )
            short = max(0, takes - held)
            taken = effect.slots[:short] + taken
            held += short + leaves - takes
        return taken

    def later(self, line: Line) -> tuple[Node, ...]:
        """A line as code to run later: its children, then its frames joined."""
        children = (node for part in self.children(line) for node in part)
        return (*children, *self.frames(line.frames))

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
            case Word():
                return (self.word(item),)
            case Text():
                return (Push(text(item)),)
            case Enclosure():
                return self.enclosure(item)
            case _:
                assert_never(item)

    def word(self, word: Word) -> Node:
        """A number, a symbol, a binder or a call."""
        if word.kind == "number":
            return Push(number(word))
        if word.prefix == "#":
            return Push(Symbol(bare(word)))
        if word.prefix in ARROWS:
            name = bare(word)
            self.effects = self.effects.new_child({name: LOCAL})
            return Bind(name, (), word.span)
        return self.call(word)

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
                return (self.quote(partial(self.frames, enclosure.frames)),)
            case "prefix":
                return self.prefix(enclosure)
            case "group":
                return (Push(Listed(tuple(map(self.element, contents(enclosure))))),)
            case "dict":
                return (self.dict(enclosure),)
            case _:
                assert_never(enclosure.pair)

    def prefix(self, enclosure: Enclosure) -> tuple[Node, ...]:
        """( head args ): each argument's code, then the head's; arguments never strand."""
        cells = [cell for frame in enclosure.frames for cell in frame.cells]
        if len(cells) != 1:
            unimplemented()
        head, *args = cells[0].items
        return tuple(node for item in (*args, head) for node in self.item(item))

    def dict(self, enclosure: Enclosure) -> Keyed:
        """Keys and values in turn: a key a plain name, a value one item pushing one value; a
        key given twice is refused where it repeats."""
        items = contents(enclosure)
        if len(items) % 2:
            unimplemented()
        entries: dict[str, Node] = {}
        for key_item, value_item in zip(items[::2], items[1::2], strict=True):
            key, nodes = plain(key_item), self.item(value_item)
            if key is None or len(nodes) != 1 or self.arity(nodes[0]) != (0, 1):
                unimplemented()
            if key in entries:
                raise FplError(key_item.span, f"repeated key {key}")
            entries[key] = nodes[0]
        return Keyed(tuple(entries.items()), enclosure.span)

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
            ins = zip(effect.ins, effect.slots, strict=True)
            taken = (item for name, kind in ins for item in declaration(name, kind))
            head = (named(statement.name), named(":"), *taken, named("--"))
            body = (Line(sugared(statement.code), (), START),) if statement.code else ()
            return Line((framed((*head, *map(named, effect.outs))),), body, START)
        case _:
            assert_never(statement)


def sugared(code: tuple[Node, ...]) -> tuple[Frame, ...]:
    """Code as frames, a bar wherever a literal follows a literal."""
    frames: list[list[Item]] = [[]]
    before: Node | None = None
    for node in unfolded(code):
        if stranding(before) and stranding(node):
            frames.append([])
        frames[-1].extend(spelled(node))
        before = node
    return tuple(framed(tuple(items)) for items in frames)


def unfolded(code: tuple[Node, ...]) -> Iterator[Node]:
    """The nodes in the order written: a binder, then its body."""
    for node in code:
        yield node
        if isinstance(node, Bind):
            yield from unfolded(node.body)


def spelled(node: Node) -> tuple[Item, ...]:
    """The items that write one node; a binder's body is written after it."""
    match node:
        case Push():
            return shown(node.value)
        case Call():
            return (named(node.name),)
        case Bind():
            return (Word("→", "name", (node.name,), "", START),)
        case Keyed():
            pairs = tuple(item for key, n in node.entries for item in (named(key), *spelled(n)))
            return (Enclosure("dict", (framed(pairs),), START),)
        case _:
            assert_never(node)


def stranding(node: Node | None) -> bool:
    """A push of a number, a string or a strand."""
    return isinstance(node, Push) and isinstance(node.value, int | Decimal | str | Strand)


def framed(items: tuple[Item, ...]) -> Frame:
    """Items as a frame of one cell, or of none."""
    return Frame((Cell(items, START),) if items else (), START)


def declaration(name: str, kind: Slot) -> tuple[Item, ...]:
    """An input as written: a value bare, a thunk `name: []`, code `name: Code`. The type a
    thunk was declared with is not kept (hole thunk-type-dropped)."""
    match kind:
        case "value":
            return (named(name),)
        case "thunk":
            return (named(name + ":"), Enclosure("quotation", (framed(()),), START))
        case "code":
            return (named(name + ":"), named("Code"))
        case _:
            assert_never(kind)


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
        case Listed() | Quotation() | Dict():
            return (enclosed(value),)
        case Symbol():
            return (Word("#", "name", (value.name,), "", START),)
        case _:
            numeral = format(value, "f") if isinstance(value, Decimal) else str(value)
            return (Word("", "number", (numeral,), "", START),)


def enclosed(value: Listed | Quotation | Dict) -> Enclosure:
    """A value written between its delimiters."""
    match value:
        case Listed():
            return Enclosure("group", (framed(spread(value.items)),), START)
        case Quotation():
            return Enclosure("quotation", sugared(value.code), START)
        case Dict():
            pairs = tuple(item for key, v in value.entries for item in (named(key), *shown(v)))
            return Enclosure("dict", (framed(pairs),), START)
        case _:
            assert_never(value)


def spread(values: tuple[Value, ...]) -> tuple[Item, ...]:
    """Values side by side."""
    return tuple(item for value in values for item in shown(value))
