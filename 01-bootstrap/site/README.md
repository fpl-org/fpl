# Site

This is the Astro project. It reads the Markdown above it and emits HTML. It does not run Marimo cells and it does not use MDX.

`src/content.config.ts` takes concept notes and skips `index.md` and `README.md`, because those two are folder pages, not concepts.

Build with `npm install` and `npx astro build` from this directory. The output is `dist/`.
