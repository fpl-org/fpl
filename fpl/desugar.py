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
A head `name/` mounts its block as a directory: its definitions are named by path, and each
directory keeps an ordered log of its definitions, subdirectories and `#name bind` mounts, where
a later entry shadows an earlier one. A word's body is its own directory (decision f), so a name
in it is looked up from there outward, `..` from the directory holding the word, and every word
w has w/history, w/doc, its docstring, and w/effect.
A `match` line in a body takes the values its balance counts, and each line of its block is a
row: one pattern cell per value, then at most a body cell. A pattern is _, a name it binds, a
literal, $x, ( constructor patterns ) or p ∈ test; a match with no row of only _ and names
makes its word's effect +fail.
A line with no code, a comment's or the empty first line, is no statement and no child; its
comment is not carried into the core, but for a word's docs (fpl/trivia.py). Anything outside
the implemented set is refused before evaluation (hole unimplemented-words).
"""

from collections import ChainMap
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from decimal import Decimal
from functools import partial
from itertools import groupby
from typing import NoReturn, assert_never

from fpl import trivia
from fpl.ast_core import (
    DIGITS,
    EFFECTS,
    Atom,
    Bind,
    Call,
    Define,
    Dict,
    Effect,
    Equal,
    Guarded,
    Inverse,
    Keyed,
    Listed,
    Match,
    Node,
    Number,
    Pattern,
    Push,
    Quotation,
    Row,
    Run,
    Slot,
    Statement,
    Strand,
    Symbol,
    Value,
    Var,
    Wild,
)
from fpl.ast_surface import Cell, Comment, Enclosure, Frame, Item, Line, Program, Text, Word
from fpl.errors import FplError, Span

START = Span(1, 1)
ARROWS = ("→", "->")
LOCAL = Effect((), ("x",))
HISTORY = Effect((), ("h",))
DOC = Effect((), ("d",))
QUERIES = {"history": HISTORY, "doc": DOC, "effect": Effect((), ("e",))}

type Here = tuple[str, ...]


def unimplemented() -> NoReturn:
    """Refuse what no part implements yet, at the source's start."""
    raise FplError(START, "no evaluator yet")


def desugar(program: Program) -> tuple[Statement, ...]:
    """The program's lines as statements, in order, a directory's definitions named by path.
    Every effect is known before any line is read, so a word may be used above its definition;
    a later definition shadows."""
    lines = coded(program.lines)
    catalog = Catalog({(): list(EFFECTS)}, dict(EFFECTS))
    catalog.enter(lines, ())
    for here, log in catalog.logs.items():
        for entry in log:
            if isinstance(entry, Mount):
                catalog.directory(here, entry.name)
    return tuple(_Desugar(catalog, trivia.docstrings(program)).statements(lines, ()))


@dataclass(frozen=True)
class Mount:
    """#name bind: the directory name, as seen from the one it is bound in."""

    name: str


@dataclass
class Catalog:
    """Every directory's log, by path, and the effect of every word, by its path joined. A word
    is a directory too, holding its history."""

    logs: dict[Here, list[str | Mount]]
    effects: dict[str, Effect]

    def enter(self, lines: tuple[Line, ...], here: Here) -> None:
        """Log the definitions, subdirectories and mounts of one directory's lines."""
        log = self.logs.setdefault(here, [])
        for line in lines:
            head, name = definition(line), directory(line)
            if head is not None:
                log.append(head[0])
                path = "/".join((*here, head[0]))
                self.effects[path] = head[1]
                self.effects |= {f"{path}/{query}": e for query, e in QUERIES.items()}
                self.logs.setdefault((*here, head[0]), []).extend(QUERIES)
            elif name is not None:
                log.append(name)
                self.enter(coded(line.block), (*here, name))
            elif here:
                log.append(Mount(mount(line)))

    def directory(self, here: Here, name: str) -> Here:
        """The directory a name reaches from here outward; none is refused."""
        for depth in range(len(here), -1, -1):
            if (*here[:depth], name) in self.logs:
                return (*here[:depth], name)
        unimplemented()

    def lookup(self, here: Here, segments: Here) -> str | None:
        """The word a path names in one directory: the latest entry that holds it wins."""
        for entry in reversed(self.logs.get(here, [])):
            found = self.through(here, entry, segments)
            if found is not None:
                return found
        return None

    def through(self, here: Here, entry: str | Mount, segments: Here) -> str | None:
        """The word a path names through one entry: a subdirectory looks on in its own log, a
        mount only at the words its directory defines, so mounts never chain."""
        if isinstance(entry, Mount):
            path = "/".join((*self.directory(here, entry.name), *segments))
            return path if path in self.effects else None
        if entry != segments[0]:
            return None
        if len(segments) > 1:
            return self.lookup((*here, entry), segments[1:])
        path = "/".join((*here, entry))
        return path if path in self.effects else None

    def resolve(self, here: Here, segments: Here) -> str:
        """The word a path names from here, then each enclosing directory; none is refused."""
        for depth in range(len(here), -1, -1):
            found = self.lookup(here[:depth], segments)
            if found is not None:
                return found
        unimplemented()


def directory(line: Line) -> str | None:
    """The name of a `name/` head; a head with no block, or a deeper path, is refused."""
    items = [item for frame in line.frames for cell in frame.cells for item in cell.items]
    match items:
        case [Word(prefix="", kind="path", body=(name, ""), mods="")] if line.block:
            return name
        case [Word(kind="path", body=(*_, "")), *_]:
            unimplemented()
        case _:
            return None


def mount(line: Line) -> str:
    """The name of a `#name bind` line; any other line in a directory is refused."""
    items = [item for frame in line.frames for cell in frame.cells for item in cell.items]
    match items:
        case [Word(prefix="#", kind="name", body=(name,), mods=""), word] if plain(word) == "bind":
            return name
        case _:
            unimplemented()


def coded(lines: tuple[Line, ...]) -> tuple[Line, ...]:
    """The lines that hold code: a bar, or an item in a frame. A line with none is a comment's
    or the empty first line, and heading a block it is refused (holes comment-heads-block,
    empty-first-line)."""
    kept: list[Line] = []
    for line in lines:
        if trivia.code(line):
            kept.append(line)
        elif line.block:
            unimplemented()
    return tuple(kept)


def definition(line: Line) -> tuple[str, Effect] | None:
    """The name and effect of a `name : ins -- outs` line; None for a line that is not one."""
    if not trivia.head(line):
        return None
    cells = line.frames[0].cells
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
    refused, and so is a numeral of more than DIGITS digits, at its position."""
    if not isinstance(item, Word) or item.prefix or item.mods or not item.body[0][-1].isdigit():
        unimplemented()
    numeral = item.body[0]
    if sum(map(str.isdecimal, numeral)) > DIGITS:
        raise FplError(item.span, "number too long")
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


def fallible(code: tuple[Node, ...]) -> bool:
    """Some match in the code, outside a quotation, has no row that catches every value."""
    for node in code:
        if isinstance(node, Match) and not any(map(catches, node.rows)):
            return True
        if isinstance(node, Bind) and fallible(node.body):
            return True
    return False


def catches(row: Row) -> bool:
    """Every pattern of the row is _ or a name."""
    return all(isinstance(pattern, Wild | Var) for pattern in row.patterns)


def matcher(line: Line) -> bool:
    """A line of the one word match, with the rows as its block."""
    items = [item for frame in line.frames for cell in frame.cells for item in cell.items]
    return bool(line.block) and len(items) == 1 and plain(items[0]) == "match"


def literal(item: Item) -> bool:
    """A number or a string: what strands."""
    return isinstance(item, Text) or (isinstance(item, Word) and item.kind == "number")


class _Desugar:
    """Lines to code, with the effect of every word known."""

    def __init__(self, catalog: Catalog, docs: dict[int, str]) -> None:
        """Keep the catalog, the docstrings by the line they document, and the effect of every
        word a line may call: the builtins' and the definitions', by path."""
        self.catalog = catalog
        self.docs = docs
        self.effects = ChainMap(catalog.effects)
        self.here: Here = ()

    def statements(self, lines: tuple[Line, ...], here: Here) -> Iterator[Statement]:
        """A directory's definitions and, at the top, the lines to run."""
        for line in lines:
            head, name = definition(line), directory(line)
            if head is not None:
                path = (*here, head[0])
                code = self.body(line.block, len(head[1].ins), path)
                effect = replace(head[1], fails=fallible(code))
                doc = self.docs.get(line.span.line, "")
                yield Define("/".join(path), effect, code, doc, line.span)
            elif name is not None:
                yield from self.statements(coded(line.block), (*here, name))
            elif not here:
                yield Run(self.body((line,), 0, here))

    def body(self, lines: tuple[Line, ...], balance: int, here: Here) -> tuple[Node, ...]:
        """Lines on one stack in turn, each starting on the balance the one before left, their
        names looked up from here. A name bound in them dies with them, and one bound in a
        section with the section."""
        outer = self.effects
        self.here = here
        code: list[Node] = []
        for line in coded(lines):
            if matcher(line):
                code.append(self.match(line, balance))
                balance = 0
                continue
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
            case Match():  # pragma: no cover -- a match is a line of its own, never in a frame
                return len(node.rows[0].patterns), 0
            case Call():
                effect = self.effects[node.name]
                return len(effect.ins), len(effect.outs)
            case _:
                assert_never(node)

    def match(self, line: Line, arity: int) -> Match:
        """The rows of a match taking arity values; a block of comments alone, no rows, is
        refused at the word."""
        word = line.frames[0].cells[0].items[0]
        rows = tuple(self.row(row, arity) for row in coded(line.block))
        if not rows:
            raise FplError(word.span, "a match has no rows")
        return Match(rows, word.span)

    def row(self, line: Line, arity: int) -> Row:
        """arity pattern cells, then at most a body cell, where the names they bind are read."""
        cells = [cell for frame in line.frames for cell in frame.cells]
        if line.block or len(line.frames) > 1 or len(cells) - arity not in (0, 1):
            raise FplError(line.span, f"a row is {arity} patterns and a body")
        outer = self.effects
        patterns = tuple(self.pattern(cell.items) for cell in cells[:arity])
        body = self.frame(Frame(tuple(cells[arity:]), line.span))
        self.effects = outer
        return Row(patterns, scoped(body))

    def pattern(self, items: tuple[Item, ...]) -> Pattern:
        """The one pattern of a cell or of ( p ∈ test )."""
        found = self.patterns(items)
        if len(found) != 1:
            unimplemented()
        return found[0]

    def patterns(self, items: tuple[Item, ...]) -> tuple[Pattern, ...]:
        """Items as patterns in turn, `∈ test` guarding the one before it."""
        found: list[Pattern] = []
        marks = iter(items)
        for item in marks:
            if plain(item) == "∈" and found:
                test = next(marks, None)
                if not isinstance(test, Word):
                    unimplemented()
                found[-1] = Guarded(found[-1], self.call(test).name, item.span)
            else:
                found.append(self.simple(item))
        return tuple(found)

    def simple(self, item: Item) -> Pattern:
        """_, $x of a bound name, a name it binds, ( constructor patterns ), ( p ∈ test ) or
        a literal."""
        match item:
            case Word(prefix="", kind="name", body=("_",), mods=""):
                return Wild()
            case Word(prefix="$", kind="name", body=(name,), mods="") if self.local(name):
                return Equal(Call(name, item.span))
            case Word() if plain(item) is not None:
                self.effects = self.effects.new_child({item.body[0]: LOCAL})
                return Var(item.body[0])
            case Enclosure(pair="prefix"):
                return self.inverse(contents(item))
            case _:
                return self.constant(item)

    def local(self, name: str) -> bool:
        """A name bound by a binder or an earlier pattern."""
        return any(name in scope for scope in self.effects.maps[:-1])

    def constant(self, item: Item) -> Equal:
        """A literal, matching by equality."""
        nodes = self.item(item)
        if len(nodes) != 1 or not isinstance(nodes[0], Push):
            unimplemented()
        return Equal(nodes[0])

    def inverse(self, items: list[Item]) -> Pattern:
        """( p ∈ test ), or a constructor taking one pattern per input and leaving one value."""
        if len(items) > 1 and plain(items[1]) == "∈":
            return self.pattern(tuple(items))
        head, *args = items
        if not isinstance(head, Word):
            unimplemented()
        name = self.call(head).name
        effect, found = self.effects[name], self.patterns(tuple(args))
        if len(effect.outs) != 1:
            raise FplError(head.span, f"{name} is not invertible")
        if len(found) != len(effect.ins):
            raise FplError(head.span, f"{name} takes {len(effect.ins)} patterns")
        return Inverse(name, found, head.span)

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
            name = "/".join(word.body) if word.kind == "path" and word.body[-1] else bare(word)
            self.effects = self.effects.new_child({name: LOCAL})
            return Bind(name, (), word.span)
        return self.call(word)

    def call(self, word: Word) -> Call:
        """A word bound on its line, else the one its path names from here, or from the
        directory holding here after `..`."""
        path = "/".join(word.body)
        if not (word.prefix or word.mods) and any(path in s for s in self.effects.maps[:-1]):
            return Call(path, word.span)
        return Call(self.catalog.resolve(self.origin(word), word.body), word.span)

    def origin(self, word: Word) -> Here:
        """Where a word's lookup starts: here, or after `..` the directory holding here; a
        modifier or another sigil is refused."""
        match word.prefix:
            case "" if not word.mods:
                return self.here
            case "../" if self.here and not word.mods:
                return self.here[:-1]
            case _:
                unimplemented()

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
    would otherwise strand, no ( ), no block but a definition's one-line body and its docs."""
    return Program(tuple(line for s in statements for line in (*above(s), written(s))), START)


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
            fails = ("+fail",) if effect.fails else ()
            ins = zip(effect.ins, effect.slots, strict=True)
            taken = (item for name, kind in ins for item in declaration(name, kind))
            head = (named(statement.name), named(":"), *taken, named("--"))
            body = (Line(sugared(statement.code), (), START),) if statement.code else ()
            outs = (*effect.outs, *fails)
            return Line((framed((*head, *map(named, outs))),), documented(statement) + body, START)
        case _:
            assert_never(statement)


def documented(statement: Define) -> tuple[Line, ...]:
    """A definition's docstring as the ;; lines opening its body; none when it has no body,
    as its docs are written above its head instead."""
    return doc_lines(statement.doc) if statement.code else ()


def above(statement: Statement) -> tuple[Line, ...]:
    """The ;; lines written above a statement: the docstring of a definition with no code,
    which under its head would be read as the next code line's (fpl/trivia.py); none else."""
    if isinstance(statement, Define) and not statement.code:
        return doc_lines(statement.doc)
    return ()


def doc_lines(doc: str) -> tuple[Line, ...]:
    """A docstring as ;; lines, one for each of its lines; none for the empty one."""
    texts = doc.split("\n") if doc else []
    return tuple(Line((), (), START, Comment(2, (f";; {text}",), START)) for text in texts)


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
            return (Word("→", named(node.name).kind, named(node.name).body, "", START),)
        case Keyed():
            pairs = tuple(item for key, n in node.entries for item in (named(key), *spelled(n)))
            return (Enclosure("dict", (framed(pairs),), START),)
        case Match():
            unimplemented()
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
    """A name as written, a path when it holds a slash."""
    segments = tuple(name.split("/"))
    return Word("", "path" if len(segments) > 1 else "name", segments, "", START)


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
