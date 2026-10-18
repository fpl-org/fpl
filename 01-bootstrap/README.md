---
title: 1 Bootstrap
---

# FPL bootstrap, literate trial

GitHub renders this file when you open the folder. A note's name is its address. A concept is `01.02-pass/01.02.01-lex.md`, not another `README.md`.

What GitHub does with this tree:

- A `README.md` is the page of its folder. Every other `.md` renders when you open it, YAML frontmatter included.
- Relative links such as [01.02.01-lex](01.02-pass/01.02.01-lex.md) navigate. `[[wikilinks]]` do not.
- GitHub does not run Astro, Quarto, or Marimo. The fences stay source.
- `index.md` is the OKF root index. GitHub does not treat it as the folder page. This README does that job.

The other tools read the same files:

- Obsidian opens the repo root as the vault. These notes are in that graph. Wikilinks are off.
- OKF concepts are the notes that carry `type`. `index.md` files are indexes and have no `type`. These READMEs have no `type` either.
- Marimo opens a filled note with `marimo edit 01.02-pass/01.02.01-lex.md`.
- Astro builds a static site from the concept notes and skips `README.md` and `index.md`.
- Quarto builds the reactive pages from the gitignored `.qmd` aliases.

## Map

- [01.01 Boundary](01.01-boundary/README.md)
- [01.02 Passes](01.02-pass/README.md)
- [01.03 Representations](01.03-repr/README.md)
- [01.04 Compositions](01.04-compose/README.md)
- [01.05 Lab](01.05-labs/README.md)
- [01.06 Nagini](01.06-nagini/README.md)
- [Site](site/README.md)
