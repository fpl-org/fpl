---
description: Interview the maintainer to fill 02-docs/02.01-design.md (the language vision)
---

Run the FPL vision interview. This is the one process allowed to write `02-docs/02.01-design.md`.

1. Set `FPL_SPEC_EDIT=1` for this session (the guard-specs hook needs it to let you edit
   `02-docs/02.01-design.md`). Commits touching it must carry the `[spec]` marker — see `.agents/COMMITS.md`.
2. Read the current `02-docs/02.01-design.md`. Work section by section (§§1–7).
3. For each section, ask the maintainer **one focused question at a time**. Do not propose
   language features unprompted — draw out *their* vision. Reflect answers back in their words.
4. After each section is answered, write it into `02-docs/02.01-design.md` and move on.
5. When §§1–6 hold real content, offer to promote the settled semantics into `02-docs/02.02-spec.md`.
6. Commit with `.harness/scripts/acommit.sh -t docs -s design -m "…" ` and `[spec]` in the body.

Do not touch `01-bootstrap/` or `03-fpl/03.01-features/` here. This command only produces the vision doc.
