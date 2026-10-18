# FPL bootstrap, literate trial

GitHub renders this file when you open the folder. The notes keep their own names. A concept is `pass/01-lex.md`, not another `README.md`.

What GitHub does with this tree:

- A `README.md` is the page of its folder. Every other `.md` renders when you open it, YAML frontmatter included.
- Relative links such as [lex](pass/01-lex.md) navigate. `[[wikilinks]]` do not.
- GitHub does not run Astro, Quarto, or Marimo. The fences stay source.
- `index.md` is the OKF root index. GitHub does not treat it as the folder page. This README does that job.

The other tools read the same files:

- Obsidian opens the repo root as the vault. These notes are in that graph. Wikilinks are off.
- OKF concepts are the notes that carry `type`. `index.md` files are indexes and have no `type`. These READMEs have no `type` either.
- Marimo opens a filled note with `marimo edit pass/01-lex.md`.
- Astro builds a static site from the concept notes and skips `README.md` and `index.md`.
- Quarto builds the reactive pages from the gitignored `.qmd` aliases.

## Map

- [Passes](pass/README.md)
- [Representations](repr/README.md)
- [Compositions](compose/README.md)
- [Boundary](boundary/README.md)
- [Lab](labs/README.md)
- [Site](site/README.md)
- [Nagini](nagini/README.md)
