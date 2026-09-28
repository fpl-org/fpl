"""The surface AST as canonical source; the printer is the only normaliser.

Items are joined by a space, cells by a tab, frames by a bar between spaces (an empty frame
beside a bar prints nothing); an enclosure prints as "o body c", or "oc" when empty; a block line
carries one tab per level; no line ends in a space; a program ends in a newline. Comments are
not in the surface AST and are not printed.
"""

from typing import assert_never

from fpl.ast_surface import Cell, Enclosure, Frame, Item, Line, Pair, Program, Text, Word

DELIMITERS: dict[Pair, tuple[str, str]] = {
    "quotation": ("[", "]"),
    "prefix": ("(", ")"),
    "group": ("⟨", "⟩"),
    "dict": ("{", "}"),
}


def render(program: Program) -> str:
    """Canonical source for a program: parse(render(p)) == p for every tree whose cells hold
    items and whose enclosures hold no lone empty frame, and render∘parse is idempotent. The
    empty program is the empty text."""
    out = _Out()
    out.lines(program.lines, 0)
    return "".join(out.chunks) + "\n" if program.lines else ""


class _Out:
    """Source as it is written, with the tabs that open its current physical line: a string's
    continuation lines carry them, since the parser drops them (S26)."""

    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.tabs = 0
        self.leading = True

    def put(self, text: str) -> None:
        """Append text, keeping count of the tabs that open the physical line it ends on."""
        self.chunks.append(text)
        newline = text.rfind("\n")
        if newline >= 0:
            self.tabs, self.leading, text = 0, True, text[newline + 1 :]
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
        """One line and its block, one level deeper."""
        self.put("\t" * depth)
        self.frames(line.frames)
        for inner in line.block:
            self.put("\n")
            self.line(inner, depth + 1)

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
        """o body c, or oc when nothing is inside."""
        opener, closer = DELIMITERS[enclosure.pair]
        if not any(frame.cells for frame in enclosure.frames) and len(enclosure.frames) < 2:
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
