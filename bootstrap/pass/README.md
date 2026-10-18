# Passes

GitHub shows this file for the folder. The passes themselves stay `01-lex.md`, `02-parse.md`, and the rest. The OKF index is [index.md](index.md).

- [lex](01-lex.md) and [parse](02-parse.md) are two Larks. Lex yields tokens. Parse reads them.
- [desugar](05-desugar.md) is the walker's fuse of resolve, expand, and lower.
- [elaborate](06-elaborate.md) and [evaluate](10-evaluate.md) are the rest of the prefix that runs.
- [resolve](03-resolve.md), [expand](04-expand.md), [lower](07-lower.md), [normalize](08-normalize.md), [optimize](09-optimize.md), and [codegen](11-codegen.md) are signatures. They have no Python yet.
