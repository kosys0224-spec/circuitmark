"""Turn circuitmark text into a list of statements.

The language is line based. One statement per line, `#` starts a comment.

    title RC low-pass filter
    V1: battery 9V up            # [ID:] KIND [VALUE] [DIRECTION] [len N] [flip] [mirror] [label "text"] [noid]
    R1: resistor 10k right
    node out                     # name the current point
    C1: capacitor 100n down
    wire left 3                  # wire DIRECTION [units]
    wire to V1.neg               # Manhattan wire to an anchor (horizontal first; add `vfirst` to go vertical first)
    at out                       # move without drawing: a node name, ID.pin, or grid coordinates `4,2`
    GND: ground down
    label "Vout" right           # re-position / replace the label of the previous element
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import List, Optional, Union

from .errors import CircuitError
from .symbols import KINDS, kind_help

DIRECTIONS = {
    "right": "right", "r": "right", "east": "right", "e": "right",
    "left": "left", "l": "left", "west": "left", "w": "left",
    "up": "up", "u": "up", "north": "up", "n": "up",
    "down": "down", "d": "down", "south": "down", "s": "down",
}
LABEL_POSITIONS = ("above", "below", "left", "right", "inside", "none")
_ANCHOR_RE = re.compile(r"^\(?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)?$")
_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-]*$")


@dataclass
class Title:
    text: str
    line: int = 0


@dataclass
class Element:
    kind: str
    id: Optional[str] = None
    value: Optional[str] = None
    direction: Optional[str] = None  # None = keep the current heading
    length: float = 1.0
    flip: bool = False      # swap the two ends (polarity)
    mirror: bool = False    # mirror across the axis (which side a transistor base / arrows are on)
    label: Optional[str] = None
    label_pos: Optional[str] = None
    show_id: bool = True
    line: int = 0


@dataclass
class Wire:
    direction: Optional[str] = None  # None = current heading
    units: float = 1.0
    line: int = 0


@dataclass
class WireTo:
    anchor: str
    vfirst: bool = False
    line: int = 0


@dataclass
class Node:
    name: str
    line: int = 0


@dataclass
class At:
    anchor: str
    line: int = 0


@dataclass
class Label:
    text: Optional[str]
    pos: Optional[str] = None
    line: int = 0


Statement = Union[Title, Element, Wire, WireTo, Node, At, Label]


@dataclass
class Program:
    statements: List[Statement] = field(default_factory=list)
    filename: str = "<string>"

    @property
    def title(self) -> Optional[str]:
        for s in self.statements:
            if isinstance(s, Title):
                return s.text
        return None

    @property
    def elements(self) -> List[Element]:
        return [s for s in self.statements if isinstance(s, Element)]


def _tokens(line: str, lineno: int, filename: str) -> List[str]:
    lex = shlex.shlex(line, posix=True)
    lex.whitespace_split = True
    lex.commenters = "#"
    try:
        return list(lex)
    except ValueError as e:
        raise CircuitError("cannot tokenize line: %s" % e, lineno, filename, hint="check for an unclosed quote")


def _number(tok: str, what: str, lineno: int, filename: str) -> float:
    try:
        v = float(tok)
    except ValueError:
        raise CircuitError("%s must be a number, got %r" % (what, tok), lineno, filename)
    if v <= 0:
        raise CircuitError("%s must be positive, got %r" % (what, tok), lineno, filename)
    return v


def is_anchor(tok: str) -> bool:
    return bool(_ANCHOR_RE.match(tok)) or bool(re.match(r"^[A-Za-z_][\w\-]*(\.[\w+\-]+)?$", tok))


def parse(source: str, filename: str = "<string>") -> Program:
    prog = Program(filename=filename)
    seen_ids = {}
    for lineno, raw in enumerate(source.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        head = stripped.split(None, 1)[0].lower()
        if head == "title":
            text = stripped[5:].split("#", 1)[0].strip().strip('"').strip("'")
            prog.statements.append(Title(text, lineno))
            continue
        toks = _tokens(stripped, lineno, filename)
        if not toks:
            continue
        kw = toks[0].lower()
        if kw == "wire":
            prog.statements.append(_parse_wire(toks[1:], lineno, filename))
        elif kw == "node":
            if len(toks) != 2 or not _ID_RE.match(toks[1]):
                raise CircuitError("usage: node NAME", lineno, filename)
            prog.statements.append(Node(toks[1], lineno))
        elif kw == "at":
            if len(toks) == 3 and _ANCHOR_RE.match(toks[1] + "," + toks[2]):
                toks = [toks[0], toks[1] + "," + toks[2]]
            if len(toks) != 2 or not is_anchor(toks[1]):
                raise CircuitError("usage: at NODE | at ID.pin | at X,Y", lineno, filename)
            prog.statements.append(At(toks[1], lineno))
        elif kw == "label":
            prog.statements.append(_parse_label(toks[1:], lineno, filename))
        else:
            el = _parse_element(toks, lineno, filename)
            if el.id:
                if el.id in seen_ids:
                    raise CircuitError("duplicate id %r (first used on line %d)" % (el.id, seen_ids[el.id]), lineno, filename)
                seen_ids[el.id] = lineno
            prog.statements.append(el)
    return prog


def _parse_wire(toks: List[str], lineno: int, filename: str) -> Union[Wire, WireTo]:
    if toks and toks[0].lower() == "to":
        rest = toks[1:]
        vfirst = False
        if rest and rest[-1].lower() in ("vfirst", "vertical-first", "v"):
            vfirst = True
            rest = rest[:-1]
        if len(rest) == 2 and _ANCHOR_RE.match(rest[0] + "," + rest[1]):
            rest = [rest[0] + "," + rest[1]]
        if len(rest) != 1 or not is_anchor(rest[0]):
            raise CircuitError("usage: wire to NODE | wire to ID.pin | wire to X,Y  [vfirst]", lineno, filename)
        return WireTo(rest[0], vfirst, lineno)
    w = Wire(line=lineno)
    for t in toks:
        tl = t.lower()
        if tl in DIRECTIONS and w.direction is None:
            w.direction = DIRECTIONS[tl]
        else:
            w.units = _number(t, "wire length", lineno, filename)
    return w


def _parse_label(toks: List[str], lineno: int, filename: str) -> Label:
    text = None
    pos = None
    for t in toks:
        if t.lower() in LABEL_POSITIONS and pos is None:
            pos = t.lower()
        elif text is None:
            text = t
        else:
            raise CircuitError("usage: label \"TEXT\" [above|below|left|right|inside|none]", lineno, filename)
    if text is None and pos is None:
        raise CircuitError("usage: label \"TEXT\" [above|below|left|right|inside|none]", lineno, filename)
    return Label(text, pos, lineno)


def _parse_element(toks: List[str], lineno: int, filename: str) -> Element:
    el = Element(kind="", line=lineno)
    i = 0
    if toks[0].endswith(":"):
        ident = toks[0][:-1]
        if not _ID_RE.match(ident):
            raise CircuitError("invalid id %r" % ident, lineno, filename, hint="ids look like R1, C_in, LED-2")
        if ident.lower() in ("wire", "node", "at", "label", "title"):
            raise CircuitError("%r is a keyword and cannot be an id" % ident, lineno, filename)
        el.id = ident
        i = 1
    elif len(toks) > 1 and toks[1] == ":":
        el.id = toks[0]
        i = 2
    if i >= len(toks):
        raise CircuitError("missing element kind after %r" % toks[0], lineno, filename, hint=kind_help())
    kind = toks[i].lower()
    if kind not in KINDS:
        close = sorted({KINDS[k].name for k in KINDS if k.startswith(kind[:3])})
        hint = "did you mean %s?" % ", ".join(close) if close else kind_help()
        raise CircuitError("unknown element kind %r" % toks[i], lineno, filename, hint=hint)
    el.kind = KINDS[kind].name
    i += 1
    rest = toks[i:]
    j = 0
    while j < len(rest):
        t = rest[j]
        tl = t.lower()
        if tl in DIRECTIONS:
            if el.direction is not None:
                raise CircuitError("two directions on one element (%s and %s)" % (el.direction, tl), lineno, filename)
            el.direction = DIRECTIONS[tl]
        elif tl in ("len", "length"):
            if j + 1 >= len(rest):
                raise CircuitError("`len` needs a number, e.g. `len 2`", lineno, filename)
            el.length = _number(rest[j + 1], "length", lineno, filename)
            j += 1
        elif tl.startswith("x") and len(tl) > 1 and re.match(r"^x\d+(\.\d+)?$", tl):
            el.length = float(tl[1:])
        elif tl == "flip":
            el.flip = True
        elif tl == "mirror":
            el.mirror = True
        elif tl == "noid":
            el.show_id = False
        elif tl == "label":
            if j + 1 >= len(rest):
                raise CircuitError("`label` needs text, e.g. label \"Vout\"", lineno, filename)
            el.label = rest[j + 1]
            j += 1
            if j + 1 < len(rest) and rest[j + 1].lower() in LABEL_POSITIONS:
                el.label_pos = rest[j + 1].lower()
                j += 1
        elif tl in LABEL_POSITIONS and el.label_pos is None and (el.value is not None or el.label is not None):
            el.label_pos = tl
        elif el.value is None:
            el.value = t
        else:
            raise CircuitError("unexpected token %r" % t, lineno, filename,
                               hint="syntax: [ID:] KIND [VALUE] [up|down|left|right] [len N] [flip] [mirror] [label \"text\" [above|below|left|right]] [noid]")
        j += 1
    return el
