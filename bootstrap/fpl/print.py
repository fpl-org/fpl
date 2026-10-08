"""The surface AST as canonical source; the printer is the only normaliser.

Items are joined by a space, cells by a tab, frames by a bar between spaces (an empty frame
prints nothing); an enclosure prints as "o body c", or "oc" when it holds one empty frame; a block
line carries one tab per level; a note stands in a cell of its own after its line's code, its
continuation lines carrying as many tabs as stand before it; a comment is printed as written; a
note on a line of its own after a line that ends in a note has a blank line before it, which ends
the note it would otherwise continue; no code line ends in a space; a program ends in a newline,
and one empty line is the empty text.
"""

from typing import assert_never

from fpl.ast_surface import Cell, Comment, Enclosure, Frame, Item, Line, Pair, Program, Text, Word
from fpl.errors import FplError, Span

DELIMITERS: dict[Pair, tuple[str, str]] = {
    "quotation": ("[", "]"),
    "prefix": ("(", ")"),
    "group": ("⟨", "⟩"),
    "dict": ("{", "}"),
}


def render(program: Program) -> str:
    """Canonical source for a program: parse(render(p)) == p for every tree the parser can
    give (cells hold items, an enclosure holds a frame, a program a line, and only its first
    line is empty), and render∘parse is idempotent. One empty line is the empty text. A tree
    nested deeper than the build can recurse to is refused at the start, as the parser refuses
    such source (issue #95)."""
    out = _Out()
    try:
        out.lines(program.lines, 0)
    except RecursionError:
        raise FplError(Span(1, 1), "nesting too deep to print") from None
    text = "".join(out.chunks)
    return text + "\n" if text else ""


class _Out:
    """Source as it is written, with the tabs that open its current physical line: a string's
    continuation lines carry them, since the parser drops them (S26); and whether the last line
    written ends in a note."""

    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.tabs = 0
        self.leading = True
        self.column = 0
        self.noted = False

    def put(self, text: str) -> None:
        """Append text, keeping count of the tabs that open the physical line it ends on, and of
        all the tabs on it (the column, in elastic tabstops)."""
        self.chunks.append(text)
        newline = text.rfind("\n")
        if newline >= 0:
            self.tabs, self.leading, self.column, text = 0, True, 0, text[newline + 1 :]
        self.column += text.count("\t")
        if self.leading:
            rest = text.lstrip("\t")
            self.tabs += len(text) - len(rest)
            self.leading = not rest

    def lines(self, lines: tuple[Line, ...], depth: int) -> None:
        """Lines at `depth` tabs, each followed by its block, a newline between two."""
        for n, line in enumerate(lines):
            if n:
                self.put("\n")
            self.line(line, depth)

    def line(self, line: Line, depth: int) -> None:
        """One line and its block, one level deeper. A note on a line of its own right after a
        line that ends in a note would read back as that note's continuation, so a blank line,
        which ends a note, stands between them."""
        code = _code(line.frames)
        note = line.comment is not None and line.comment.level == 1
        if self.noted and note and not code:
            self.put("\n")
        self.put("\t" * depth)
        self.frames(line.frames)
        if line.comment is not None:
            self.comment(line.comment, code)
        self.noted = note
        for inner in line.block:
            self.put("\n")
            self.line(inner, depth + 1)

    def comment(self, comment: Comment, code: bool) -> None:
        """A comment as written: a note after code in a cell of its own, its continuation lines
        aligned under it by their tabs."""
        first, *rest = comment.lines
        self.put("\t" if code else "")
        column = self.column
        self.put(first)
        for more in rest:
            self.put("\n" + "\t" * column + more)

    def frames(self, frames: tuple[Frame, ...]) -> None:
        """Frames between bars; an empty frame adds only its bar."""
        written = False
        for n, frame in enumerate(frames):
            if n:
                self.put(" |" if written else "|")
                written = True
            if frame.cells:
                self.put(" " if written else "")
                self.cells(frame.cells)
                written = True

    def cells(self, cells: tuple[Cell, ...]) -> None:
        """Cells between tabs, items between spaces."""
        for n, cell in enumerate(cells):
            self.put("\t" if n else "")
            for k, item in enumerate(cell.items):
                self.put(" " if k else "")
                self.item(item)

    def item(self, item: Item) -> None:
        """A word as written, a string, or an enclosure."""
        match item:
            case Word():
                self.put(item.prefix + "/".join(item.body) + item.mods)
            case Text():
                self.text(item)
            case Enclosure():
                self.enclosure(item)
            case _:
                assert_never(item)

    def enclosure(self, enclosure: Enclosure) -> None:
        """o body c, or oc when one empty frame is inside."""
        opener, closer = DELIMITERS[enclosure.pair]
        if not _code(enclosure.frames):
            self.put(opener + closer)
            return
        self.put(opener + " ")
        self.frames(enclosure.frames)
        self.put(" " + closer)

    def text(self, text: Text) -> None:
        """A raw string verbatim; an interpolating one with its continuation lines indented as
        the line it opens on, and its islands as programs."""
        if text.kind == "raw":
            self.put(f"「{''.join(str(part) for part in text.parts)}」")
            return
        indent = "\n" + "\t" * self.tabs
        self.put("“")
        for part in text.parts:
            if isinstance(part, str):
                self.put(part.replace("\n", indent))
            else:
                self.put("⟨")
                self.lines(part.lines, 0)
                self.put("⟩")
        self.put("”")


def _code(frames: tuple[Frame, ...]) -> bool:
    """Frames hold code: a bar, or a frame with cells. A line without is empty, or a comment of
    its own; an enclosure without holds one empty frame."""
    return len(frames) > 1 or any(frame.cells for frame in frames)
