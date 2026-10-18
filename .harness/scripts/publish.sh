#!/bin/sh
# Publish the literate site and the LuaLaTeX book to psjg/fpl-lit-scratch.
#   publish.sh            html, then tex, then pdf, then site
#   publish.sh html       README -> index.qmd, then the website
#   publish.sh tex        the book, written to .book/FPL.pdf
#   publish.sh pdf        that PDF onto gh-pages and onto main as pdf/FPL.pdf
#   publish.sh site       .site/ onto the gh-pages root, plus the PDF when it exists

set -eu

top=$(git rev-parse --show-toplevel)
cd "$top"
scratch=https://github.com/psjg/fpl-lit-scratch.git

html() {
  python3 "$top/.harness/scripts/homepage.py"
  quarto render
}

tex() {
  quarto render --profile book --to pdf
}

commit_push() {
  branch=$1
  message=$2
  dir=$3
  # This machine's git template ignores every new file except flake.nix.
  git -C "$dir" add -f -A
  if git -C "$dir" diff --cached --quiet; then
    echo "publish: $branch unchanged"
    return
  fi
  git -C "$dir" commit -m "$message"
  git -C "$dir" push origin "HEAD:$branch"
}

pdf() {
  test -f "$top/.book/FPL.pdf"
  pages=$(mktemp -d)
  main=$(mktemp -d)
  git clone --depth 1 --branch gh-pages "$scratch" "$pages"
  cp "$top/.book/FPL.pdf" "$pages/FPL.pdf"
  touch "$pages/.nojekyll"
  commit_push gh-pages "chaos: publish the lualatex pdf" "$pages"
  git clone --depth 1 --branch main "$scratch" "$main"
  mkdir -p "$main/pdf"
  cp "$top/.book/FPL.pdf" "$main/pdf/FPL.pdf"
  commit_push main "chaos: publish the lualatex pdf" "$main"
}

site() {
  test -d "$top/.site"
  pages=$(mktemp -d)
  git clone --depth 1 --branch gh-pages "$scratch" "$pages"
  rsync -a --delete --exclude .git "$top/.site/" "$pages/"
  if [ -f "$top/.book/FPL.pdf" ]; then
    cp "$top/.book/FPL.pdf" "$pages/FPL.pdf"
  fi
  touch "$pages/.nojekyll"
  commit_push gh-pages "chaos: publish the site" "$pages"
}

if [ "$#" -eq 0 ]; then
  html
  tex
  pdf
  site
  exit
fi

case $1 in
  html | tex | pdf | site) "$1" ;;
  *)
    echo "usage: publish.sh [html|tex|pdf|site]" >&2
    exit 1
    ;;
esac
