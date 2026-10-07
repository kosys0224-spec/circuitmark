"""Regenerate docs/symbols.svg (+ docs/symbols.ckt), docs/examples/*.svg, examples/README.md and (with Playwright) docs/demo.png.

    python scripts/make_docs.py            # SVGs + examples/README.md
    python scripts/make_docs.py --png      # also docs/demo.png (needs: pip install playwright)
"""
from __future__ import annotations

import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from circuitmark import layout, parse, render_svg  # noqa: E402
from circuitmark.symbols import kind_table  # noqa: E402

TWO_TERMINAL = [k for k, _, _ in kind_table() if k not in ("ground", "terminal", "dot", "npn", "pnp", "opamp", "box")]


def symbol_sheet() -> str:
    lines = ["title Symbols"]
    cols = 4
    for i, name in enumerate(TWO_TERMINAL):
        x, y = (i % cols) * 6, (i // cols) * 3
        lines.append("at %d,%d" % (x, y))
        lines.append("wire right")
        lines.append("%s right label \"%s\" above" % (name, name))
        lines.append("wire right")
    rows = (len(TWO_TERMINAL) + cols - 1) // cols
    y = rows * 3
    lines += ["at 0,%d" % y, "wire right", "npn right label \"npn\" above", "wire right",
              "at 6,%d" % y, "wire right", "pnp right label \"pnp\" above", "wire right",
              "at 12,%d" % y, "wire right", "opamp right label \"opamp\" above", "wire right",
              "at 18,%d" % y, "wire right", "terminal right label \"terminal\"",
              "at 0,%d" % (y + 3), "wire right", "ground right label \"ground\"",
              "at 6,%d" % (y + 3), "wire right", "dot label \"dot\" above", "wire right",
              "at 12,%d" % (y + 3), "wire right", "box \"box\" right", "wire right",
              ]
    return "\n".join(lines) + "\n"


def main() -> None:
    src = symbol_sheet()
    with open(os.path.join(ROOT, "docs", "symbols.ckt"), "w", encoding="utf-8") as f:
        f.write(src)
    d = layout(parse(src, filename="symbols.ckt"))
    d.warnings = []  # the sheet intentionally leaves pins open
    with open(os.path.join(ROOT, "docs", "symbols.svg"), "w", encoding="utf-8") as f:
        f.write(render_svg(d))

    readme = ["# Examples", "", "Each `.ckt` file in this directory, rendered with `circuitmark render`. "
              "Regenerate with `python scripts/make_docs.py`.", ""]
    for path in sorted(glob.glob(os.path.join(ROOT, "examples", "*.ckt"))):
        name = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as f:
            text = f.read()
        d = layout(parse(text, filename=path))
        for w in d.warnings:
            print("warning:", w)
        out = os.path.join(ROOT, "docs", "examples", name + ".svg")
        with open(out, "w", encoding="utf-8") as f:
            f.write(render_svg(d))
        readme += ["## %s" % (d.title or name), "", "![%s](../docs/examples/%s.svg)" % (d.title or name, name), "",
                   "```circuit", text.rstrip("\n"), "```", ""]
        print("wrote", os.path.relpath(out, ROOT))
    with open(os.path.join(ROOT, "examples", "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(readme))
    if "--png" in sys.argv:
        make_png()


def make_png() -> None:
    from playwright.sync_api import sync_playwright  # type: ignore

    path = os.path.join(ROOT, "examples", "rc-lowpass.ckt")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    svg = render_svg(layout(parse(text)), scale=1.6)
    code = text.replace("&", "&amp;").replace("<", "&lt;")
    html = """<html><body style="margin:0;background:#fff"><div style="display:inline-flex;align-items:center;gap:28px;padding:22px 26px;font-family:ui-sans-serif,system-ui,sans-serif">
    <pre style="margin:0;font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#f6f8fa;border:1px solid #d0d7de;border-radius:8px;padding:16px 18px;color:#24292f">%s</pre>
    <div style="font-size:30px;color:#8c959f">&#8594;</div>
    <div>%s</div></div></body></html>""" % (code, svg)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(device_scale_factor=2)
        pg.set_content(html)
        pg.locator("div").first.screenshot(path=os.path.join(ROOT, "docs", "demo.png"))
        b.close()
    print("wrote docs/demo.png")


if __name__ == "__main__":
    main()
