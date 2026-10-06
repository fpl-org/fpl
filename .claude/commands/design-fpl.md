---
description: Interview the maintainer to fill docs/DESIGN.md (the language vision)
---

Run the FPL vision interview. This is the one process allowed to write `docs/DESIGN.md`.

1. Set `FPL_SPEC_EDIT=1` for this session (the guard-specs hook needs it to let you edit
   `docs/DESIGN.md`). Commits touching it must carry the `[spec]` marker — see `.agents/COMMITS.md`.
2. Read the current `docs/DESIGN.md`. Work section by section (§§1–7).
3. For each section, ask the maintainer **one focused question at a time**. Do not propose
   language features unprompted — draw out *their* vision. Reflect answers back in their words.
4. After each section is answered, write it into `docs/DESIGN.md` and move on.
5. When §§1–6 hold real content, offer to promote the settled semantics into `docs/SPEC.md`.
6. Commit with `scripts/acommit -t docs -s design -m "…" ` and `[spec]` in the body.

Do not touch `bootstrap/` or `features/` here. This command only produces the vision doc.
