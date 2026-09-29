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
- Depends on it: fpl/driver.py, fpl/desugar.py listing, tests/test_desugar.py, every .expected that is not an error line
- Default in force: each top-level line that is not a definition runs on a fresh stack and prints one line, the stack it leaves as fpl/print.py writes the items that push it, with a bar between two literals that would otherwise strand; a definition prints nothing; a program with no line to run prints nothing. A section prints in the printer's spelling, [ 1 2 3 + ] for the Draft's [1‿2‿3 +]
- Closes by: design side, a Draft statement of what a program prints
- Evidence: decision (d); draft2 §frames, features/draft2/examples/01-frames.fpl:2-4 (one result per line; line 3 has nothing below after line 2 left 2 3 4); claims D2.1-D2.3

## expected-evolution
- Depends on it: every features/*/examples/*.expected (28, _template aside); tests/test_conformance.py::test_example[*]; tests/test_main.py::test_a_file_that_cannot_run_prints_one_error_line
- Default in force: every .expected starts as the one line ERROR: 1:1 no evaluator yet; a step-3 PR replaces one in its own [spec] commit with a value transcribed from the example's trailing ; comments or a Draft claim, source lines named, never from the implementation's output; the maintainer did not write these values
- Closes by: maintainer, reviewing each [spec] commit; each step-3 PR closes it per example
- Evidence: decisions (b) and (c); AGENTS.md "The oracle rule"; features/*/examples/*.expected at 3302d197

## unimplemented-words
- Depends on it: fpl/desugar.py unimplemented; every example still at ERROR: 1:1 no evaluator yet (26 of 28 at this commit: 01-frames for swap-args, 09-rotates for fold, the rest for more)
- Default in force: desugar refuses, before anything runs, all but: decimal numbers, strings without islands, [ ], ( ) of one cell, ⟨ ⟩ of literals, bars, tabs, blocks, name : ins -- outs definitions (each slot a name or name: Type), →x and ->x of a plain name or a path, #name symbols, { } of plain keys each with one item pushing one value, name/ heads with a block of definitions, name/ heads and #name bind lines, paths a/b and ../x that name a defined word, w/history, and the words of fpl/ast_core.py EFFECTS (+ - times swap dup drop enclose ,), with ERROR: 1:1 no evaluator yet (the skeleton's message and position, reused)
- Closes by: each step-3 part, shrinking the set
- Evidence: fpl/driver.py (skeleton); fpl/ast_core.py EFFECTS

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
- Depends on it: fpl/desugar.py arity, fpl/eval.py builtin
- Default in force: a defined word's arity is read from its effect line and trusted; a body that leaves fewer values than declared makes a later word find too few, refused at that word as stack underflow
- Closes by: fpl/types.py (types part), checking a body against its effect line
- Evidence: claim D3.4; tests/test_desugar.py test_a_word_refuses_at_its_position

## definition-scope
- Depends on it: fpl/desugar.py desugar, fpl/eval.py evaluate, tests/test_desugar.py test_lcurry_puts_a_swap_between
- Default in force: definitions are global to the program; a word may be used above its definition; a later definition of a name shadows an earlier one for every line, builtins included
- Closes by: design side, with bind's ordered log (decision f) once 03-binders lands
- Evidence: features/draft2/examples/02-currying.fpl:4-5 (lcurry uses curry); decision (f) "later shadows earlier"

## pervasive-arithmetic
- Depends on it: fpl/eval.py arithmetic, tests/test_desugar.py
- Default in force: + - times take numbers or strands of numbers; a number meets each item of a strand, two strands meet item by item; unequal lengths and non-numbers are refused at the word
- Closes by: design side, the arithmetic of the array model
- Evidence: claim D2.1 (1 | 1 2 3 + gives 2 3 4)

## list-elements
- Depends on it: fpl/desugar.py enclosure, element
- Default in force: ⟨ ⟩ holds literals only (numbers, strings, quotations, lists), each item one element, nothing strands inside; , joins two lists
- Closes by: design side, what a ⟨ ⟩ body may compute
- Evidence: features/draft2/examples/08-objects-are-directories.fpl:7 (⟨⟩ as an empty accumulator)

## number-glyphs
- Depends on it: fpl/desugar.py atom
- Default in force: ∞ and π, which the affix pass reads as numbers, are refused as unimplemented; numbers are integers and decimals, a decimal kept exact as written
- Closes by: implementer, once an example that uses them evaluates
- Evidence: fpl/lex.py NUMBER; features/draft1/examples/draft1.fpl:29-32

## effect-query
- Depends on it: claim D3.4
- Default in force: each effect line is kept as declared data (fpl/ast_core.py Effect, on Define; EFFECTS for builtins); the query words/*/effect is not implemented
- Closes by: the part that implements directories and paths
- Evidence: claim D3.4 (features/draft3/examples/draft3.fpl)

## stack-claims-deferred
- Depends on it: claims D1.6, D1.9, D1.10, D2.8, D2.9, D2.10, D2.14, D2.15, D2.16 (part 02-stack)
- Default in force: open, their examples at no evaluator yet: D2.9 needs binders and each (03-binders); D2.8 and D2.10 symbols, pair, dict, method, inverse; D2.14 and D2.15 unquote; D2.16 laziness; D1.6 ! and if; D1.9 and D1.10 ∞, inner, log, repeat and a block of literals under a head that is not a definition
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
- Default in force: , takes two code slots (it joins quotations as data, never runs them); enclose takes a value; curry and lcurry, defined in features/draft2/examples/02-currying.fpl with bare names, take values
- Closes by: design side (question to Caesura: are , enclose and curry code, thunk or polymorphic; , also joins lists, and curry takes a thunk in 11-laziness.fpl:3)
- Evidence: features/draft2/examples/02-currying.fpl:2-5; features/draft2/examples/11-laziness.fpl:3; claims D1.4, D1.5

## bare-slot-names
- Depends on it: fpl/desugar.py typed; every effect line in features/ and tests/
- Default in force: a bare name on an effect line stays legal, an untyped value slot; only `name: Type` declares a thunk or code slot
- Closes by: design side (question to Caesura: do bare names stay, and do the old bracket slots `or : [ p ] [ q ]` survive)
- Evidence: design doc FON tab S49 item 1; features/sketch/examples/01-1-a-logic.fpl:12-13

## thunk-type-dropped
- Depends on it: fpl/desugar.py slot, declaration; tests/test_desugar.py test_core_without_sugar_writes_back_as_its_source
- Default in force: the core keeps each input's slot, not its type: `x: Int` is written back as `x`, `t: [ -- x ]` as `t: []`, `c: Code` as itself; an output's type is read past
- Closes by: fpl/types.py (types part), keeping the declared types it checks
- Evidence: design doc FON tab S49 item 1 (`f : x: Int  y: Int -- z: Int`)

## double-use-refusal
- Depends on it: features/server/examples/server.fpl:21 (a ;; comment, not run)
- Default in force: not refused in this part: a quotation both forced and inspected needs a kind on each stack cell through dup, which desugar does not track
- Closes by: fpl/types.py (#59, types), carrying thunk and code kinds through the stack and refusing the double use
- Evidence: features/server/examples/server.fpl:19-21; design doc FON tab S49 rule 5

## number-bound
- Depends on it: fpl/ast_core.py DIGITS, fpl/desugar.py number, fpl/eval.py arithmetic, tests/test_desugar.py::test_a_numeral_longer_than_digits_is_refused_at_its_position, ::test_a_result_of_more_than_digits_digits_is_refused_at_the_word
- Default in force: a numeral has at most 4096 digits, its sign and point not counted, the number FON's reader bounds a token by (fon.read max_token); a longer one is ERROR: <line>:<col> number too long at the numeral. 4096 is under Python's 4300-digit int/str conversion limit, so the bound is the language's, not the interpreter's setting. A result of + - times of magnitude 10^4096 or more is ERROR: <line>:<col> number too large at the word, so an integer has at most 4096 digits, written or computed, and a decimal never overflows its context; a computed decimal keeps the context's 28 significant digits and its fraction is not bounded
- Closes by: design, naming the bound on a number, written and computed (or none, with a reader and printer that never meet the limit)
- Evidence: a 4301-digit numeral raised ValueError from int() in fpl/desugar.py number before this entry, a traceback past the FplError boundary of fpl/__main__.py, as 10 squared 13 times did from str() in fpl/desugar.py shown and 9.9 squared 22 times did as decimal.Overflow in fpl/eval.py; docs/CONVENTIONS.md "no Python traceback ever reaches the user"

## binder-scope
- Depends on it: fpl/desugar.py (body, quote, scoped), fpl/eval.py (substitute), tests/test_binders.py
- Default in force: →x names the top for the rest of the sequence it is written in: a definition's body across its lines and the blocks under them, one top-level line, one child line under a thunk or code slot, one quotation or section; a child under a value slot runs in place, so its binder lives on in the sequence the child runs in, like a frame's (hole child-slots); eval substitutes the value for the name there (lexical, a nested binder of the name shadows, nothing mutates); past it the name is no word; the printer writes → for both spellings
- Closes by: design, by saying where a binder's scope ends at top level and in a child line
- Evidence: decision (f); features/server/examples/server.fpl:3-4 (p bound on one body line, read on the next); features/draft2/examples/07-scope-follows-the.fpl:3-5; features/draft2/examples/08-objects-are-directories.fpl:6-10 rebinds acc and s in a repeat child and reads acc after it, which shadowing cannot give

## dict-values
- Depends on it: fpl/desugar.py (dict), fpl/eval.py (gathered), tests/test_binders.py
- Default in force: { } pairs a plain name key with the next item, which must push exactly one value (a literal, symbol, list, quotation, dict, bound name or a word taking none); each value runs on a fresh stack when the dict is reached; ( ) as a value, a strand, an odd count and a path key are refused as unimplemented; a repeated key is refused where it repeats with fpl/fon.py's message; symbols do not strand
- Closes by: design, by saying what a dict value may be and where one ends
- Evidence: features/match/examples/06-6-python-s-keywords.fpl:2-5; fpl/fon.py dict; features/draft2/examples/08-objects-are-directories.fpl:3 (#x #y swap)

## require-ensure-rescue
- Depends on it: nothing yet
- Default in force: no example uses require, ensure or rescue; they are unknown words, refused as unimplemented
- Closes by: design, with an example of f/require
- Evidence: grep -l over features/*/examples/*.fpl finds none; decision (f)

## directory-log
- Depends on it: fpl/desugar.py (Catalog, directory, mount, _Desugar.call, origin), tests/test_binders.py; features/draft3/examples/draft3.fpl:1-9, features/match/examples/05-5-prolog-s-family.fpl:2, features/server/examples/server.fpl:4
- Default in force: a head name/ with a block is a directory; its definitions, subdirectories and #name bind mounts form one ordered log, read whole before any line runs (the rule top-level definitions already follow), where the latest entry holding a name wins; a word is a directory holding its history; a name resolves at desugar time from the word's own directory outward, ../x from the directory holding the word; a mount sees only the words its directory defines, never its mounts; a second head of the same name appends to the same log; a name/ head without a block, a deeper a/b/ head, any other line in a directory, bind of anything but a literal #name, a #name that is no directory and ../x on a top-level line are refused as unimplemented
- Closes by: design, by saying whether a log entry is visible above the line that adds it, whether mounts chain, and what a directory holds besides definitions and binds
- Evidence: claims D3.1 (draft3.fpl:7 "ordered log append (§5.2): later shadows earlier"), D3.5 (draft3.fpl:13 "takes ../io lexically"); decision (f) f/require; features/sketch/examples/07-7-facts-signed.fpl:18 binds a quotation of paths, which this default refuses

## history-shape
- Depends on it: fpl/eval.py (evaluate), fpl/desugar.py (HISTORY), tests/test_binders.py; features/draft3/examples/draft3.fpl:11
- Default in force: w/history pushes a ⟨ ⟩ list of the definitions of w that a later one shadows, oldest first, each its body as a quotation; the one in force is not in it; one definition gives ⟨⟩
- Closes by: design, by saying what a history entry is (body, effect, source) and whether the one in force belongs to it
- Evidence: claim D3.3 (draft3.fpl:11 "shadowed definitions")

## effect-sugar-io
- Depends on it: features/draft3/examples/draft3.fpl:13, features/server/examples/server.fpl:2 and 10
- Default in force: only the lexical half of D3.5 is in force (../x resolves from the directory holding the word); an effect line naming +io or any +effect is refused as unimplemented, so nothing threads an effect linearly
- Closes by: the effects part, with the design saying what +io desugars to
- Evidence: claim D3.5 (draft3.fpl:13 "sugar: takes ../io lexically, threads it linearly (§4.3 answer)")

## with-record-union
- Depends on it: features/match/examples/06-6-python-s-keywords.fpl:5
- Default in force: with is no word and is refused as unimplemented; it needs record patterns in a head (06-6-python-s-keywords.fpl:2), which no part implements yet
- Closes by: implementer of 06-match, after record-pattern heads
- Evidence: claim D4.12 ("with: curry-with-union; later calls still override")

## qualified-resugar
- Depends on it: fpl/desugar.py (resugar, named, written), tests/test_print.py
- Default in force: resugar writes a definition inside a directory as a top-level path head (m/sq : x -- y), which does not parse back to the same statement; the printer's round trip holds only for programs without directories, the only ones its strategies generate
- Closes by: implementer, by resugaring the log as nested name/ heads when a property needs it
- Evidence: fpl/desugar.py written
