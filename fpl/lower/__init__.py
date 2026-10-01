"""The lowering: passes from the walker's core AST into the CBPV IR (design section 6).

Languages are packages (`fpl.cbpv`); a pass is a function between two of them and lives here,
so a module of this package may import both ends: the core AST, the walker's elaboration and
evaluation, and `fpl.cbpv`. It starts from the core AST, as `fpl.eval` and `fpl.types` do, and
imports nothing of the surface: no parser, no desugarer, no driver (law lower-boundary).

`walker` is Σ_walker, the signature whose constants are the walker's own functions, and
readback from IR values to walker values. A pass refuses what it cannot lower by returning a
refusal, never by raising.
"""
