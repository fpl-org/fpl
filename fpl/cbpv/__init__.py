"""The object-level CBPV IR: incipit's statement "A: the object-level CBPV IR, K1's core"
(main table rows 81 (4) and 82, the Backend plan tab rev 16, lines 55-91).

Levy's call-by-push-value, simply typed, with the statement's three additions: capability
operations (`op V W`), the effect line (`ε ⊆ {div, fail}`, with `rec` for div and `fail W`),
and cost labels (`label l. M`). Literals are value constants and primitive words are
computation constants (`Prim`) at an instance of their type, which the signature
(`fpl.cbpv.sig`) admits or refuses. Every binder carries a grade.

Modules: `syntax` (the frozen terms and types), `sig` (a signature of constants), `check`
(the typing judgements), `text` (Levy's notation, for review and failure messages).

Left out, each a hole in HOLES.md: `μD`, `con` and `pm V as con x. M` (mu-types, K5); grades
other than 0 are carried, not counted (grades); a thunk's latent effect lives on `U`, which the
statement does not say (thunk-effect); `Dyn`, the walker's untracked sort, is consistent with
base types at application and nowhere else (dynamic-sort). The package imports only the
standard library, `icontract` and itself: it knows nothing of the walker.
"""
