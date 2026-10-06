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
A word with two or more keys, or one with a typed input, is dispatched (design 09 §1.1): its
i-th key of arity n is the clause f/n/i, and f/n its dispatcher, one row per clause guarding
each typed input with its type word and calling the clause, the most typed inputs first and the
newest first among as many; a call takes the arity group its balance picks.
"""

from collections import ChainMap
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field, replace
from decimal import Decimal
from functools import partial
from itertools import combinations, groupby
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
    Refuse,
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
from fpl.print import render

START = Span(1, 1)
ARROWS = ("→", "->")
LOCAL = Effect((), ("x",))
HISTORY = Effect((), ("h",))
DOC = Effect((), ("d",))
QUERIES = {"history": HISTORY, "doc": DOC, "effect": Effect((), ("e",))}
PRIME = "\N{PRIME}"
TYPES = frozenset(("Int", "Decimal", "Text", "Symbol"))

type Here = tuple[str, ...]
type Part = str | None
type Key = tuple[Part, ...]
type Head = tuple[Effect, Span]
type Pair = tuple[int, int]
type Clause = tuple[str, Effect]


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
    catalog.settle()
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
    is a directory too, holding its history. Each word's heads by key, in the order first
    written; each dispatched word's arities; the queries that answer at another path, and those
    refused; per arity group the pairs of clauses that cross typed two ways at one input."""

    logs: dict[Here, list[str | Mount]]
    effects: dict[str, Effect]
    heads: dict[str, dict[Key, Head]] = field(default_factory=dict[str, dict[Key, Head]])
    groups: dict[str, tuple[int, ...]] = field(default_factory=dict[str, tuple[int, ...]])
    aliases: dict[str, str] = field(default_factory=dict[str, str])
    refused: dict[str, str] = field(default_factory=dict[str, str])
    crossings: dict[str, list[Pair]] = field(default_factory=dict[str, list[Pair]])

    def enter(self, lines: tuple[Line, ...], here: Here) -> None:
        """Log the definitions, subdirectories and mounts of one directory's lines."""
        log = self.logs.setdefault(here, [])
        for line in lines:
            head, name = definition(line), directory(line)
            if head is not None:
                log.append(head[0])
                self.keyed("/".join((*here, head[0])), head[1], line.span)
                self.queried((*here, head[0]), head[1], [])
            elif name is not None:
                log.append(name)
                self.enter(coded(line.block), (*here, name))
            elif here:
                log.append(Mount(mount(line)))

    def keyed(self, path: str, effect: Effect, span: Span) -> None:
        """Note a definition's head by its key, a same key shadowing in its place; it must take
        the slot kinds and leave the values of every other key of its arity, else it is refused
        at its head (design 09 §2.3)."""
        heads, key = self.heads.setdefault(path, {}), keyed(effect)
        group = [other for other in heads if len(other) == len(key)]
        at = group.index(key) + 1 if key in group else len(group) + 1
        for i, other in enumerate(group, 1):
            if other != key:
                agree(f"{path}/{len(key)}", (at, effect, span), (i, heads[other][0]))
        heads[key] = (effect, span)

    def queried(self, here: Here, effect: Effect, entries: list[str]) -> None:
        """A word at here, its effect and its queries, its log holding entries before them."""
        path = "/".join(here)
        self.effects[path] = effect
        self.effects |= {f"{path}/{query}": e for query, e in QUERIES.items()}
        self.logs.setdefault(here, []).extend([*entries, *QUERIES])

    def settle(self) -> None:
        """Dispatch each word with two or more keys, or one with a typed input."""
        builtins = TYPES - {path.rsplit("/", 1)[-1] for path in self.heads}
        for path, heads in self.heads.items():
            if len(heads) > 1 or any(typings(effect) for effect, _ in heads.values()):
                self.dispatched(path, builtins)

    def clauses(self, path: str, n: int) -> list[Head]:
        """A word's clauses of arity n, by path ordinal."""
        return [head for key, head in self.heads[path].items() if len(key) == n]

    def ordinal(self, path: str, effect: Effect) -> int:
        """The ordinal of a clause's key among its arity's."""
        key = keyed(effect)
        return [k for k in self.heads[path] if len(k) == len(key)].index(key) + 1

    def dispatched(self, path: str, builtins: frozenset[str]) -> None:
        """A word's arity groups f/n, each with its clauses f/n/i, of which two whose typed
        inputs cross are refused unless builtins make them disjoint or their meet is a clause or
        is typed two ways at one input;
        f/n's doc and history are its clause's when it has one, refused naming its clauses
        otherwise; f's queries are those of its only group, refused naming its groups when it
        has more."""
        here = tuple(path.split("/"))
        groups = {len(key): self.clauses(path, len(key)) for key in self.heads[path]}
        self.groups[path] = tuple(sorted(groups))
        for n, clauses in groups.items():
            self.crossings[f"{path}/{n}"] = crossed(f"{path}/{n}", clauses, builtins)
            self.logs[here].append(str(n))
            ordinals = [str(i) for i in range(1, len(clauses) + 1)]
            self.queried((*here, str(n)), shared([effect for effect, _ in clauses]), ordinals)
            for i, (clause, _) in zip(ordinals, clauses, strict=True):
                self.queried((*here, str(n), i), clause, [])
            self.answered(f"{path}/{n}", [f"{path}/{n}/{i}" for i in ordinals], "clause")
        self.effects[path] = self.effects[f"{path}/{self.groups[path][0]}"]
        self.answered(path, [f"{path}/{n}" for n in self.groups[path]], "group")

    def answered(self, path: str, parts: list[str], kind: str) -> None:
        """path's doc and history, and at a word its effect, answer as at its one part; with
        more they are refused naming them."""
        queries = ("history", "doc") if kind == "clause" else tuple(QUERIES)
        for query in queries:
            asked = f"{path}/{query}"
            if len(parts) > 1:
                self.refused[asked] = f"{asked} names more than one {kind}: {' '.join(parts)}"
                continue
            answer = f"{parts[0]}/{query}"
            self.aliases[asked] = self.aliases.get(answer, answer)
            if answer in self.refused:
                self.refused[asked] = self.refused[answer].replace(answer, asked, 1)

    def dispatch(self, path: str, balance: int) -> str:
        """The arity group a call on balance values takes: the largest arity it saturates, else
        the smallest; the path itself for a word not dispatched."""
        groups = self.groups.get(path)
        if groups is None:
            return path
        fits = [n for n in groups if n <= balance]
        return f"{path}/{max(fits, default=groups[0])}"

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
    slots: tuple[Slot, ...] = tuple(kind for _, kind, _ in declared[:cut])
    types = tuple(part for _, _, part in declared[:cut])
    return name, Effect(tuple(names[:cut]), tuple(names[cut + 1 :]), slots=slots, types=types)


def typed(items: tuple[Item, ...]) -> list[tuple[str, Slot, Part]]:
    """Each plain name with its slot and type: `name: Type` has the slot its type makes, a bare
    name is an untyped value (hole bare-slot-names); `∈` is refused."""
    declared: list[tuple[str, Slot, Part]] = []
    rest = iter(items)
    for item in rest:
        name = plain(item)
        if isinstance(item, Enclosure) and item.pair == "prefix":
            declared.append(("_", "value", spelt(item)))
        elif name is None or name == "∈":
            unimplemented()
        elif ascribed(item):
            declared.append((name[:-1], *slot(next(rest, None))))
        else:
            declared.append((name, "value", None))
    return declared


def slot(kind: Item | None) -> tuple[Slot, Part]:
    """The slot a type makes (S49 rule 5), and its type: [ ] a thunk, Code code, both untyped; a
    name a value of that type (a word x -- b). A `name:` with no type after it is refused, and
    so is a compound type (hole compound-type)."""
    if kind is None or plain(kind) == "--":
        unimplemented()
    if isinstance(kind, Enclosure) and kind.pair == "quotation":
        return "thunk", None
    part = plain(kind)
    if part is None:
        unimplemented()
    return ("code", None) if part == "Code" else ("value", part)


def ascribed(item: Item) -> bool:
    """A plain `name:`, whose type follows it."""
    name = plain(item)
    return name is not None and len(name) > 1 and name.endswith(":")


def grouped(part: Part) -> bool:
    """A slot's type is a group `( p )`, written as the printer writes it."""
    return part is not None and part.startswith("(")


def spelt(item: Item) -> str:
    """An item as the printer writes it."""
    line = Line((framed((item,)),), (), START)
    return render(Program((Line((), (), START), line), START)).strip()


def pins(items: list[Item]) -> bool:
    """Items holding a `$` pin, at any depth."""
    return any(
        (isinstance(item, Word) and item.prefix == "$")
        or (isinstance(item, Enclosure) and pins(contents(item)))
        for item in items
    )


def keyed(effect: Effect) -> Key:
    """A definition's key: per input its type, a thunk or code slot its kind (hole
    clause-identity)."""
    pairs = zip(effect.slots, effect.types, strict=True)
    return tuple(part if kind == "value" else kind for kind, part in pairs)


def agree(group: str, later: tuple[int, Effect, Span], earlier: tuple[int, Effect]) -> None:
    """Two clauses of one arity group take the same slot kinds and leave as many values, else
    the later is refused at its head."""
    at, effect, span = later
    i, other = earlier
    for position, (kind, before) in enumerate(zip(effect.slots, other.slots, strict=True), 1):
        if kind != before:
            message = f"{group}/{at} takes a {kind} at {position}, {group}/{i} a {before}"
            raise FplError(span, message)
    if len(effect.outs) != len(other.outs):
        message = f"{group}/{at} leaves {len(effect.outs)}, {group}/{i} {len(other.outs)}"
        raise FplError(span, message)


def typings(effect: Effect) -> frozenset[int]:
    """The typed inputs of a clause, by position."""
    return frozenset(i for i, part in enumerate(effect.types) if part is not None)


def crossed(group: str, clauses: list[Head], builtins: frozenset[str]) -> list[Pair]:
    """Refuse two clauses each typed where the other is not, unless disjoint, two different
    builtins at one position, or their meet, each input typed as either types it, is itself a
    clause: at the later head, naming the meet (design 09 §3.3). The pairs, by ordinal, whose
    meet one input would type two ways: only a run can tell whether both fit (§3.4)."""
    written = {effect.types for effect, _ in clauses}
    undecided: list[Pair] = []
    for a, b in combinations(enumerate(clauses, 1), 2):
        first, second = a[1][0], b[1][0]
        ordered = typings(first) <= typings(second) or typings(second) <= typings(first)
        if ordered or disjoint(first, second, builtins):
            continue
        meet = met(first, second)
        if meet is None:
            undecided.append((a[0], b[0]))
        elif meet.types not in written:
            (later, (_, span)), (earlier, _) = sorted((a, b), key=lambda c: -c[1][1].line)
            message = f"{group}/{later} is ambiguous with {group}/{earlier} at {spoken(meet)}"
            raise FplError(span, message)
    return undecided


def disjoint(a: Effect, b: Effect, builtins: frozenset[str]) -> bool:
    """Two clauses no value fits both of: two different builtins at one position."""
    return any(x != y and {x, y} <= builtins for x, y in zip(a.types, b.types, strict=True))


def met(a: Effect, b: Effect) -> Effect | None:
    """Two clauses' meet: a's effect, each input typed as either types it; None when both type
    one input differently."""
    pairs = list(zip(a.types, b.types, strict=True))
    if any(x is not None and y is not None and x != y for x, y in pairs):
        return None
    return replace(a, types=tuple(x or y for x, y in pairs))


def spoken(effect: Effect) -> str:
    """An effect's inputs as a head writes them, `x: T` where typed, two spaces apart."""
    pairs = zip(effect.ins, effect.types, strict=True)
    return "  ".join(name if part is None else f"{name}: {part}" for name, part in pairs)


def shared(clauses: list[Effect]) -> Effect:
    """A dispatcher's effect: its first clause's, keeping a type only where all agree."""
    first = clauses[0]
    types = tuple(
        part if all(c.types[i] == part for c in clauses) else None
        for i, part in enumerate(first.types)
    )
    return replace(first, types=types)


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
        self.dispatchers: set[str] = set()

    def statements(self, lines: tuple[Line, ...], here: Here) -> Iterator[Statement]:
        """A directory's definitions and, at the top, the lines to run."""
        for line in lines:
            head, name = definition(line), directory(line)
            if head is not None:
                path = (*here, head[0])
                code = self.code(line, head[1], path)
                effect = replace(head[1], fails=fallible(code))
                doc = self.docs.get(line.span.line, "")
                yield from self.defined(Define("/".join(path), effect, code, doc, line.span), here)
            elif name is not None:
                yield from self.statements(coded(line.block), (*here, name))
            elif not here:
                yield Run(self.body((line,), 0, here), line.span)

    def code(self, line: Line, effect: Effect, here: Here) -> tuple[Node, ...]:
        """A definition's code: its body; with a head group, one row binding a fresh name at
        every other input and the group's pattern at each group, the other inputs pushed back in
        order, then the body, which sees the group's names (design 09 §2.4). A `$` pin in a
        head group is refused (hole head-group-pin)."""
        groups = iter(
            i
            for i in line.frames[0].cells[0].items[2:]
            if isinstance(i, Enclosure) and i.pair == "prefix"
        )
        if not any(map(grouped, effect.types)):
            return self.body(line.block, len(effect.ins), here)
        outer, patterns, repush = self.effects, list[Pattern](), list[Node]()
        self.here = here
        for name, part in zip(fresh(effect), effect.types, strict=True):
            if grouped(part):
                group = next(groups)
                if pins(contents(group)):
                    unimplemented()
                patterns.append(self.simple(group))
            else:
                patterns.append(Var(name))
                repush.append(Call(name, line.span))
        body = self.body(line.block, len(repush), here)
        self.effects = outer
        return (Match((Row(tuple(patterns), (*repush, *body)),), line.span),)

    def defined(self, define: Define, here: Here) -> Iterator[Define]:
        """A definition; of a dispatched word, its clause, and after the first clause of an
        arity its dispatcher at that clause's head (design 09 §2.4)."""
        if define.name not in self.catalog.groups:
            yield define
            return
        n = len(define.effect.ins)
        clause = replace(define, clause=(n, self.catalog.ordinal(define.name, define.effect)))
        yield clause
        yield from tests(clause)
        group = f"{define.name}/{n}"
        if group not in self.dispatchers:
            self.dispatchers.add(group)
            yield self.dispatcher(define.name, n, clause.span, here)

    def dispatcher(self, name: str, n: int, span: Span, here: Here) -> Define:
        """The dispatcher of an arity group: a row per clause and a refusing row per pair that
        crosses typed two ways at one input, the most typed inputs first; among as many the
        clauses' rows, newest first, then the refusing ones (design 09 §3.2); +fail when no
        row catches every value."""
        group = f"{name}/{n}"
        clauses = [(f"{group}/{i}", c) for i, (c, _) in enumerate(self.catalog.clauses(name, n), 1)]
        ranked = [
            ((-len(typings(effect)), 0, -i, 0), self.guarding(word, effect, span, here))
            for i, (word, effect) in enumerate(clauses, 1)
        ]
        for i, j in self.catalog.crossings[group]:
            sides = (clauses[i - 1], clauses[j - 1])
            count = len(typings(sides[0][1]) | typings(sides[1][1]))
            ranked.append(((-count, 1, i, j), self.refusing(name, sides, span, here)))
        rows = tuple(row for _, row in sorted(ranked, key=lambda rank: rank[0]))
        code = (Match(rows, span),)
        effect = replace(self.catalog.effects[group], fails=fallible(code))
        words = tuple(word for word, _ in clauses)
        return Define(name, effect, code, span=span, clause=(n,), clauses=words)

    def guarding(self, word: str, effect: Effect, span: Span, here: Here) -> Row:
        """A clause's dispatcher row: at each input a fresh name, its slot's name, a prime and
        its position, guarding each typed input with its test, then every input pushed back in
        order and the clause called."""
        names = fresh(effect)
        tests = zip(names, self.checks(word, effect, here), strict=True)
        patterns = tuple(guard(Var(name), (test,), span) for name, test in tests)
        return Row(patterns, (*(Call(name, span) for name in names), Call(word, span)))

    def refusing(self, name: str, sides: tuple[Clause, Clause], span: Span, here: Here) -> Row:
        """The row fitting where both clauses fit, each input under the first clause's test and
        then the second's, refusing the call as ambiguous (design 09 §2.4)."""
        tests = [self.checks(word, effect, here) for word, effect in sides]
        patterns = tuple(guard(Wild(), column, span) for column in zip(*tests, strict=True))
        both = " and ".join(word for word, _ in sides)
        return Row(patterns, (Refuse(f"ambiguous call to {name}: {both} both fit", span),))

    def checks(self, word: str, effect: Effect, here: Here) -> list[str | None]:
        """The test of each input of a clause, None where it is untyped."""
        return [
            None if part is None else self.tested(word, part, i, here)
            for i, part in enumerate(effect.types, 1)
        ]

    def tested(self, word: str, part: str, position: int, here: Here) -> str:
        """The word testing a clause's typed input: a group's generated word, else the word its
        type names from the directory of its definition, on one value."""
        if grouped(part):
            return f"{word}{PRIME}{position}"
        return self.catalog.dispatch(self.catalog.resolve(here, (part,)), 1)

    def routed(self, nodes: tuple[Node, ...], balance: int) -> tuple[Node, ...]:
        """The nodes, each call of a dispatched word taking the arity group its balance picks;
        a word reaching below the balance leaves it at what it adds."""
        out: list[Node] = []
        for node in nodes:
            taken = node
            if isinstance(node, Call) and not self.local(node.name):
                taken = Call(self.catalog.dispatch(node.name, balance), node.span)
            takes, leaves = self.arity(taken)
            balance = max(0, balance - takes) + leaves
            out.append(taken)
        return tuple(out)

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
                written = part()
                nodes = self.routed(written, balance)
                after = self.balance(nodes, balance)
                if after is None:
                    nodes, after = (Push(Quotation(scoped(self.routed(written, 0)))),), balance + 1
                    self.effects = before
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
            case Refuse():  # pragma: no cover -- a dispatcher's code is generated, never routed
                return 0, 0
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
        body = self.routed(self.frame(Frame(tuple(cells[arity:]), line.span)), 0)
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
                found[-1] = self.guarded(found[-1], next(marks, None), item.span)
            elif isinstance(item, Word) and ascribed(item):
                name = replace(item, body=(item.body[0][:-1],))
                found.append(self.guarded(self.simple(name), next(marks, None), item.span))
            else:
                found.append(self.simple(item))
        return tuple(found)

    def guarded(self, pattern: Pattern, test: Item | None, span: Span) -> Guarded:
        """A pattern that fits where it matches and its test word leaves 1."""
        if not isinstance(test, Word):
            unimplemented()
        return Guarded(pattern, self.catalog.dispatch(self.call(test).name, 1), span)

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
        if not items:
            unimplemented()
        if len(items) > 1 and (plain(items[1]) == "∈" or ascribed(items[0])):
            return self.pattern(tuple(items))
        head, *args = items
        if not isinstance(head, Word):
            unimplemented()
        called = self.call(head).name
        found = self.patterns(tuple(args))
        name = self.catalog.dispatch(called, len(found))
        effect = self.effects[name]
        if len(effect.outs) != 1:
            raise FplError(head.span, f"{name} is not invertible")
        if len(found) != len(effect.ins):
            raise FplError(head.span, f"{name} takes {len(effect.ins)} patterns")
        return Inverse(name, found, head.span)

    def quote(self, build: Callable[[], tuple[Node, ...]]) -> Push:
        """Code built in a scope of its own, pushed as a quotation."""
        outer = self.effects
        code = self.routed(build(), 0)
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
        inputs = self.inputs(self.routed(self.frames(line.frames), len(block)))
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
        path = self.catalog.resolve(self.origin(word), word.body)
        if path in self.catalog.refused:
            raise FplError(word.span, self.catalog.refused[path])
        return Call(self.catalog.aliases.get(path, path), word.span)

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
            key, nodes = plain(key_item), self.routed(self.item(value_item), 0)
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
    would otherwise strand, no ( ), no block but a definition's one-line body and its docs; a
    dispatcher is generated, never written."""
    kept = (s for s in statements if not generated(s))
    return Program(tuple(line for s in kept for line in (*above(s), written(s))), START)


def generated(statement: Statement) -> bool:
    """A dispatcher, a group's test word or a clause with a group: made from a head, never
    written back (hole resugar-match)."""
    if not isinstance(statement, Define):
        return False
    made = len(statement.clause) == 1 or PRIME in statement.name
    return made or any(map(grouped, statement.effect.types))


def guard(pattern: Pattern, tests: Iterable[str | None], span: Span) -> Pattern:
    """The pattern guarded by each test in turn, the first innermost; None is no test."""
    for test in tests:
        if test is not None:
            pattern = Guarded(pattern, test, span)
    return pattern


def fresh(effect: Effect) -> list[str]:
    """A fresh name per input: its slot's name, a prime and its position (design 09 §2.4)."""
    return [f"{name}{PRIME}{i}" for i, name in enumerate(effect.ins, 1)]


def tests(clause: Define) -> Iterator[Define]:
    """For each group of a clause, the word x -- b leaving 1 where the group matches, else 0,
    named by the clause's word, a prime and the group's position."""
    for position, part in enumerate(clause.effect.types, 1):
        match clause.code:
            case (Match(rows=(row,)),) if grouped(part):
                fits = Row((row.patterns[position - 1],), (Push(1),))
                code = Match((fits, Row((Wild(),), (Push(0),))), clause.span)
                name = f"{clause.word}{PRIME}{position}"
                yield Define(name, Effect(("x",), ("b",)), (code,), span=clause.span)
            case _:
                pass


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
            ins = zip(effect.ins, effect.slots, effect.types, strict=True)
            taken = (item for name, kind, part in ins for item in declaration(name, kind, part))
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
        case Match() | Refuse():
            unimplemented()
        case _:
            assert_never(node)


def stranding(node: Node | None) -> bool:
    """A push of a number, a string or a strand."""
    return isinstance(node, Push) and isinstance(node.value, int | Decimal | str | Strand)


def framed(items: tuple[Item, ...]) -> Frame:
    """Items as a frame of one cell, or of none."""
    return Frame((Cell(items, START),) if items else (), START)


def declaration(name: str, kind: Slot, part: Part) -> tuple[Item, ...]:
    """An input as written: a value bare or `name: Type`, a thunk `name: []`, code `name: Code`.
    The type a thunk was declared with is not kept (hole thunk-type-dropped)."""
    match kind:
        case "value" if part is not None:
            return (named(name + ":"), named(part))
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
