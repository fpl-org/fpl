# Holes

## parser-algorithm
- Depends on it: fpl/parse.py, tests/test_parse.py, tests/test_ambiguity.py
- Default in force: LALR over fpl/grammar.lark with the tab indenter as postlex; the pre-lexer counts strings and block comments; no backtracking
- Closes by: design, by naming the parser the Drafts promise
- Evidence: SHAR gram/test_fpl.py:5-16 and the parser line after islands()

## ambiguity-over-flat
- Depends on it: tests/test_ambiguity.py
- Default in force: the obligation is paid by programs drawn from the grammar with blocks removed (Earley, explicit ambiguity), since an indenter cannot run inside a derivation; the corpus is read by Earley with lexer="basic" and the tab indenter over the whole grammar
- Closes by: an implementer, by drawing programs with indented blocks (a derivation that emits _INDENT and _DEDENT, rendered as tabs)
- Evidence: after 8a753ec no _ambig in 2000 flat draws nor in the 29 pre-lexed examples; before it, 1814 of 2000 draws and 26 of 29 examples (/private/tmp/claude-501/-Users-psj-dev-github-com-psjg-fpl/7c6e7589-3182-49e2-922a-0c6c40c6f1c4/scratchpad/grammar-fix/proof.log)

## string-self-delimits
- Depends on it: fpl/lex.py (_pair), fpl/parse.py (item), tests/test_parse.py
- Default in force: a string's placeholder is its own token, found by its code offset, as every other enclosure self-delimits; a sigil before a string is a word of its own
- Closes by: design, by saying whether $“x” or #“x” carries a prefix
- Evidence: SHAR gram/test_fpl.py:98-103 (shape: kind string when the body starts with ¶); fpl/grammar.lark layer (1) comment

## comments-hide-pairs
- Depends on it: fpl/lex.py (_special, _brackets), tests/test_parse.py
- Default in force: a ; or ⍝ line comment is copied through untouched: quotes and brackets in it are not counted, as the grammar's LCOMMENT swallows them
- Closes by: design, by confirming a line comment is opaque to the pre-lexer
- Evidence: SHAR gram/test_fpl.py:18-38 and :40-67 count inside comments; features/match/examples/04-4-list-patterns.fpl:16

## block-comment-at-line-start
- Depends on it: fpl/lex.py (_pair)
- Default in force: a ⟦ ⟧ comment opening a line leaves the line's tabs and drops the spaces after it; mid-line it becomes one space
- Closes by: design, by saying what indentation a line opened by a block comment has
- Evidence: SHAR gram/test_fpl.py:25-26 strips the leading tabs too

## final-newline
- Depends on it: fpl/lex.py (prelex)
- Default in force: the pre-lexer ends the code with a newline, so a source or island need not end in one
- Closes by: design, or the printer, which normalises
- Evidence: SHAR gram/test_fpl.py islands() appends '\n' to an island; grammar line: frames _NL

## modifier-inside-word
- Depends on it: fpl/lex.py (shape), fpl/parse.py (word)
- Default in force: a modifier anywhere but at the end of a token is refused: "a modifier ends its word: <token>"
- Closes by: design
- Evidence: SHAR gram/test_fpl.py shape() asserts the match

## arrow-spelling
- Depends on it: fpl/lex.py (SHAPE)
- Default in force: the prefix -> (name spelling) is read beside → (glyph), each kept as written
- Closes by: design, with the name-spelling table
- Evidence: SHAR SHAPE has → only; shared decision (f) "->x (→x) is mortal"

## trailing-comment-glued
- Depends on it: fpl/trivia.py
- Default in force: the first run of ; on a line is its comment, also when glued to code (x; note)
- Closes by: design
- Evidence: SHAR gram/test_fpl.py:265 requires whitespace before ;; the grammar's TOKEN excludes ; (x; note)

## empty-node-span
- Depends on it: fpl/parse.py (_Build.at)
- Default in force: a frame that matched no token (one beside a bar, | x) starts where its enclosing node does
- Closes by: the printer's round trip, when it needs a finer position

## nesting-depth
- Depends on it: fpl/parse.py (_Build is recursive)
- Default in force: none; nesting deep enough to exhaust Python's recursion limit raises RecursionError, a traceback
- Closes by: an implementer, by an iterative build or a refusal at the depth limit
- Evidence: fpl/parse.py _Build.item -> subtrees -> frames -> frame

## grammar-departs-from-handoff
- Depends on it: fpl/grammar.lark, every example
- Default in force: the hand-off grammar with frame non-empty: a frame is empty only beside a bar (| x, a | | b), an empty enclosure is frames? absent, a blank or comment line is part of _NL; a comment line neither opens nor closes a block
- Closes by: Caesura (syntax author), confirming or rewriting the rule in the hand-off
- Evidence: 8a753ec fix(grammar): let a frame be empty only beside a bar; /private/tmp/claude-501/-Users-psj-dev-github-com-psjg-fpl/7c6e7589-3182-49e2-922a-0c6c40c6f1c4/scratchpad/grammar-fix/proof.log
