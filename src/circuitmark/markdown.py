"""Replace ```circuit fenced blocks in Markdown with rendered SVG (inline, or files + image links)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .errors import CircuitError, Warning
from .layout import layout
from .parser import parse
from .render import render_svg

_FENCE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>```+|~~~+)[ \t]*(?P<lang>circuit|circuitmark|ckt)\b[^\n]*\n(?P<body>.*?)^(?P=indent)(?P=fence)[ \t]*$",
                       re.M | re.S)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class Block:
    source: str
    start_line: int
    title: Optional[str] = None
    svg: Optional[str] = None
    path: Optional[str] = None
    warnings: List[Warning] = field(default_factory=list)


def find_blocks(text: str) -> List[Tuple[re.Match, Block]]:
    out = []
    for m in _FENCE_RE.finditer(text):
        body = m.group("body")
        indent = m.group("indent")
        if indent:
            body = "\n".join(line[len(indent):] if line.startswith(indent) else line for line in body.splitlines())
        start_line = text.count("\n", 0, m.start()) + 2
        out.append((m, Block(body, start_line)))
    return out


def slug(title: Optional[str], n: int) -> str:
    base = _SLUG_RE.sub("-", (title or "").lower()).strip("-")
    return base or "circuit-%02d" % n


def convert(text: str, filename: str = "<markdown>", theme: str = "light", scale: float = 1.0,
            svg_dir: Optional[str] = None, link_prefix: Optional[str] = None, keep_source: bool = False,
            write_files: bool = True) -> Tuple[str, List[Block]]:
    """Return (new_markdown, blocks). With `svg_dir`, SVG files are written there and the block becomes an
    image link (prefix `link_prefix`, default = svg_dir); otherwise the SVG is inlined."""
    blocks = find_blocks(text)
    if not blocks:
        return text, []
    pieces = []
    last = 0
    done: List[Block] = []
    for n, (m, blk) in enumerate(blocks, 1):
        try:
            prog = parse(blk.source, filename="%s (block at line %d)" % (filename, blk.start_line))
        except CircuitError as e:
            e.line = e.line + blk.start_line - 1 if e.line else blk.start_line
            e.filename = filename
            raise
        drawing = layout(prog)
        for w in drawing.warnings:
            w.line = w.line + blk.start_line - 1 if w.line else blk.start_line
            w.filename = filename
        blk.warnings = drawing.warnings
        blk.title = drawing.title
        blk.svg = render_svg(drawing, theme=theme, scale=scale)
        indent = m.group("indent")
        if svg_dir is not None:
            name = slug(blk.title, n) + ".svg"
            blk.path = os.path.join(svg_dir, name)
            if write_files:
                os.makedirs(svg_dir, exist_ok=True)
                with open(blk.path, "w", encoding="utf-8") as f:
                    f.write(blk.svg)
            prefix = svg_dir if link_prefix is None else link_prefix
            link = (prefix.rstrip("/") + "/" + name) if prefix else name
            alt = blk.title or "circuit diagram"
            replacement = "%s![%s](%s)" % (indent, alt.replace("]", ""), link.replace(os.sep, "/"))
        else:
            replacement = "\n".join(indent + line for line in blk.svg.rstrip("\n").splitlines())
        if keep_source:
            replacement += ("\n\n%s<details><summary>circuit source</summary>\n\n%s```circuit\n%s%s```\n\n%s</details>"
                            % (indent, indent, "".join(indent + line + "\n" for line in blk.source.splitlines()), indent, indent))
        pieces.append(text[last:m.start()])
        pieces.append(replacement)
        last = m.end()
        done.append(blk)
    pieces.append(text[last:])
    return "".join(pieces), done
