# Passes

GitHub shows this file for the folder. The passes themselves stay `lex.md`, `parse.md`, and the rest. The OKF index is [index.md](index.md).

- [lex](lex.md) and [parse](parse.md) are two Larks. Lex yields tokens. Parse reads them.
- [desugar](desugar.md) is the walker's fuse of resolve, expand, and lower.
- [elaborate](elaborate.md) and [evaluate](evaluate.md) are the rest of the prefix that runs.
- [resolve](resolve.md), [expand](expand.md), [lower](lower.md), [normalize](normalize.md), [optimize](optimize.md), and [codegen](codegen.md) are signatures. They have no Python yet.
