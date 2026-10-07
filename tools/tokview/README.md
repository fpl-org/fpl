# tokview

A local page that shows how a tokenizer cuts FPL source. Paste or pick a program and every
token is a coloured run over the text: where a tab, a comment marker or a cell edge fuses
with the word after it, and where a character breaks into byte fragments. The count of
tokens, characters, lines and bytes per token updates as you type.

    uv run --project tools/tokview tokview            # then open http://127.0.0.1:8765/
    uv run --project tools/tokview tokview --port 9000 --root .

The snippet menu lists `fpl/features/*/examples/*.fpl` of the checkout the tool sits in (or of
`--root`).

Controls:

- **tokenizer**: o200k (GPT-5.x), cl100k (GPT-4); Qwen2.5-Coder and DeepSeek-V3 with the
  `hf` extra: `uv run --project tools/tokview --extra hf tokview`. Their `tokenizer.json` is
  fetched from Hugging Face once, into `$XDG_CACHE_HOME/fpl-tokview` (or
  `~/.cache/fpl-tokview`).
- **hard wrap**: as written; notes folded at the column width on lone `;` lines, with `;;`
  lines wrapped under their own marker; or ventilated, one sentence per `;` line. Code is
  never rewritten, and a code line past the width counts as *over*. A note or comment line
  with nothing after its marker stays as it is.
- **width**: the column the notes are folded at, so under the folded hard wrap it changes the
  text sent to the tokenizer; under every mode it sets which code lines count as *over*, and
  where the rule and the soft wrap fall.
- **indent, gap, elastic tabstops, soft wrap, colours**: display only; the text sent to the
  tokenizer does not change.
- **Claude count**: the exact count from Anthropic's token-counting endpoint, which is not a
  model call. Set `ANTHROPIC_API_KEY` before starting the server; without it the count
  shows `–`.

The page serves on 127.0.0.1 only.
