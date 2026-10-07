# Contributing to circuitmark

## Most useful contributions

1. **New symbols.** A symbol is a function in `src/circuitmark/symbols.py` that returns a few primitives in a local frame (the element runs from `(0,0)` to `(L,0)`, body 30 px wide in the middle), registered with a `Kind(...)` entry (name, aliases, pins, label clearance). Add it to the table in `docs/syntax.md` and run `python scripts/make_docs.py` to refresh the symbol sheet; `tests/test_circuitmark.py::ParserTests.test_every_kind_parses_and_renders` covers it automatically.
2. **Diagrams that lay out badly.** Open an issue with the `.ckt` source and what you expected; label placement and junction detection are heuristics and each fixed case becomes a test.
3. **Integrations.** mkdocs plugin, pre-commit hook, editor syntax highlighting, a PNG back-end behind an optional dependency.

## Layout

```
src/circuitmark/parser.py     text -> statements (dataclasses), errors with line numbers
src/circuitmark/symbols.py    symbol drawings and the Kind registry
src/circuitmark/layout.py     cursor walk -> absolute geometry, pins, junctions, warnings, labels
src/circuitmark/render.py     Drawing -> SVG
src/circuitmark/markdown.py   ```circuit fenced blocks
src/circuitmark/cli.py
examples/*.ckt                every example must render without warnings (tested)
docs/                         syntax.md, symbols sheet, generated example SVGs, demo.png
scripts/make_docs.py          regenerates docs/examples, docs/symbols.*, examples/README.md (+ demo.png with --png)
```

## Rules

- Standard library only, Python 3.9+. Output must be deterministic (same input, byte-identical SVG).
- Every language change needs a test, a line in `docs/syntax.md` and a CHANGELOG entry.
- Keep generated docs in sync: CI runs `scripts/make_docs.py` and fails if `docs/examples`, `docs/symbols.svg` or `examples/README.md` change.

## Running

```bash
pip install -e .
python -m unittest discover -s tests -v
circuitmark check -W examples/*.ckt
python scripts/make_docs.py --png     # --png needs `pip install playwright && playwright install chromium`
```
