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
- Closes by: design side or maintainer, a claims table or a confirmation of this reading
- Evidence: the session's design/INDEX.md (0 table lines in draft-1..4.md); design/claims.jsonl sha256 62c3c94e

## parser-algorithm
- Depends on it: fpl/parse.py, tests/test_parse.py, tests/test_ambiguity.py, every features example
- Default in force: LALR over fpl/grammar.lark with the tab indenter as postlex (linear, no backtracking); the pre-lexer counts strings and block comments; docs/STACK.md and AGENTS.md still name Earley with ambiguity='explicit'
- Closes by: maintainer, a root docs change settling LALR in docs/STACK.md, or a request for Earley
- Evidence: docs/STACK.md:27; handoff/SHAR-syntax.org:122 "The grammar"; SHAR gram/test_fpl.py:5-16 and the parser line after islands()

## ambiguity-over-flat
- Depends on it: tests/test_ambiguity.py ("programs derived from the grammar parse without ambiguity"), tests/test_print.py (the flat law)
- Default in force: from_lark draws from the block-free FLAT grammar (declared _INDENT/_DEDENT have no pattern to generate from), parsed by Earley ambiguity='explicit' lexer='basic'; the corpus is read by Earley with the tab indenter over the whole grammar; blocks are covered by the corpus and the printer's tree strategy only
- Closes by: implementer, a generator emitting indented blocks (a derivation that emits _INDENT and _DEDENT, rendered as tabs); or maintainer accepts
- Evidence: handoff/SHAR-syntax.org:486 printer.py docstring, its FLAT replace() for _NL and LCOMMENT match nothing in fpl.lark; after 8a753ec no _ambig in 2000 flat draws nor in the 29 pre-lexed examples, before it 1814 of 2000 and 26 of 29 (session grammar-fix/proof.log)

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
- Evidence: SHAR gram/test_fpl.py:18-38 and :40-67 count inside comments; features/match/examples/04-4-list-patterns.fpl:16

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
- Depends on it: features/{draft1,draft2,draft3,server,sketch,match}/examples/*.fpl; tests/test_conformance.py::test_example[*]; tests/test_ambiguity.py::test_no_ambiguity_in_the_corpus[*]
- Default in force: one .fpl per snippet set, cut at ;;; lines where the section parses alone, else joined to the part before (draft1, draft3 and server stay whole; draft2 is split 11 ways, sketch 7, match 7); the parts are byte copies of the tangled hand-off and concatenate to the snippet byte for byte
- Closes by: maintainer or design side, re-cutting the fixtures or confirming the rule
- Evidence: decision (b); session shar/split.tsv (parses_alone column, all yes); handoff/SHAR-syntax.org:828 "The snippet corpus"

## program-output
- Depends on it: fpl/driver.py, every .expected that is not an error line
- Default in force: what the Drafts say; where silent, the final stack printed by fpl/print.py (format fixed by 02-stack); whether top-level lines share a stack is part of this
- Closes by: design side, a Draft statement of what a program prints
- Evidence: decision (d); snippets carry values only as trailing ; comments

## expected-evolution
- Depends on it: every features/*/examples/*.expected (28, _template aside); tests/test_conformance.py::test_example[*]; tests/test_main.py::test_a_file_that_cannot_run_prints_one_error_line
- Default in force: every .expected starts as the one line ERROR: 1:1 no evaluator yet; a step-3 PR replaces one in its own [spec] commit with a value transcribed from the example's trailing ; comments or a Draft claim, source lines named, never from the implementation's output; the maintainer did not write these values
- Closes by: maintainer, reviewing each [spec] commit; each step-3 PR closes it per example
- Evidence: decisions (b) and (c); AGENTS.md "The oracle rule"; features/*/examples/*.expected at 3302d197

## unimplemented-words
- Depends on it: fpl/driver.py; every example still at ERROR: 1:1 no evaluator yet (all 28 at this commit)
- Default in force: a program using anything outside the implemented set reports ERROR: 1:1 no evaluator yet before evaluating (the skeleton's message and position, reused)
- Closes by: each step-3 part, shrinking the set
- Evidence: fpl/driver.py (skeleton)

## fresh-unify-space
- Depends on it: features/match (Prolog's family), features/sketch (logic tree)
- Default in force: not implemented; a program using fresh, unify or space reports ERROR: 1:1 no evaluator yet
- Closes by: maintainer, scheduling two-way unification
- Evidence: campaign scope, step 3

## goal-placeholder
- Depends on it: fpl/types.py (07-goals), programs containing ?
- Default in force (proposed; 07-goals confirms): elaboration writes GOAL <line>:<col> <expected effect> to stderr and continues with a placeholder; evaluating it gives ERROR: <line>:<col> unfilled goal
- Closes by: design side, the report's form and destination
- Evidence: handoff/SHAR-syntax.org:832 and :1016 (S40)

## printer-example-count
- Depends on it: tests/test_print.py; handoff/SHAR-syntax.org as evidence
- Default in force: SHAR printer.py prints "2000 examples" but sets max_examples=300; the port sets no count, so the profiles decide (quick 100, harden 2000)
- Closes by: syntax author (Caesura), correcting SHAR; else maintainer accepts the port's count
- Evidence: handoff/SHAR-syntax.org:559 and :605 (@settings) against :614-615 and :1233-1234 (the printed count)

## print-obligation-unlisted
- Depends on it: tests/test_print.py, scripts/props
- Default in force: the tree law is marked @pytest.mark.obligation("print then parse is the identity"), but quality/obligations.toml lists no printer obligation, so scripts/props does not enforce it
- Closes by: a root [policy] commit adding [fpl.print] to quality/obligations.toml
- Evidence: quality/obligations.toml ("Owed once there is a printer")

## fon-hash-sigil
- Depends on it: fpl/fon.py
- Default in force: &hex is a content hash, #name a symbol; SHAR's Hash class comment still says #hash
- Closes by: syntax author, correcting the comment in SHAR
- Evidence: handoff/SHAR-syntax.org:692 (Hash class comment) against :704 (HASH)

## agree-not-run
- Depends on it: handoff/SHAR-syntax.org (tangled files as evidence)
- Default in force: only the awk tangle ran; Org's tangle not compared
- Closes by: anyone with Emacs, ./SHAR.org agree printing TANGLERS-AGREE
- Evidence: handoff/SHAR-syntax.org:1203 "Seams"; session logs/wf0a-shar-nix.log

## shar-nix-unpinned
- Depends on it: reproducing the hand-off check under its own flake
- Default in force: SHAR's flake.nix has no locked nixpkgs; today it resolves hypothesis 6.156.1, not 6.168.0 of its recorded run; the output was identical
- Closes by: Caesura, committing a flake.lock with the shar
- Evidence: handoff/SHAR-syntax.org:80 (Bootstrap: flake.lock listed as not derived); session logs/wf0a-shar-nix.log

## shar-results-dup
- Depends on it: handoff/SHAR-syntax.org #+RESULTS: check-run as evidence
- Default in force: printer.py imports test_fpl.py, whose unguarded top-level battery then runs twice; RESULTS shows only one extra line of it
- Closes by: Caesura, guarding test_fpl.py's battery with if __name__ == '__main__'
- Evidence: handoff/SHAR-syntax.org:1203 "Seams" (#+RESULTS: check-run, examples2 printed twice); session logs/wf0a-filtered.txt against logs/wf0a-expected.txt

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
- Depends on it: fpl/parse.py (_Build.comment), features/match/examples
- Default in force: a ; with no code before it that continues no note is kept as a note line (one empty frame and its note), not refused as the rule says, because the corpus has four: features/match/examples/04-4-list-patterns.fpl:15-16, 07-7-abc-s-keywords.fpl:2-3; no ;; is after code
- Closes by: PSJ or Caesura rewriting those lines (as ;; or as notes after code); then the builder refuses the standalone ;
- Evidence: session grammar-fix/measure.log, proof2.log

## note-alignment
- Depends on it: fpl/parse.py (_Build.comment), fpl/print.py (_Out.column, comment)
- Default in force: PSJ's decision of 2026-09-29: a continuation line of a note carries as many tabs before its ; as the code line has before its own ; (elastic tabstops), and a continued note stands in its own cell; the printer sets every note in its own cell and aligns its continuations; the builder does not refuse a misaligned continuation, since the corpus has two: features/match/examples/03-3-multiple-dispatch.fpl:8 (1 tab, note at 5), 06-6-python-s-keywords.fpl:6 (0 tabs, note at 1)
- Closes by: Caesura folding the rule into the hand-off; PSJ or Caesura realigning those lines; then the builder refuses with "a continued note aligns with the note above: N tabs"
- Evidence: session grammar-fix/proof2.log (note alignment section)

## comment-heads-block
- Depends on it: fpl/grammar.lark (line)
- Default in force: a comment line may head an indented block (an outline heading); no example has one
- Closes by: Caesura, confirming or refusing it
- Evidence: session grammar-fix/proof2.log (";;; s\n\ta" parses once, 0 heads in the corpus)

## comment-in-enclosure
- Depends on it: fpl/parse.py (_tree)
- Default in force: a comment inside a multi-line enclosure is refused, ERROR: a comment cannot stand inside an enclosure; no example has one
- Closes by: Caesura, giving comments a place inside enclosures if one is wanted
- Evidence: session grammar-fix/proof2.log (0 comments inside an enclosure in the corpus); tests/test_parse.py::test_a_refusal_is_one_error_line

## empty-first-line
- Depends on it: fpl/grammar.lark (start), fpl/print.py (render)
- Default in force: a file that opens with blank lines has one empty first line, and "\n\tx" gives that line a block; a blank source ("", "\n") is that one line and prints as the empty text; no example opens blank (PSJ: leading blank lines are not useful, a refusal is acceptable)
- Closes by: PSJ or Caesura, keeping it or refusing a blank first line
- Evidence: session grammar-fix/proof2.log; tests/test_parse.py::test_only_the_first_line_is_empty_and_it_may_hold_a_block

## form-feed-line
- Depends on it: fpl/grammar.lark (_NL), tests/test_print.py::test_a_blank_line_is_part_of_its_blank_run_whatever_it_holds
- Default in force: a form feed is the page separator, ignored like a space; a line holding only tabs, spaces and form feeds inside a blank run is part of the run, so it leaves no line and prints as nothing; only the last line's tabs are indentation, so a form feed before a line's tabs leaves it at depth 0 as before
- Closes by: Caesura or PSJ, confirming the form feed as a page separator, or refusing it outside strings and comments
- Evidence: bd41245 fix(grammar): read a line of form feeds as part of its blank run; session grammar-fix/proof3.log, ffcheck.log
