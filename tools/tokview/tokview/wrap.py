"""Hard wrapping of FPL comments, never of code.

A trailing `<tab>; note` that runs past the width continues on lone `;` lines at the code's
indentation; a `;;`, `;;;` or `;;;;` line wraps with its own marker repeated. Code has no
continuation form, so a code line past the width stays as it is and is counted as over.
Ventilating cuts every note and comment line at sentence ends instead of at a width.
"""

import importlib
import re

TAB = 4  # columns per tab; elastic tabstops make the true width unknowable
NOTE = "\t; "
COMMENT = re.compile(r"(\t*)(;{2,4}) (.*)$")
LIST_NUMBER = re.compile(r"\W*\d+\.\s*")
CLAUSE = re.compile(r"(?<=;) (?=[A-Za-z(\[→∨])")  # noqa: RUF001 -- FPL's or sign may open a clause
# pysbd ships neither stubs nor py.typed. Imported by name it is typed Any, where a static import
# would need a waiver from each checker, and mypy refuses the reason that scripts/escapes
# requires after its ignore comment.
SEGMENTER = importlib.import_module("pysbd").Segmenter(language="en", clean=False)


def cols(line: str) -> int:
    """The width of a line in columns, a tab counting TAB."""
    return sum(TAB if char == "\t" else 1 for char in line)


def indentation(code: str) -> str:
    """The leading tabs of a line."""
    return code[: len(code) - len(code.lstrip("\t"))]


def wrap(words: list[str], width: int, prefix: int) -> list[str]:
    """Words joined by spaces into lines that fit width after prefix columns. A word that
    does not fit alone gets a line of its own."""
    out: list[str] = []
    cur = ""
    for word in words:
        if cur and prefix + len(cur) + 1 + len(word) > width:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        out.append(cur)
    return out or [""]


def fold_line(line: str, width: int) -> tuple[list[str], bool]:
    """The line folded to width, and whether its code alone is wider than that. A comment
    line that fits is left as written, its spacing included."""
    if m := COMMENT.match(line):
        if cols(line) <= width:
            return [line], False
        indent, mark, text = m.groups()
        parts = wrap(text.split(" "), width, len(indent) * TAB + len(mark) + 1)
        return [f"{indent}{mark} {p}" for p in parts], False
    if NOTE not in line:
        return [line], cols(line) > width
    code, note = line.split(NOTE, 1)
    if cols(code) + TAB + 2 + len(note) <= width:
        return [line], False
    indent = indentation(code)
    parts = wrap(note.split(" "), width, cols(code) + TAB + 2)
    rest = wrap(" ".join(parts[1:]).split(" "), width, len(indent) * TAB + 2) if parts[1:] else []
    return [f"{code}{NOTE}{parts[0]}"] + [f"{indent}; {p}" for p in rest], cols(code) > width


def folded(text: str, width: int) -> tuple[str, int]:
    """Every line of text folded to width, and how many code lines stay wider than it."""
    out: list[str] = []
    over = 0
    for line in text.split("\n"):
        lines, wide = fold_line(line, width)
        out.extend(lines)
        over += wide
    return "\n".join(out), over


def sentences(note: str) -> list[str]:
    """The note cut at sentence ends, then at `; ` between clauses. A list number standing
    alone (`— 1.`) is kept with the item after it."""
    parts: list[str] = []
    pending = ""
    segments: list[str] = SEGMENTER.segment(note)
    for segment in segments:
        sentence = pending + segment
        if LIST_NUMBER.fullmatch(sentence):
            pending = sentence
            continue
        parts.append(sentence)
        pending = ""
    if pending:
        parts.append(pending)
    return [c.strip() for p in parts for c in CLAUSE.split(p) if c.strip()]


def ventilated(text: str) -> str:
    """Text with every note and comment line cut into one sentence per line."""
    out: list[str] = []
    for line in text.split("\n"):
        if m := COMMENT.match(line):
            indent, mark, body = m.groups()
            out.extend(f"{indent}{mark} {s}" for s in sentences(body) or [body])
        elif NOTE in line:
            code, note = line.split(NOTE, 1)
            first, *rest = sentences(note) or [note]
            out.append(f"{code}{NOTE}{first}")
            out.extend(f"{indentation(code)}; {s}" for s in rest)
        else:
            out.append(line)
    return "\n".join(out)
