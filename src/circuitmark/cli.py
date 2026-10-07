"""circuitmark command line.

    circuitmark render diagram.ckt -o diagram.svg
    circuitmark md README.md --svg-dir docs/circuits --in-place
    circuitmark check examples/*.ckt
    circuitmark symbols
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from . import __version__
from .errors import CircuitError
from .layout import layout
from .markdown import convert
from .parser import parse
from .render import THEMES, render_svg
from .symbols import kind_table


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write(path: Optional[str], data: str) -> None:
    if path in (None, "-"):
        sys.stdout.write(data)
        sys.stdout.flush()
        return
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)


def _warn(msg: str) -> None:
    sys.stderr.write(str(msg) + "\n")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="circuitmark", description="Write circuit diagrams as text, render them to SVG.")
    ap.add_argument("--version", action="version", version="circuitmark " + __version__)
    sub = ap.add_subparsers(dest="cmd")

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--theme", choices=sorted(THEMES), default="light", help="colour theme (default: light; `auto` uses currentColor and no background)")
        p.add_argument("--scale", type=float, default=1.0, help="multiply the SVG width/height attributes (viewBox is unchanged)")
        p.add_argument("-W", "--warnings-as-errors", action="store_true", help="exit 1 on dangling connections and other warnings")
        p.add_argument("-q", "--quiet", action="store_true", help="do not print warnings")

    r = sub.add_parser("render", help="render one or more .ckt files to SVG")
    r.add_argument("files", nargs="+", help=".ckt files, or - for stdin")
    r.add_argument("-o", "--output", help="output file (single input) or directory (several inputs); default: next to the input, or stdout for -")
    common(r)

    m = sub.add_parser("md", help="replace ```circuit blocks in Markdown with SVG")
    m.add_argument("files", nargs="+", help="Markdown files, or - for stdin")
    m.add_argument("-o", "--output", help="output file (single input) or directory; default: stdout")
    m.add_argument("-i", "--in-place", action="store_true", help="rewrite the Markdown file(s) in place")
    m.add_argument("--svg-dir", help="write each diagram to this directory and link it with ![title](path) instead of inlining <svg> (needed for GitHub READMEs)")
    m.add_argument("--link-prefix", help="path prefix used in the image links (default: --svg-dir as given)")
    m.add_argument("--keep-source", action="store_true", help="keep the circuit source below the diagram in a <details> block")
    common(m)

    c = sub.add_parser("check", help="parse and lay out without writing anything; exit 1 on errors (and warnings with -W)")
    c.add_argument("files", nargs="+", help=".ckt or .md files")
    c.add_argument("-W", "--warnings-as-errors", action="store_true")
    c.add_argument("-q", "--quiet", action="store_true")

    sub.add_parser("symbols", help="list element kinds, aliases and pin names")
    return ap


def _render_file(path: str, theme: str, scale: float) -> "tuple[str, list]":
    src = _read(path)
    prog = parse(src, filename=path)
    drawing = layout(prog)
    return render_svg(drawing, theme=theme, scale=scale), drawing.warnings


def main(argv: Optional[List[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 2
    try:
        if args.cmd == "symbols":
            print("%-10s %-22s %s" % ("kind", "aliases", "notes"))
            for name, aliases, doc in kind_table():
                print("%-10s %-22s %s" % (name, aliases, doc))
            print("\npins: .start/.end (also .1/.2); polarised: .neg/.pos (.-/.+), .anode/.cathode; bjt: .e/.c/.b (.base); opamp: .in-/.in+/.out")
            return 0
        nwarn = 0
        if args.cmd == "render":
            many = len(args.files) > 1
            if many and args.output and not os.path.isdir(args.output):
                os.makedirs(args.output, exist_ok=True)
            for path in args.files:
                svg, warns = _render_file(path, args.theme, args.scale)
                nwarn += _report(warns, args.quiet)
                if path == "-":
                    out = args.output if (args.output and not many) else None
                elif many:
                    base = os.path.splitext(os.path.basename(path))[0] + ".svg"
                    out = os.path.join(args.output, base) if args.output else os.path.splitext(path)[0] + ".svg"
                else:
                    out = args.output or os.path.splitext(path)[0] + ".svg"
                _write(out, svg)
                if out not in (None, "-") and not args.quiet:
                    _warn("wrote %s" % out)
        elif args.cmd == "md":
            many = len(args.files) > 1
            for path in args.files:
                text = _read(path)
                new, blocks = convert(text, filename=path, theme=args.theme, scale=args.scale, svg_dir=args.svg_dir,
                                      link_prefix=args.link_prefix, keep_source=args.keep_source)
                for b in blocks:
                    nwarn += _report(b.warnings, args.quiet)
                if args.in_place and path != "-":
                    out = path
                elif args.output and many:
                    os.makedirs(args.output, exist_ok=True)
                    out = os.path.join(args.output, os.path.basename(path))
                else:
                    out = args.output
                _write(out, new)
                if not args.quiet and out not in (None, "-"):
                    _warn("%s: %d diagram(s) -> %s" % (path, len(blocks), out))
        elif args.cmd == "check":
            for path in args.files:
                text = _read(path)
                if path.lower().endswith((".md", ".markdown")):
                    _, blocks = convert(text, filename=path, svg_dir=None, write_files=False)
                    warns = [w for b in blocks for w in b.warnings]
                    n = len(blocks)
                else:
                    drawing = layout(parse(text, filename=path))
                    warns = drawing.warnings
                    n = 1
                nwarn += _report(warns, args.quiet)
                if not args.quiet:
                    _warn("%s: ok (%d diagram%s, %d warning%s)" % (path, n, "" if n == 1 else "s", len(warns), "" if len(warns) == 1 else "s"))
        if nwarn and getattr(args, "warnings_as_errors", False):
            return 1
        return 0
    except CircuitError as e:
        _warn(str(e))
        return 1
    except FileNotFoundError as e:
        _warn("circuitmark: %s" % e)
        return 2
    except BrokenPipeError:
        return 0


def _report(warns: list, quiet: bool) -> int:
    if not quiet:
        for w in warns:
            _warn(str(w))
    return len(warns)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
