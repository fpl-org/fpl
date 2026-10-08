# HOLES.md

Where the documents are silent: what depends on it, the default in force, who closes it and how.
A hole is closed by the commit that removes its entry; that commit's body names it.

    ## <hole-name>
    - Depends on it: <paths, examples, tests>
    - Default in force: <behaviour now; the mechanism it reuses>
    - Closes by: <whom>, <how>
    - Evidence: <file:line | SHAR section | claim id>

## claims-source
- Depends on it: the claims lens, every step-3 implementer, the coverage matrix
- Default in force: the Drafts have no tables; a claim is a Draft 1-4 code line carrying a trailing ; comment (43 claims, ids D<draft>.<n>), its part set by keyword family, else the ;;; section, else 02-stack (3 rows)
- Closes by: PSJ and palimpsest, taking or refusing Caesura's proposal as the candidate close: a claim is a trailing comment that begins '; →', an expected result (10 in the corpus, 11 once Draft 1's '; 0 3 5 6 / …' is respelled); else a claims table
- Evidence: the session's design/INDEX.md (0 table lines in design/draft-1.md to design/draft-4.md); design/claims.jsonl sha256 62c3c94e

## parser-algorithm
- Depends on it: fpl/parse.py, tests/test_parse.py, tests/test_ambiguity.py, every features example
- Default in force: LALR over fpl/grammar.lark with the tab indenter as postlex (linear, no backtracking); the pre-lexer counts strings and block comments; .agents/STACK.md:27 still names Earley
- Closes by: maintainer, a root docs change settling LALR in .agents/STACK.md, or a request for Earley
- Evidence: .agents/STACK.md:27; handoff/SHAR-syntax.org:122 "The grammar"; SHAR gram/test_fpl.py:5-16 and the parser line after islands()

## ambiguity-over-flat
- Depends on it: tests/test_ambiguity.py ("programs derived from the grammar parse without ambiguity"), tests/test_print.py (the flat law)
- Default in force: from_lark draws from the block-free FLAT grammar (declared _INDENT/_DEDENT have no pattern to generate from), parsed by Earley ambiguity='explicit' lexer='basic'; the corpus is read by Earley with the tab indenter over the whole grammar; blocks are covered by the corpus and the printer's tree strategy only
- Closes by: implementer, a generator emitting indented blocks (a derivation that emits _INDENT and _DEDENT, rendered as tabs); or maintainer accepts
- Evidence: handoff/SHAR-syntax.org:486 printer.py docstring, its FLAT replace() for _NL and LCOMMENT match nothing in fpl.lark; after 8a753ec no _ambig in 2000 flat draws nor in the 29 pre-lexed examples, before it 1814 of 2000 and 26 of 29 (8a753ec's body)

## grammar-departs-from-handoff
- Depends on it: fpl/grammar.lark, every example
- Default in force: PSJ's decisions of 2026-09-29: the hand-off's one frame rule (frames: frame (_BAR frame)*, a frame may be empty) for lines and enclosures; an enclosure takes frames without ?, so [] ⟨⟩ () {} are one empty frame (bars + 1 frames, the base case, distinct from [ | ]); start: line* without _NL*, so an empty line is only the first line of a file that opens blank; comments are NOTE and DOC tokens on their line (line: frames (NOTE | DOC)? _NL block?), no longer ignored, and _NL is the hand-off's blank run again, whose lines but the last may hold tabs, spaces and form feeds (form-feed-line)
- Closes by: Caesura (syntax author), folding these decisions into the hand-off's grammar and its prose
- Evidence: 61399de fix(grammar): keep comments as tokens and read [] as one empty frame; session grammar-fix/proof2.log (LALR no conflicts, 29/29 examples, Earley _ambig 0/29 and 0/2000 flat draws); earlier 8a753ec; proof3.log after bd41245, the same counts

## grammar-comment-word
- Depends on it: fpl/grammar.lark:15
- Default in force: the grammar is kept to the hand-off's wording, including one filler word ('simply') in a comment
- Closes by: Caesura, rewording in the hand-off; the grammar follows
- Evidence: fpl/grammar.lark:15; handoff/SHAR-syntax.org:122 "The grammar"

## string-self-delimits
- Depends on it: fpl/lex.py (_pair), fpl/parse.py (item), tests/test_parse.py
- Default in force: a string's placeholder is its own token, found by its code offset, as every other enclosure self-delimits; a sigil before a string is a word of its own
- Closes by: design, by saying whether $“x” or #“x” carries a prefix
- Evidence: SHAR gram/test_fpl.py:98-103 (shape: kind string when the body starts with ¶); fpl/grammar.lark layer (1) comment

## comments-hide-pairs
- Depends on it: fpl/lex.py (_special, _brackets), tests/test_parse.py
- Default in force: a ; or ⍝ line comment is copied through untouched: quotes and brackets in it are not counted, as the grammar's LCOMMENT swallows them
- Closes by: design, by confirming a line comment is opaque to the pre-lexer
- Evidence: SHAR gram/test_fpl.py:18-38 and :40-67 count inside comments; fpl/features/match/examples/04-4-list-patterns.fpl:16

## block-comment-at-line-start
- Depends on it: fpl/lex.py (_pair)
- Default in force: a ⟦ ⟧ comment opening a line leaves the line's tabs and drops the spaces after it; mid-line it becomes one space
- Closes by: design, by saying what indentation a line opened by a block comment has
- Evidence: SHAR gram/test_fpl.py:25-26 strips the leading tabs too

## final-newline
- Depends on it: fpl/lex.py (prelex), fpl/print.py
- Default in force: the pre-lexer ends the code with a newline, so a source or island need not end in one; the printer always writes one
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
- Depends on it: fpl/grammar.lark (TOKEN, NOTE), fpl/parse.py (_Build.comment), fpl/print.py (comment)
- Default in force: ; self-delimits, as the grammar's TOKEN excludes it, so x; note is the word x and a note on its line, also when glued; the printer sets the note apart in a cell of its own (x\t; note)
- Closes by: design, confirming that ; needs no whitespace before it
- Evidence: SHAR gram/test_fpl.py:265 requires whitespace before ;; fpl/grammar.lark TOKEN (x; note)

## empty-node-span
- Depends on it: fpl/parse.py (_Build.at)
- Default in force: a frame that matched no token (one beside a bar, | x, or the one frame of an empty enclosure, []) starts where its enclosing node does; an empty first line starts at the newline that ends it
- Closes by: the printer's round trip, when it needs a finer position
- Evidence: fpl/parse.py _Build.at (tree.meta.empty); Span is field(compare=False) in fpl/ast_surface.py, so the round trip does not see it

## nesting-depth
- Depends on it: fpl/parse.py (parse, _Build is recursive), tests/test_parse.py::test_nesting_too_deep_to_read_is_refused
- Default in force: nesting that exhausts Python's recursion limit (about 100 brackets or ⟨ ⟩ islands, a few hundred block levels) is one error, ERROR: 1:1 nesting too deep to read; it reuses the FplError every refusal is
- Closes by: an implementer, by an iterative build that reads any depth, or design, by naming a depth limit and where it is reported
- Evidence: fpl/parse.py _Build.item -> subtrees -> frames -> frame; RecursionError at 100 nested [ and at 400 block levels before the refusal

## stray-closer-refused
- Depends on it: fpl/lex.py (_special, _brackets), tests/test_parse.py::test_a_refusal_is_one_error_line
- Default in force: a closer with no opener (] ” 」 ⟧) or one that does not close the latest opener is refused where it stands, as an unclosed opener is; SHAR passes a stray bracket closer to Lark and a stray pair closer through as text
- Closes by: design, by confirming that every closer must balance
- Evidence: SHAR gram/test_fpl.py:34 (elif ch in CLOSE and stack: stack.pop()), :45-46 (only openers are special)

## snippet-split
- Depends on it: fpl/features/{draft1,draft2,draft3,server,sketch,match}/examples/*.fpl; tests/test_conformance.py::test_example[*]; tests/test_ambiguity.py::test_no_ambiguity_in_the_corpus[*]
- Default in force: one .fpl per snippet set, cut at ;;; lines where the section parses alone, else joined to the part before (draft1, draft3 and server stay whole; draft2 is split 11 ways, sketch 7, match 7); the parts are byte copies of the tangled hand-off and concatenate to the snippet byte for byte
- Closes by: maintainer or design side, re-cutting the fixtures or confirming the rule
- Evidence: decision (b); the fixture commits 42a7b7c, f30b1ef, e04a708, b75ee2f, 4b8213b, 3302d19, each section parsing alone; handoff/SHAR-syntax.org:828 "The snippet corpus"

## program-output
- Depends on it: fpl/driver.py, fpl/desugar.py listing, tests/test_desugar.py, every .expected that is not an error line
- Default in force: each top-level line that is not a definition runs on a fresh stack and prints one line, the stack it leaves as fpl/print.py writes the items that push it, with a bar between two literals that would otherwise strand; a definition prints nothing; a program with no line to run prints nothing. A section prints in the printer's spelling, [ 1 2 3 + ] for the Draft's [1‿2‿3 +]
- Closes by: design side, a Draft statement of what a program prints
- Evidence: decision (d); draft2 §frames, fpl/features/draft2/examples/01-frames.fpl:2-4 (one result per line; line 3 has nothing below after line 2 left 2 3 4); claims D2.1-D2.3

## expected-evolution
- Depends on it: every fpl/features/*/examples/*.expected (28, _template aside); tests/test_conformance.py::test_example[*]; tests/test_main.py::test_a_file_that_cannot_run_prints_one_error_line
- Default in force: every .expected starts as the one line ERROR: 1:1 no evaluator yet; a step-3 PR replaces one in its own [spec] commit with a value transcribed from the example's trailing ; comments or a Draft claim, source lines named, never from the implementation's output; the maintainer did not write these values
- Closes by: maintainer, reviewing each [spec] commit; each step-3 PR closes it per example
- Evidence: decisions (b) and (c); AGENTS.md "The oracle rule"; fpl/features/*/examples/*.expected at 3302d197

## unimplemented-words
- Depends on it: fpl/desugar.py unimplemented; the 23 of 28 examples still at ERROR: 1:1 no evaluator yet, each named with the first thing desugar refuses: fpl/features/draft1/examples/draft1.fpl (newline), fpl/features/draft2/examples/03-operatives-thunks.fpl (debug), fpl/features/draft2/examples/04-effects-holes-ascription.fpl (shape), fpl/features/draft2/examples/05-the-dictionary-is.fpl (words), fpl/features/draft2/examples/06-constructors-run-backwards.fpl (unpair), fpl/features/draft2/examples/08-objects-are-directories.fpl (dict), fpl/features/draft2/examples/10-quasiquote-inside.fpl ($q, an unquote), fpl/features/draft2/examples/11-laziness.fpl (curry), fpl/features/draft3/examples/paths.fpl (shape), fpl/features/match/examples/01-1-constructors-run.fpl (pos), fpl/features/match/examples/02-2-the-same.fpl (a pattern on the effect line), fpl/features/match/examples/03-3-multiple-dispatch.fpl (Asteroid), fpl/features/match/examples/04-4-list-patterns.fpl (false), fpl/features/match/examples/05-5-prolog-s-family.fpl (x in mother's body), fpl/features/match/examples/06-6-python-s-keywords.fpl (a record pattern on the effect line), fpl/features/server/examples/server.fpl (+in/data on the effect line), fpl/features/sketch/examples/05-5-multiple-dispatch.fpl (shape/r), and fpl/features/sketch/examples/01, 02, 03, 04, 06 and 07 (seam ∈ … in a directory, no definition nor bind)
- Default in force: desugar refuses, before anything runs, all but: decimal numbers, strings without islands, [ ], ( ) of one cell, ⟨ ⟩ of literals, bars, tabs, blocks, name : ins -- outs definitions (each slot a name or name: Type), →x and ->x of a plain name or a path, #name symbols, { } of plain keys each with one item pushing one value, name/ heads with a block of definitions, subdirectories and #name bind lines, paths a/b and ../x that name a defined word, w/history, w/doc, w/effect, a match line with its block of rows in a definition's body, clauses of one word whose typed inputs cross only where their meet is a clause or two builtin type words make them disjoint, and the words of fpl/ast_core.py EFFECTS (+ - times swap dup drop enclose , pair cons ! if swap-args repeat each scan fold, and ? and _ in a term), with ERROR: 1:1 no evaluator yet (the skeleton's message and position, reused)
- Closes by: each step-3 part, shrinking the set
- Evidence: fpl/driver.py (skeleton); fpl/ast_core.py EFFECTS; each example run through fpl.driver.run at 203e0ba, the refusal traced to its caller in fpl/desugar.py (resolve, origin, effect_line, mount)

## doc-absent
- Depends on it: fpl/desugar.py (Catalog.enter, DOC), fpl/eval.py (evaluate), tests/test_comments.py, fpl/features/draft3/examples/paths.fpl:10
- Default in force: every word w has w/doc, as it has w/history; the doc goes with the definition in force (Define.doc), so a word with no doc, or shadowed by a definition with none, pushes the empty string
- Closes by: design, saying what an undocumented word's doc is (a refusal, the empty string, or no such word)
- Evidence: claim D3.2 (draft-3.md:13); paths.fpl:10 asks math/mean/doc of a mean with no ;; line

## doc-text
- Depends on it: fpl/trivia.py (docstrings, _aimed), tests/test_trivia.py, tests/test_comments.py
- Default in force: a ;; is a doc when the next code line is a head (winning over a body it opens), or when it opens a head's body before any of its code, as SHAR comments() reads it; else it is before the next code line; a head is a line whose first cell's second item is the plain word :; a docstring is each doc's text, marks and the whitespace around it dropped, those above the head first, joined by newlines; ;;; and ;;;; stay bound to their level wherever they stand (hole comment-levels), where the SHAR reads them at column 0 only
- Closes by: design, fixing a docstring's text and whether both places may hold one
- Evidence: SHAR gram/test_fpl.py:255-281; fpl/features/draft2/examples/04-effects-holes-ascription.fpl:3

## fresh-unify-space
- Depends on it: fpl/features/match (Prolog's family), fpl/features/sketch (logic tree)
- Default in force: not implemented; a program using fresh, unify or space reports ERROR: 1:1 no evaluator yet
- Closes by: maintainer, scheduling two-way unification
- Evidence: campaign scope, step 3

## goal-placeholder
- Depends on it: fpl/types.py filled, wanted, reported; fpl/driver.py run; fpl/__main__.py; fpl/eval.py unfilled; tests/test_types.py test_a_goal_is_reported_with_the_effect_that_fills_it, test_a_goal_run_is_refused_where_it_stands; tests/test_main.py test_a_goal_goes_to_stderr_before_the_program_runs; tests/test_match.py test_a_wildcard_row_whose_body_is_a_goal_is_reported
- Default in force: ? is a word of no fixed effect (a Call, no core node; desugar balances it as taking and leaving nothing); elaboration reports it as data, GOAL <line>:<col> ? : <ins> -- <outs>, the driver handing each line to a reporter the command line points at stderr, before any line runs; the goal takes the whole stack under it and leaves what the code after it takes, or, when nothing follows, what the effect line promises (none on a top-level line); an input of the body prints as t and its index, a sort as its name; elaboration goes on with values of no known sort; running it is ERROR: <line>:<col> unfilled goal; a goal under a control word, in a quotation or a { } value, or in a body a control word leaves untyped is not reported
- Closes by: design side, the report's form and destination and a goal's extent (the whole stack, or what it is ascribed)
- Evidence: handoff/SHAR-syntax.org:906 and :1016 (S40); claims D2.7 (fpl/features/draft2/examples/04-effects-holes-ascription.fpl:5, grade and pick not builtins, so it cannot evaluate yet) and D4.3, fpl/features/match/examples/01-1-constructors-run.fpl:15

## print-obligation-unlisted
- Depends on it: tests/test_print.py, scripts/props
- Default in force: the tree law is marked @pytest.mark.obligation("print then parse is the identity"), but quality/obligations.toml lists no printer obligation, so scripts/props does not enforce it
- Closes by: a root [policy] commit adding [fpl.print] to quality/obligations.toml
- Evidence: quality/obligations.toml ("Owed once there is a printer")

## eval-obligation-unlisted
- Depends on it: tests/test_match.py test_the_row_chosen_is_the_first_whose_patterns_match and test_a_match_is_exhaustive_exactly_when_its_effect_has_no_fail, scripts/props
- Default in force: the two properties are marked @pytest.mark.obligation("the row chosen is the first whose patterns match") and @pytest.mark.obligation("a match is exhaustive exactly when its effect has no +fail"), and the file imports fpl.eval and fpl.desugar so scripts/props credits both; quality/obligations.toml lists neither, so scripts/props does not enforce them (as print-obligation-unlisted)
- Closes by: a root [policy] commit adding the first to [fpl.eval] (matching) and the second to [fpl.desugar] (fallible, catches) in quality/obligations.toml
- Evidence: quality/obligations.toml (no [fpl.eval] table; [fpl.desugar] lists one obligation); campaign scope 06-match ("Property: the row chosen is the first whose patterns match. Property: exhaustive ⇔ no +fail.")





## fon-unwritable
- Depends on it: fpl/fon.py (write, embed), tests/test_fon.py::test_json_embeds_and_reads_back
- Default in force: a text holding an unbalanced “ or 「, or a symbol that spells another kind (1, #a, true), has no FON spelling; write gives the text as is and read refuses it or reads another value; the JSON property draws texts without “ and ”; a JSON key that is not a plain symbol is kept as text
- Closes by: design, an escape in strings or a statement that such values are outside the profile
- Evidence: handoff/SHAR-syntax.org:621 "FON-data" (no escape; its strategy filters balanced quotes)

## comment-levels
- Depends on it: fpl/grammar.lark (NOTE, DOC), fpl/parse.py (_Build.comment), fpl/print.py (comment), fpl/trivia.py
- Default in force: PSJ's decisions of 2026-09-29: the level is bound to position, as in Lisp. ; (and ⍝, which counts as ;) is a note after the code of its line, continued by the ; lines right under it, one token with them; a blank line ends a note; ;; ;;; ;;;; stand on a line of their own: ;; the doc of the next code line, ;;; a section, ;;;; the file; ;; or deeper after code is refused at the comment
- Closes by: Caesura, folding the rule into the hand-off's grammar prose
- Evidence: session grammar-fix/proof2.log; tests/test_parse.py::test_a_comment_is_held_by_its_line, tests/test_trivia.py

## comment-levels-vs-corpus
- Depends on it: fpl/parse.py (_Build.comment), fpl/features/match/examples
- Default in force: a ; with no code before it that continues no note is kept as a note line (one empty frame and its note), not refused as the rule says, because the corpus has four: fpl/features/match/examples/04-4-list-patterns.fpl:15-16, 07-7-abc-s-keywords.fpl:2-3; no ;; is after code
- Closes by: PSJ or Caesura rewriting those lines (as ;; or as notes after code); then the builder refuses the standalone ;
- Evidence: session grammar-fix/measure.log, proof2.log

## note-alignment
- Depends on it: fpl/parse.py (_Build.comment), fpl/print.py (_Out.column, comment)
- Default in force: PSJ's decision of 2026-09-29: a continuation line of a note carries as many tabs before its ; as the code line has before its own ; (elastic tabstops), and a continued note stands in its own cell; the printer sets every note in its own cell and aligns its continuations; the builder does not refuse a misaligned continuation, since the corpus has two: fpl/features/match/examples/03-3-multiple-dispatch.fpl:8 (1 tab, note at 5), 06-6-python-s-keywords.fpl:6 (0 tabs, note at 1)
- Closes by: Caesura folding the rule into the hand-off; PSJ or Caesura realigning those lines; then the builder refuses with "a continued note aligns with the note above: N tabs"
- Evidence: session grammar-fix/proof2.log (note alignment section)

## comment-heads-block
- Depends on it: fpl/grammar.lark (line), fpl/desugar.py (coded)
- Default in force: a comment line may head an indented block (an outline heading); no example has one; desugar refuses such a line as unimplemented (no evaluator yet), since running its block as quotations or as lines is undecided; a comment line with no block is no statement
- Closes by: Caesura, confirming or refusing it
- Evidence: session grammar-fix/proof2.log (";;; s\n\ta" parses once, 0 heads in the corpus)

## comment-in-enclosure
- Depends on it: fpl/parse.py (_tree)
- Default in force: a comment inside a multi-line enclosure is refused, ERROR: a comment cannot stand inside an enclosure; no example has one
- Closes by: Caesura, giving comments a place inside enclosures if one is wanted
- Evidence: session grammar-fix/proof2.log (0 comments inside an enclosure in the corpus); tests/test_parse.py::test_a_refusal_is_one_error_line

## empty-first-line
- Depends on it: fpl/grammar.lark (start), fpl/print.py (render), fpl/desugar.py (coded)
- Default in force: a file that opens with blank lines has one empty first line, and "\n\tx" gives that line a block; a blank source ("", "\n") is that one line and prints as the empty text; no example opens blank (PSJ: leading blank lines are not useful, a refusal is acceptable)
- Closes by: PSJ or Caesura, keeping it or refusing a blank first line; until then desugar runs nothing for it, and refuses it as unimplemented when it heads a block
- Evidence: session grammar-fix/proof2.log; tests/test_parse.py::test_only_the_first_line_is_empty_and_it_may_hold_a_block

## form-feed-line
- Depends on it: fpl/grammar.lark (_NL), tests/test_print.py::test_a_blank_line_is_part_of_its_blank_run_whatever_it_holds
- Default in force: a form feed is the page separator, ignored like a space; a line holding only tabs, spaces and form feeds inside a blank run is part of the run, so it leaves no line and prints as nothing; only the last line's tabs are indentation, so a form feed before a line's tabs leaves it at depth 0 as before
- Closes by: Caesura or PSJ, confirming the form feed as a page separator, or refusing it outside strings and comments
- Evidence: bd41245 fix(grammar): read a line of form feeds as part of its blank run; session grammar-fix/proof3.log, ffcheck.log

## saturation-balance
- Depends on it: fpl/desugar.py _Desugar.body, tests/test_desugar.py (D2.1-D2.3, D2.5, D2.6, D1.5)
- Default in force: arity is balanced statically in desugar: a top-level line starts at 0; the bar carries the balance on; a : body starts at the effect line's inputs and runs on from line to line (one stack); a block's children come before their head, each saturated as a frame is (a value child adds what its code leaves, a quotation child one); quotation bodies are code and never checked; a frame whose words reach below its starting balance is a section, the whole frame pushed as one quotation, never an error
- Closes by: design side, a Draft rule for where a section starts (the whole frame, or from the word that underflows) and for body lines
- Evidence: decision (f); claims D2.1-D2.3 (draft2 §frames), D2.5 (curry's body underflows its frame but not its effect line)

## effect-line-trusted
- Depends on it: fpl/types.py inferred, declared, agreed; fpl/desugar.py arity; fpl/eval.py builtin; tests/test_binders.py and tests/test_desugar.py reaching a runtime underflow through [ ] !; tests/test_types.py test_match_rows_leaving_different_counts_keep_the_effect_line
- Default in force: a body is inferred and its count checked against its effect line at the definition (fpl/types.py), a match's rows each typed, their pattern names of no known sort; a body with a control word (! if swap-args repeat each scan fold), or a match whose rows leave different counts, is not inferred and its effect line is trusted, a shortfall refused later at the word that finds too few
- Closes by: fpl/types.py, once control words take their quotation's arrow (hole control-effects); design, whether rows leaving different counts are an error
- Evidence: fpl/types.py; tests/test_types.py test_a_body_is_checked_against_its_effect_line

## definition-scope
- Depends on it: fpl/desugar.py desugar, fpl/eval.py evaluate, tests/test_desugar.py test_lcurry_puts_a_swap_between
- Default in force: definitions are global to the program; a word may be used above its definition; a later definition of a name shadows an earlier one for every line, builtins included
- Closes by: design side, with bind's ordered log (decision f) once 03-binders lands
- Evidence: fpl/features/draft2/examples/02-currying.fpl:4-5 (lcurry uses curry); decision (f) "later shadows earlier"

## pervasive-arithmetic
- Depends on it: fpl/eval.py arithmetic, tests/test_desugar.py
- Default in force: + - times take numbers or strands of numbers; a number meets each item of a strand, two strands meet item by item; unequal lengths and non-numbers are refused at the word
- Closes by: design side, the arithmetic of the array model
- Evidence: claim D2.1 (1 | 1 2 3 + gives 2 3 4)

## list-elements
- Depends on it: fpl/desugar.py enclosure, element
- Default in force: ⟨ ⟩ holds literals only (numbers, strings, quotations, lists), each item one element, nothing strands inside; , joins two lists
- Closes by: design side, what a ⟨ ⟩ body may compute
- Evidence: fpl/features/draft2/examples/08-objects-are-directories.fpl:7 (⟨⟩ as an empty accumulator)

## number-glyphs
- Depends on it: fpl/desugar.py atom
- Default in force: ∞ and π, which the affix pass reads as numbers, are refused as unimplemented; numbers are integers and decimals, a decimal kept exact as written
- Closes by: implementer, once an example that uses them evaluates
- Evidence: fpl/lex.py NUMBER; fpl/features/draft1/examples/draft1.fpl:29-32

## effect-query
- Depends on it: claim D3.4
- Default in force: each effect line is kept as declared data (fpl/ast_core.py Effect, on Define; EFFECTS for builtins); w/effect pushes a defined word's effect as a list of strings, ins, "--", outs, then "+fail" when a match in its body is partial (tests/test_match.py); the query words/*/effect is not implemented
- Closes by: the part that implements directories and paths
- Evidence: claim D3.4 (fpl/features/draft3/examples/paths.fpl)

## stack-claims-deferred
- Depends on it: claims D1.6, D1.9, D1.10, D2.8, D2.10, D2.14, D2.15, D2.16 (part 02-stack)
- Default in force: open, their examples at no evaluator yet (D2.9 is paid by fpl/features/draft2/examples/07-scope-follows-the.expected, 2 4 6): D2.8 and D2.10 symbols, pair, dict, method, inverse; D2.14 and D2.15 unquote; D2.16 laziness; D1.6 apply, whose two-child if is refused (hole if-valence); D1.9 and D1.10 ∞, inner, log, repeat and a block of literals under a head that is not a definition
- Closes by: the parts that implement those words, each with a test named by its claim id
- Evidence: design/claims.jsonl rows with part 02-stack

## child-slots
- Depends on it: fpl/desugar.py _Desugar.children, child; tests/test_desugar.py test_a_child_under_a_thunk_or_code_slot_is_pushed_as_a_quotation
- Default in force: a child past the inputs of its head phrase fills no slot, so its slot is unknown: it is pushed as a quotation, as every child was before slots; a value child whose code reaches below its balance is a section, pushed whole (decision f)
- Closes by: design side, saying what a child past the head's inputs is (an error, or a quotation)
- Evidence: design doc FON tab S49 rule 5 ("a child is never run by its position, only by its head"); S42 (children push, head consumes)

## multi-word-head
- Depends on it: fpl/desugar.py _Desugar.inputs; tests/test_desugar.py test_a_child_under_a_value_slot_runs_at_once (+ dup times)
- Default in force: the children fill the inputs of the head phrase as a whole, all its frames joined, the first child the deepest input and the last the top; a word's inputs that the code before it does not supply lie under those already taken; with fewer children than inputs they fill the top ones and the rest come from the stack below
- Closes by: design side (question to Caesura: which slot a child fills under a head of several words, `+ sqrt`)
- Evidence: design doc FON tab S42 (hypot : a b -- c over + sqrt, two children); S49 rule 5 ("top to bottom")

## quotation-slot-words
- Depends on it: fpl/ast_core.py EFFECTS; tests/test_desugar.py test_join_takes_code_and_enclose_a_value, test_a_block_is_one_node_per_head (D1.4), test_children_are_quotations_before_the_head (D1.5)
- Default in force: , takes two code slots (it joins quotations as data, never runs them); enclose takes a value; curry and lcurry, defined in fpl/features/draft2/examples/02-currying.fpl with bare names, take values
- Closes by: design side (question to Caesura: are , enclose and curry code, thunk or polymorphic; , also joins lists, and curry takes a thunk in 11-laziness.fpl:3)
- Evidence: fpl/features/draft2/examples/02-currying.fpl:2-5; fpl/features/draft2/examples/11-laziness.fpl:3; claims D1.4, D1.5

## bare-slot-names
- Depends on it: fpl/desugar.py typed; every effect line in fpl/features/ and tests/
- Default in force: a bare name on an effect line stays legal, an untyped value slot; only `name: Type` declares a thunk or code slot
- Closes by: design side (question to Caesura: do bare names stay, and do the old bracket slots `or : [ p ] [ q ]` survive)
- Evidence: design doc FON tab S49 item 1; fpl/features/sketch/examples/01-1-a-logic.fpl:12-13

## thunk-type-dropped
- Depends on it: fpl/desugar.py slot, declaration; tests/test_desugar.py test_core_without_sugar_writes_back_as_its_source
- Default in force: the core keeps each input's slot, not its type: `x: Int` is written back as `x`, `t: [ -- x ]` as `t: []`, `c: Code` as itself; an output's type is read past
- Closes by: fpl/types.py (types part), keeping the declared types it checks
- Evidence: design doc FON tab S49 item 1 (`f : x: Int  y: Int -- z: Int`)

## double-use-refusal
- Depends on it: fpl/features/server/examples/server.fpl:21 (a ;; comment, not run)
- Default in force: not refused in this part: a quotation both forced and inspected needs a kind on each stack cell through dup, which desugar does not track
- Closes by: fpl/types.py (#59, types), carrying thunk and code kinds through the stack and refusing the double use
- Evidence: fpl/features/server/examples/server.fpl:19-21; design doc FON tab S49 rule 5

## number-bound
- Depends on it: fpl/ast_core.py DIGITS, fpl/desugar.py number, fpl/eval.py arithmetic, tests/test_desugar.py::test_a_numeral_longer_than_digits_is_refused_at_its_position, ::test_a_result_of_more_than_digits_digits_is_refused_at_the_word
- Default in force: a numeral has at most 4096 digits, its sign and point not counted, the number FON's reader bounds a token by (fon.read max_token); a longer one is ERROR: <line>:<col> number too long at the numeral. 4096 is under Python's 4300-digit int/str conversion limit, so the bound is the language's, not the interpreter's setting. A result of + - times of magnitude 10^4096 or more is ERROR: <line>:<col> number too large at the word, so an integer has at most 4096 digits, written or computed, and a decimal never overflows its context; a computed decimal keeps the context's 28 significant digits and its fraction is not bounded
- Closes by: design, naming the bound on a number, written and computed (or none, with a reader and printer that never meet the limit)
- Evidence: a 4301-digit numeral raised ValueError from int() in fpl/desugar.py number before this entry, a traceback past the FplError boundary of fpl/__main__.py, as 10 squared 13 times did from str() in fpl/desugar.py shown and 9.9 squared 22 times did as decimal.Overflow in fpl/eval.py; .agents/CONVENTIONS.md "no Python traceback ever reaches the user"

## binder-scope
- Depends on it: fpl/desugar.py (body, quote, scoped), fpl/eval.py (substitute), tests/test_binders.py
- Default in force: →x names the top for the rest of the sequence it is written in: a definition's body across its lines and the blocks under them, one top-level line, one child line under a thunk or code slot, one quotation or section; a child under a value slot runs in place, so its binder lives on in the sequence the child runs in, like a frame's (hole child-slots); eval substitutes the value for the name there (lexical, a nested binder of the name shadows, nothing mutates); past it the name is no word; the printer writes → for both spellings
- Closes by: design, by saying where a binder's scope ends at top level and in a child line
- Evidence: decision (f); fpl/features/server/examples/server.fpl:3-4 (p bound on one body line, read on the next); fpl/features/draft2/examples/07-scope-follows-the.fpl:3-5; fpl/features/draft2/examples/08-objects-are-directories.fpl:6-10 rebinds acc and s in a repeat child and reads acc after it, which shadowing cannot give

## dict-values
- Depends on it: fpl/desugar.py (dict), fpl/eval.py (gathered), tests/test_binders.py
- Default in force: { } pairs a plain name key with the next item, which must push exactly one value (a literal, symbol, list, quotation, dict, bound name or a word taking none); each value runs on a fresh stack when the dict is reached; ( ) as a value, a strand, an odd count and a path key are refused as unimplemented; a repeated key is refused where it repeats with fpl/fon.py's message; symbols do not strand
- Closes by: design, by saying what a dict value may be and where one ends
- Evidence: fpl/features/match/examples/06-6-python-s-keywords.fpl:2-5; fpl/fon.py dict; fpl/features/draft2/examples/08-objects-are-directories.fpl:3 (#x #y swap)

## require-ensure-rescue
- Depends on it: nothing yet
- Default in force: no example uses require, ensure or rescue; they are unknown words, refused as unimplemented
- Closes by: design, with an example of f/require
- Evidence: grep -l over fpl/features/*/examples/*.fpl finds none; decision (f)

## directory-log
- Depends on it: fpl/desugar.py (Catalog, directory, mount, _Desugar.call, origin), tests/test_binders.py; fpl/features/draft3/examples/paths.fpl:1-9, fpl/features/match/examples/05-5-prolog-s-family.fpl:2, fpl/features/server/examples/server.fpl:4
- Default in force: a head name/ with a block is a directory; its definitions, subdirectories and #name bind mounts form one ordered log, read whole before any line runs (the rule top-level definitions already follow), where the latest entry holding a name wins; a word is a directory holding its history; a name resolves at desugar time from the word's own directory outward, ../x from the directory holding the word; a mount sees only the words its directory defines, never its mounts; a second head of the same name appends to the same log; a name/ head without a block, a deeper a/b/ head, any other line in a directory, bind of anything but a literal #name, a #name that is no directory and ../x on a top-level line are refused as unimplemented
- Closes by: design, by saying whether a log entry is visible above the line that adds it, whether mounts chain, and what a directory holds besides definitions and binds
- Evidence: claims D3.1 (paths.fpl:7 "ordered log append (§5.2): later shadows earlier"), D3.5 (paths.fpl:13 "takes ../io lexically"); decision (f) f/require; fpl/features/sketch/examples/07-7-facts-signed.fpl:18 binds a quotation of paths, which this default refuses

## history-shape
- Depends on it: fpl/eval.py (evaluate), fpl/desugar.py (HISTORY), tests/test_binders.py; fpl/features/draft3/examples/paths.fpl:11
- Default in force: w/history pushes a ⟨ ⟩ list of the definitions of w that a later one shadows, oldest first, each its body as a quotation; the one in force is not in it; one definition gives ⟨⟩
- Closes by: design, by saying what a history entry is (body, effect, source) and whether the one in force belongs to it
- Evidence: claim D3.3 (paths.fpl:11 "shadowed definitions")

## effect-sugar-io
- Depends on it: fpl/features/draft3/examples/paths.fpl:13, fpl/features/server/examples/server.fpl:2 and 10
- Default in force: only the lexical half of D3.5 is in force (../x resolves from the directory holding the word); an effect line naming +io or any +effect is refused as unimplemented, so nothing threads an effect linearly
- Closes by: the effects part, with the design saying what +io desugars to
- Evidence: claim D3.5 (paths.fpl:13 "sugar: takes ../io lexically, threads it linearly (§4.3 answer)")

## with-record-union
- Depends on it: fpl/features/match/examples/06-6-python-s-keywords.fpl:5
- Default in force: with is no word and is refused as unimplemented; it needs record patterns in a head (06-6-python-s-keywords.fpl:2), which no part implements yet
- Closes by: implementer of 06-match, after record-pattern heads
- Evidence: claim D4.12 ("with: curry-with-union; later calls still override")

## qualified-resugar
- Depends on it: fpl/desugar.py (resugar, named, written), tests/test_print.py
- Default in force: resugar writes a definition inside a directory as a top-level path head (m/sq : x -- y), which does not parse back to the same statement; the printer's round trip holds only for programs without directories, the only ones its strategies generate
- Closes by: implementer, by resugaring the log as nested name/ heads when a property needs it
- Evidence: fpl/desugar.py written

## control-effects
- Depends on it: fpl/ast_core.py EFFECTS, fpl/desugar.py balance, tests/test_control.py
- Default in force: each control word declares one fixed effect for saturation, whatever its quotation does: ! q -- x, if c t e --, swap-args x y q -- z, repeat q n --, each and scan xs q -- ys, fold xs q -- x; a quotation that does otherwise shows at run time as an underflow or as values left over (1 [+] ! is ERROR: 1:4 stack underflow); a frame in which the control word itself finds too few is a section, as saturation-balance says (1 [2] [3] if 1 + prints [ 1 [ 2 ] [ 3 ] if 1 + ]); the mechanism is the builtin effect table
- Closes by: the types part, inferring a quotation's effect and checking the word against it
- Evidence: combined-draft.md:134 (if : c t e --, fixed valence); claims D2.4, D2.13; no document gives the outputs of !

## truth-values
- Depends on it: fpl/eval.py choose, tests/test_control.py
- Default in force: if takes the integer 0 or 1 and refuses anything else with "if takes 0 or 1"; the 0/1 of the array model's comparisons, reused
- Closes by: design side, naming the truth values
- Evidence: combined-draft.md:134; draft-2.md:17-18 (my-if forces c before if)

## if-valence
- Depends on it: fpl/features/draft1/examples/draft1.fpl:16-18 (apply), tests/test_control.py
- Default in force: if : c t e -- with c a value; a block under if gives t and e, children first, so the form works where c is already below, as in a body; draft1's two-child apply, a condition quotation and one branch, meets a non-0/1 condition and is refused; there is no when
- Closes by: syntax author, rewriting draft1's apply with when : c t -- as combined-draft row 14 says
- Evidence: combined-draft.md:134; draft-1.md:20-22

## step-stack
- Depends on it: fpl/eval.py single, each, scan, fold; fpl/features/draft2/examples/07-scope-follows-the, 09-rotates
- Default in force: each runs its quotation on a fresh stack holding one item, scan and fold on one holding the result so far and the next item; a step leaves one value or is refused with "each step leaves one value"; the first item starts scan and fold, and fold over nothing is refused (ERROR at fold, "fold over nothing"), so draft-2's mean, whose comment says empty input gives ∞, cannot reach ∞ through [+] fold; the mechanism is gathered's fresh stack for a dict value
- Closes by: design side, if a step may reach below its item, and whether fold takes a seed or mean is rewritten
- Evidence: claim D2.13; draft-1.md:6; draft-2.md:23-25 (mean)

## sequence-shape
- Depends on it: fpl/eval.py items, rebuilt; tests/test_control.py
- Default in force: each, scan and fold take a strand or a ⟨ ⟩ list; each and scan give a strand back when they took one and every result is a number or a string, else a list; any other value as the sequence is refused
- Closes by: design side, the array model
- Evidence: combined-draft.md:44 (the one carrier is the nested array)

## text-as-array
- Depends on it: claims D1.1, D1.2, D1.3; fpl/features/draft1/examples/draft1.fpl:1-5
- Default in force: tab = and trim space split pair are no words and each over a string is refused, so draft1's read stays at no evaluator yet; D1.2's scan then fold is tested on a strand of 0 and 1, times standing for and
- Closes by: a later part, adding characters and the text words
- Evidence: draft-1.md:4-8

## pair-shape
- Depends on it: fpl/eval.py pair, unpair; tests/test_match.py
- Default in force: a b pair is the two-item list ⟨ a b ⟩, so a pair prints as a list and ( cons x xs ) matches it; cons : x xs -- ys puts x before a list's items, the order ( cons x xs ) gives
- Closes by: design, saying what a pair is and cons's argument order
- Evidence: fpl/features/match/examples/01-1-constructors-run.fpl:5-8; fpl/features/match/examples/04-4-list-patterns.fpl:5,8 (x y pair cons after xs ys zip reads cons as xs x -- ys)

## match-arity
- Depends on it: fpl/desugar.py _Desugar.match, row; tests/test_match.py
- Default in force: a match line takes the values the body's balance counts where it stands (the effect line's inputs, less what binders took), and leaves the balance at 0; a row is that many pattern cells then at most a body cell, else refused at the row; match outside a definition's body is an unknown word
- Closes by: design, saying what a match takes and whether code may follow it
- Evidence: claim D4.7; fpl/features/match/examples/05-5-prolog-s-family.fpl:3-8

## match-consumes
- Depends on it: fpl/eval.py matching; tests/test_match.py test_a_symmetric_case_delegates
- Default in force: a match takes its values; a row's body sees only the names its patterns bind, so _ leaves nothing behind
- Closes by: design, for claim D4.4, whose row body swap collide reads the values the match took
- Evidence: claim D4.4; fpl/features/match/examples/03-3-multiple-dispatch.fpl:5; :4 and :7 leave one value only if the match takes its arguments

## pin-scope
- Depends on it: fpl/desugar.py _Desugar.simple, local; tests/test_match.py
- Default in force: $x pins a name bound by a binder or by an earlier pattern of the row; effect-line names are no locals (as in every body), so $x of one is refused as unimplemented
- Closes by: design, saying whether an effect line's names are bound in its body
- Evidence: claim D4.6; fpl/features/match/examples/04-4-list-patterns.fpl:13-14 (pins x, the effect line's name)

## guard-test
- Depends on it: fpl/eval.py matched; tests/test_match.py
- Default in force: p ∈ test matches when p does and the word test, run on the value alone, leaves just 1; types are not implemented, so pos, Ship and Asteroid are unknown words, refused as unimplemented
- Closes by: fpl/types.py (07-goals and types), ascription to a type
- Evidence: claims D4.1, D4.4; fpl/features/match/examples/01-1-constructors-run.fpl:12

## exhaustive-by-catch-all
- Depends on it: fpl/desugar.py fallible, catches; tests/test_match.py test_a_match_is_exhaustive_exactly_when_its_effect_has_no_fail
- Default in force: a match is exhaustive when some row's patterns are all _ or names; ⟨⟩ then ( cons x xs ) is partial and carries +fail; a written +fail on an effect line is not read
- Closes by: fpl/types.py, exhaustiveness over a type's constructors
- Evidence: claim D4.5; fpl/features/match/examples/04-4-list-patterns.fpl:3-5

## fail-raises
- Depends on it: fpl/eval.py matching
- Default in force: no row matching is ERROR at the match word, "no row matches"; nothing catches it (rescue is unimplemented)
- Closes by: design, with rescue or a space's backtracking
- Evidence: claims D4.5, D4.8; decision (f) "+fail if non-exhaustive"

## invertible-when-tried
- Depends on it: fpl/eval.py undone, unrun; tests/test_match.py test_only_an_invertible_word_is_a_pattern
- Default in force: a constructor pattern names a word taking its patterns and leaving one value, checked in desugar; that its body is swap, pair, cons, literal pushes and such words, no recursion, is checked when the row is tried, refused at the pattern's head
- Closes by: implementer, a check over every definition once desugar holds all bodies
- Evidence: campaign scope 06-match "using any other word as a pattern is an error"

## resugar-match
- Depends on it: fpl/desugar.py spelled; tests/test_match.py test_a_match_is_not_written_back_as_code
- Default in force: code holding a match is not written back (w/history of a shadowed word with one); refused as unimplemented
- Closes by: implementer, writing a match as a line with its block
- Evidence: fpl/desugar.py listing, written

## effect-head-defaults
- Depends on it: fpl/desugar.py effect_line; fpl/features/match/examples/06-6-python-s-keywords.fpl; tests/test_match.py test_a_record_pattern_in_a_head_waits_for_defaults
- Default in force: an effect line is plain names only; a record pattern in the head (claim D4.11, S39: sep and end bound by the pattern, the caller's record unioned over the defaults) is refused as unimplemented, ERROR: 1:1 no evaluator yet
- Closes by: the part that implements records as signatures and with (S39), outside 06-match's scope; design, saying where a head's defaults bind
- Evidence: claim D4.11; fpl/features/match/examples/06-6-python-s-keywords.fpl:2-3; fpl/desugar.py effect_line

## typed-fragment
- Depends on it: fpl/types.py Kind, ARROWS, met, matched, agreed; tests/test_types.py test_a_well_typed_program_runs_to_a_value and test_a_step_keeps_the_sorts_a_state_leaves (the obligations of [fpl.types]), test_an_input_a_row_does_arithmetic_on_is_a_number_for_its_word, test_rows_agree_on_the_sort_a_later_row_finds, test_a_dead_row_counts_for_the_sorts_its_word_leaves
- Default in force: sorts are number, text, symbol and value; a match's rows are typed, a name a pattern binds of no known sort, and every row counts for its word's sorts, dead rows included (decided by PSJ, 2026-10-05): a sort any row finds for a value under the match or a name around it holds for the whole word, and the rows agree on what they leave, even where a pattern means a row never runs (a first _ row leaving a number and a later _ row leaving a text leave value, not number); pruning rows by verdict serves only static dispatch at a call site (fpl/types.py chosen), never this agreement, since a row wrongly pruned from it could return a sort the word does not promise, while with every row counting a bug in pruning can only over-refuse; OCaml 5.5 does the same, typing `let f x = match x with _ -> 0 | _ -> x + 1` as int -> int with Warning 11 (this match case is unused); no warning for a row that never runs is built; value is untracked and trusted (lists, quotations, dicts, strands of mixed items, what enclose , pair cons and a word with an untyped body leave), so arithmetic on one passes elaboration and may still fail at run time; a body calling a word defined later meets that word's effect line with values of no tracked sort; progress and preservation are stated over programs of number, text and symbol pushes, dup swap drop + - times, binders, matches of _ rows that agree on the sorts they leave, and words calling earlier words
- Closes by: fpl/types.py, sorts for lists, quotations and dicts and arrows for control words; design, whether a list or a quotation carries its items' or its code's type
- Evidence: fpl/ast_core.py EFFECTS and hole control-effects; claim D2.7 ("_ would ask it to infer")

## infer-hole
- Depends on it: fpl/types.py filled; fpl/eval.py nothing; tests/test_types.py test_a_hole_in_a_term_is_inferred_as_nothing, test_a_hole_that_is_not_nothing_is_refused_at_its_span; tests/test_match.py test_what_is_no_pattern_is_refused (_ as a row's body)
- Default in force: _ in a term is inferred only as nothing: accepted when the code after it takes the stack as it stands (and, at the end of a body, the effect line's count), run as a no-op; otherwise ERROR: <line>:<col> cannot infer _ : <ins> -- <outs>, the shape a goal there would report; no code is synthesised; a _ in code elaboration does not type runs as nothing
- Closes by: design side, what the elaborator may infer for _ (D2.7 "_ would ask it to infer"), and whether a _ in untyped code is refused
- Evidence: claim D2.7 (fpl/features/draft2/examples/04-effects-holes-ascription.fpl:5); handoff/SHAR-syntax.org:1016 (S40: "_ is inferred by the elaborator (or a wildcard, or absence)")

## symbolic-lane-unbounded
- Depends on it: make harden and make ready (quality/noslop.mk:81, HYPOTHESIS_PROFILE=symbolic pytest); every unit's gate.ready
- Default in force: the symbolic lane is not run; the six bounded lanes of the orchestrator's amendment stand in for make ready: check, the harden profile, crosshair icontract at 20 s per condition, mutants, gates, pip-audit
- Closes by: maintainer, a per-test budget for the symbolic lane in quality/, then a full make ready
- Evidence: quality/noslop.mk:81; orchestrator amendment 2026-09-28 21:50 (a run passed 27 minutes and was killed)

## mutant-verdicts-vary-between-runs
- Depends on it: mutants.allow, scripts/mutants (quality lane d)
- Default in force: every allowed entry is kept even when a run reports it as no longer living, since dropping one that lives on the next run fails the gate; the gate reports stale entries and does not fail on them; runs on one head differ (9 allowed entries reported no longer living on 7d1c179 in one run, none in the next); returned also as mutmut-run-dependent-kills
- Closes by: maintainer, deciding whether a Hypothesis-random kill falsifies an "equivalent" reason, or pinning the seed or profile scripts/mutants runs the suite under, then pruning mutants.allow
- Evidence: mutants.allow; scripts/mutants; session pr/05-comments.md (its PR note; the run logs are not kept)

## log-hash-stand-in
- Depends on it: fpl/multihash.py (hashed), fpl/log.py (every id, body name and MAC), fpl/session.py (evaluator)
- Default in force: blake2b-256 (multihash code 45600) from the standard library, one current code per store; blake3 (code 30) is refused as unknown
- Closes by: maintainer, a root [policy] commit adding blake3 to the lock, then switching the current code to 30; stored ids keep their code and are not rehashed
- Evidence: combined-draft.md:161 (row 39, blake3-256), as amended by PSJ's decisions of 2026-09-29 (decimal multihash, $45600 and &45600 on blake2b-256 now); quality/uv.lock holds no blake3; fpl/multihash.py:47

## log-signing
- Depends on it: fpl/log.py (keyed, the MAC), tests/test_log.py
- Default in force: a symmetric MAC, blake2b-256 keyed over the id's multihash bytes and outside the id's preimage; the key is $FPL_LOG_KEY, else $XDG_CONFIG_HOME/fpl/log.key, else ~/.config/fpl/log.key, created mode 0600 on first use
- Closes by: design, choosing the signature of C6's signed feeds; a signature replaces the MAC and ids stay unchanged
- Evidence: combined-draft.md:38 (C6, append-only signed single-writer logs); PSJ's decisions of 2026-09-29 (the MAC stays outside the hashed preimage); fpl/log.py:126

## log-checkpoint
- Depends on it: fpl/session.py (enter, program), fpl/log.py (load)
- Default in force: every call loads and re-verifies the whole log and runs every accepted input up to the event again as one file
- Closes by: design, a checkpoint of frontier and state hash (row 50) once the cost is measured
- Evidence: combined-draft.md:172 (row 50, checkpoints certified by a hash of the frontier); fpl/session.py:63, :175; fpl/log.py:313

## log-v0-in-fpl
- Depends on it: fpl/log.py, fpl/session.py
- Default in force: events named by the hash of their header, with deps (the state they extend) and links (a rewind's abandoned head), not v0's positional ids; this log is the first slice of v0 in FPL and the Rust v0 spike is abandoned
- Closes by: PSJ, with an FPL v0 prototype that reads these logs
- Evidence: PSJ's decisions of 2026-09-29; v0 repository a4dac05 src/event.rs:27-34 (Event with parents and links)

## repl-bare-entry
- Depends on it: fpl/__main__.py, tests/test_main.py:70-72
- Default in force: bare python -m fpl prints its usage line and exits 2; the loop is python -m fpl.repl
- Closes by: maintainer, either .agents/CONVENTIONS.md naming python -m fpl.repl or bare python -m fpl routed to fpl.repl.main
- Evidence: .agents/CONVENTIONS.md:21 (python -m fpl starts the REPL); tests/test_main.py:70-72; PSJ's decisions of 2026-09-29 (entry python -m fpl.repl, python -m fpl FILE unchanged)

## log-layering-unchecked
- Depends on it: fpl/multihash.py, fpl/log.py, fpl/session.py
- Default in force: no import-linter contract names the three modules; log imports multihash, fon and errors, never driver, by convention only
- Closes by: maintainer, a root [policy] commit adding them to quality/importlinter.ini
- Evidence: quality/importlinter.ini:46-60 (driver-on-top names fpl.repl only as a forbidden target)

## fuel-scope
- Depends on it: fpl/eval.py (metered), fpl/session.py (FUEL_DEFAULT), fpl/repl.py (--fuel), tests/test_fuel.py
- Default in force: 1,000,000 steps per top-level run line, nested runs counted, the budget recorded in each event; out of fuel is an error at the run's line
- Closes by: design, choosing the unit the budget bounds (line, input or session)
- Evidence: fpl/eval.py:95; fpl/session.py:18; [ 1 drop ] 100000 repeat took 500,003 steps in 1.23 s at 4e26338 (about 2.5 s per line at the default)

## log-fsync-barrier
- Depends on it: fpl/log.py (write, keyed), the law write-ahead (tests/test_repl.py)
- Default in force: os.fsync of each file and its directory; on macOS it does not flush the drive's cache (F_FULLFSYNC), so a power loss can lose an append that was printed
- Closes by: maintainer, a per-platform coverage policy under which a darwin branch to fcntl.F_FULLFSYNC can be kept at 100%
- Evidence: fpl/log.py:370, :385, :420, :490; fcntl.F_FULLFSYNC exists on darwin only; quality/coveragerc:10 (fail_under = 100)

## repl-transcript
- Depends on it: fpl/repl.py, fpl/session.py (enter), tests/test_repl.py, tests/test_session.py
- Default in force: an error in an earlier event is ERROR: @<seq> <l>:<c>; CHANGED <seq> $<id> names an earlier input whose output moved; HEAD <seq> $<id> follows an append on stderr; an input after the first starts at the left margin; an input ends at a blank line or once it is not pending; a first line with : is a command (:words :show :log :rewind E :canonical :quit; :words lists the builtins, then after a blank line the session's own words, a line `name : ins -- outs` each as w/effect spells it, appends nothing, and shows no slot kinds); joined outputs differ from the file's only where a run leaves a single empty stack; at a terminal a tab inserts itself (GNU readline; libedit untried)
- Closes by: design, fixing the transcript's form
- Evidence: tests/test_session.py:117, :126, :136; tests/test_repl.py:264, :299, :345; fpl/print.py:24-31

## head-group-pin
- Depends on it: fpl/desugar.py `_Desugar.code`, tests/test_overload.py test_a_pin_in_a_head_group_is_refused
- Default in force: a `$` pin inside a head group `( p )` is refused as unimplemented; a group clause binds its other inputs by fresh names `x′i` (the dispatcher-row mechanism), so a pin by the written name could not resolve
- Closes by: the part that binds head names, by binding a head's written names
- Evidence: design-09-v3.md §2.1 (Groups), §10 head-group-pin

## group-clause-fails
- Depends on it: fpl/desugar.py `_Desugar.statements`, `tests`; `f/n/i/effect` of a clause with a head group
- Default in force: a clause with a head group keeps `fallible(code)`, so its own effect is `+fail` (its one row misses when called by path); its dispatcher's `+fail` is computed from the dispatcher's rows, as for every match
- Closes by: the design side, by choosing between the written line and the computed `+fail` for `f/n/i/effect`
- Evidence: design-09-v3.md §1.1 (`f/n/i` effect as written) against §3.5 (a group clause's own +fail)

## dispatch-order
- Depends on it: fpl/desugar.py `_Desugar.dispatcher`, `crossed`, `disjoint`, `met`; tests/test_overload.py test_the_most_specific_then_the_newest_fitting_clause_wins, test_p1_and_p2, test_rows_sort_by_typed_count_then_newest, test_p3_is_refused_until_its_meet_is_a_clause, test_crossing_clauses_are_refused_unless_their_meet_is_a_clause
- Default in force: order B as the orchestrator defined it: a clause's typed inputs decide its specificity, whatever the types; rows sort by typed-input count descending, newest first by path ordinal among as many; crossing clauses are refused at the later head unless disjoint (two different builtin type words the program does not define) or their meet is a clause; a meet one input would type two ways is refused as unimplemented. First-row-wins `Match` reuses eval's `matching`
- Closes by: palimpsest, confirming the definition and amending combined-draft row 18 ("No automatic specificity") and row 73 for overloading, PSJ confirming; both pending
- Evidence: design-09-v3.md Read first, §3.1-§3.3; combined-draft.md:138 (row 18), :197 (row 73)

## tie-age
- Depends on it: fpl/desugar.py `Catalog.keyed`, `Catalog.ordinal`; tests/test_overload.py test_a_shadowing_clause_keeps_its_age, test_a_clause_keeps_the_ordinal_of_its_key
- Default in force: a same-key redefinition shadows its clause in place and keeps its path ordinal, which is its age among equally specific clauses (the log's later-shadows-earlier, keyed by path)
- Closes by: PSJ, choosing between keeping the place and taking the newest ordinal
- Evidence: design-09-v3.md §3.4 (Newest under shadowing), §11

## repl-crossing-order
- Depends on it: fpl/desugar.py `crossed`, run on every prefix a session desugars
- Default in force: the crossing check runs on the whole program each time; a file whose meet follows both crossing clauses is accepted, while typed into the REPL in that order the second crossing clause is refused, so the meet must be entered first
- Closes by: the design side, by accepting the narrowing of "REPL equals file" or deferring the check
- Evidence: design-09-v3.md §3.3 (The REPL checks every prefix)

## group-disjoint
- Depends on it: fpl/desugar.py `disjoint`
- Default in force: a head group is disjoint from nothing, since two groups may both match one value (`⟨ #circle ⟨ #rect 5 ⟩ ⟩`); two group clauses at one input are equally specific and the newest wins
- Closes by: the design side, if constructor patterns gain a static disjointness
- Evidence: design-09-v3.md §3.1 (Disjoint), §4 P7

## ambiguity-wording
- Depends on it: fpl/desugar.py `agree`, `crossed`; tests/test_overload.py test_clauses_of_one_arity_leave_as_many_values, test_crossing_clauses_are_refused_unless_their_meet_is_a_clause
- Default in force: an output-count mismatch reads `f/1/2 leaves 2, f/1/1 1`, after the slot-kind message `f/1/2 takes a thunk at 1, f/1/1 a value`; the meet in `g/2/2 is ambiguous with g/2/1 at x: Int  y: Int` takes the earlier clause's slot names
- Closes by: the design side, by fixing the wording
- Evidence: design-09-v3.md §2.3, §3.3, §11 (the wording of the ambiguity error); the design gives no output-count message

## refusal-not-fail
- Depends on it: fpl/ast_core.py `Refuse`; fpl/desugar.py `fallible`; tests/test_overload.py test_an_ambiguity_is_a_refusal_not_a_miss, test_p5_refuses_a_call_both_crossing_clauses_fit
- Default in force: landed in C10: an ambiguous call raises an `FplError` at the dispatcher's span, never `FailError`; `fallible` counts no `Refuse` row, so it adds no +fail; the walker has no `or` to tell the two apart outside guards
- Closes by: the part that lands `or`, which must catch `FailError` (`no row matches`) only
- Evidence: design-09-v3.md §3.4, §10 (refusal-not-fail)

## guard-failure
- Depends on it: fpl/eval.py `matched` (a guard's test), fpl/errors.py `FailError`; tests/test_overload.py test_a_guard_that_misses_is_not_fitting, test_an_error_in_a_guard_propagates
- Default in force: landed in C10, decided: a predicate used as a slot type must be total over the values it can meet; a test that fails with `no row matches` (`FailError`) is a miss, in dispatcher and match rows alike; an ambiguity refusal, fuel exhaustion or any other error inside the test propagates out of the call as that error
- Closes by: PSJ, only to widen the miss; order B itself waits on the row-18 amendment (dispatch-order), pending
- Evidence: design-09-v3.md §3.9, §10 (guard-failure); combined-draft.md:138 (row 18)

## number-split
- Depends on it: fpl/types.py `tested`
- Default in force: types has one number sort, so neither `Int` nor `Decimal` surely misses a number, and a more specific maybe row before a sure one keeps the call dynamic (P1's `5 f`)
- Closes by: types, by splitting the number sort, which lets `Int` surely miss a decimal and `Decimal` an integer; a guarded row stays at most maybe (static-dispatch-residual)
- Evidence: design-09-v3.md §3.6, §10 (number-split)

## static-miss
- Depends on it: fpl/types.py `chosen`; tests/test_overload.py test_a_call_types_leaves_unresolved_fails_at_run_time
- Default in force: a call no row can fit keeps the dispatcher's arrow and is `no row matches` +fail at run time; types neither refuses nor warns
- Closes by: types, with a warning
- Evidence: design-09-v3.md §3.6, §10 (static-miss)

## static-dispatch-residual
- Depends on it: fpl/types.py `chosen`, `surviving`, `tested`, `taken`; tests/test_overload.py test_types_resolves_a_dispatch_where_one_clause_row_survives, test_static_and_dynamic_dispatch_agree, test_a_guarded_row_is_never_a_sure_fit
- Default in force: pruning rows by verdict serves only static dispatch at a call site (`chosen`); a match in a body prunes nothing, every row of it counting for its word's sorts, dead rows included (decided by PSJ, 2026-10-05; hole typed-fragment), where design-09-v3.md §3.6 prunes there too; a row with a guard or an ascription (a cell with ∈, or `x: w`) is never a sure fit, so pruning never stops at it and TEXT_FIRST's `“a” f` keeps its catch-all row; a call keeps the dispatcher's arrow when a synthetic row survives, when an argument is an `Input` (even to a lone untyped clause of a two-group word), and when the one surviving row is a maybe whose clause's arrow refuses the argument sorts (`x: one` with body `1 +` on `“a”`: the run misses, so types does not refuse)
- Closes by: the design side, by accepting the maybe-row condition and the guard rule, which §3.6 does not state, and by taking body-match pruning out of §3.6
- Evidence: design-09-v3.md §3.6 (Pruning, Why an `Input` blocks resolution), §10 (static-dispatch-residual)
