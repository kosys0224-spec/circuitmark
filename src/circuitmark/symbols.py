"""Schematic symbols drawn in a local frame: the element runs from (0,0) to (L,0) along +x.

Each symbol returns a list of primitives:
    ("path", "M ... ")                 stroked, not filled
    ("fill", "M ... Z")                filled with the stroke colour
    ("circle", cx, cy, r, filled)
    ("text", x, y, text)               a glyph that is part of the symbol (M for motor, + for a source)
The renderer rotates/mirrors them into place; text primitives are placed unrotated.

The grid unit is 20 px; a two-terminal element is 3 units (60 px) long with a 30 px body in the middle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

UNIT = 20.0        # one grid unit in px (a plain `wire` is one unit)
ELEMENT_LEN = 3.0  # default element length in units
BODY = 30.0        # body length in px

Prim = tuple


def _leads(x0: float, x1: float, L: float) -> List[Prim]:
    return [("path", "M0 0 H%g M%g 0 H%g" % (x0, x1, L))]


def _body(L: float) -> Tuple[float, float, float]:
    cx = L / 2
    return cx - BODY / 2, cx + BODY / 2, cx


def resistor(L: float) -> List[Prim]:
    x0, x1, _ = _body(L)
    pts = [(x0, 0)]
    for k in range(6):
        pts.append((x0 + 2.5 + 5 * k, -6 if k % 2 == 0 else 6))
    pts.append((x1, 0))
    d = "M" + " L".join("%g %g" % p for p in pts)
    return _leads(x0, x1, L) + [("path", d)]


def capacitor(L: float) -> List[Prim]:
    _, _, cx = _body(L)
    return _leads(cx - 3, cx + 3, L) + [("path", "M%g -10 V10 M%g -10 V10" % (cx - 3, cx + 3))]


def inductor(L: float) -> List[Prim]:
    x0, x1, _ = _body(L)
    d = "M%g 0" % x0 + " a3.75 3.75 0 0 1 7.5 0" * 4
    return _leads(x0, x1, L) + [("path", d)]


def diode(L: float, kind: str = "diode") -> List[Prim]:
    _, _, cx = _body(L)
    prims = _leads(cx - 7, cx + 7, L)
    prims.append(("fill", "M%g -7 L%g 0 L%g 7 Z" % (cx - 7, cx + 7, cx - 7)))
    if kind == "zener":
        prims.append(("path", "M%g -7 V7 M%g -7 l-3 0 M%g 7 l3 0" % (cx + 7, cx + 7, cx + 7)))
    elif kind == "schottky":
        prims.append(("path", "M%g -7 V7 M%g -7 l3 0 l0 2 M%g 7 l-3 0 l0 -2" % (cx + 7, cx + 7, cx + 7)))
    else:
        prims.append(("path", "M%g -7 V7" % (cx + 7)))
    if kind == "led":
        for dx in (-3, 4):
            prims.append(("path", "M%g -9 l5 -7" % (cx + dx)))
            prims.append(("fill", "M%g -16 l-1 3.5 l4 0 Z" % (cx + dx + 5)))
    return prims


def battery(L: float) -> List[Prim]:
    _, _, cx = _body(L)
    prims = _leads(cx - 9, cx + 9, L)
    # short thick plate = negative (start), long thin plate = positive (end); two cells
    prims.append(("path", "M%g -5 V5 M%g -10 V10 M%g -5 V5 M%g -10 V10" % (cx - 9, cx - 3, cx + 3, cx + 9)))
    return prims


def dc_source(L: float) -> List[Prim]:
    _, _, cx = _body(L)
    return _leads(cx - 12, cx + 12, L) + [("circle", cx, 0, 12, False),
                                          ("path", "M%g -2.5 V2.5 M%g 0 H%g M%g 0 H%g" % (cx + 5, cx + 2.5, cx + 7.5, cx - 7.5, cx - 2.5))]


def ac_source(L: float) -> List[Prim]:
    _, _, cx = _body(L)
    return _leads(cx - 12, cx + 12, L) + [("circle", cx, 0, 12, False),
                                          ("path", "M%g 0 q3.5 -8 7 0 t7 0" % (cx - 7))]


def current_source(L: float) -> List[Prim]:
    _, _, cx = _body(L)
    return _leads(cx - 12, cx + 12, L) + [("circle", cx, 0, 12, False), ("path", "M%g 0 H%g" % (cx - 7, cx + 4)),
                                          ("fill", "M%g 0 l-5 -3.5 l0 7 Z" % (cx + 8))]


def switch(L: float) -> List[Prim]:
    _, _, cx = _body(L)
    return _leads(cx - 12, cx + 12, L) + [("circle", cx - 12, 0, 2, False), ("circle", cx + 12, 0, 2, False),
                                          ("path", "M%g -1 L%g -10" % (cx - 10.5, cx + 11))]


def fuse(L: float) -> List[Prim]:
    x0, x1, _ = _body(L)
    return _leads(x0, x1, L) + [("path", "M%g -5 H%g V5 H%g Z M%g 0 H%g" % (x0 + 3, x1 - 3, x0 + 3, x0, x1))]


def lamp(L: float) -> List[Prim]:
    _, _, cx = _body(L)
    k = 10 * 0.7071
    return _leads(cx - 10, cx + 10, L) + [("circle", cx, 0, 10, False),
                                          ("path", "M%g %g L%g %g M%g %g L%g %g" % (cx - k, -k, cx + k, k, cx - k, k, cx + k, -k))]


def motor(L: float) -> List[Prim]:
    _, _, cx = _body(L)
    return _leads(cx - 12, cx + 12, L) + [("circle", cx, 0, 12, False), ("text", cx, 0, "M")]


def speaker(L: float) -> List[Prim]:
    _, _, cx = _body(L)
    return _leads(cx - 8, cx + 8, L) + [("path", "M%g -6 H%g V6 H%g Z M%g -6 L%g -14 V14 L%g 6" % (cx - 8, cx + 2, cx - 8, cx + 2, cx + 10, cx + 2))]


def box(L: float) -> List[Prim]:
    x0, x1, _ = _body(L)
    return _leads(x0, x1, L) + [("path", "M%g -10 H%g V10 H%g Z" % (x0, x1, x0))]


def ground(L: float) -> List[Prim]:
    return [("path", "M0 0 H10 M10 -10 V10 M14 -6 V6 M18 -2 V2")]


def terminal(L: float) -> List[Prim]:
    return [("path", "M0 0 H16"), ("circle", 20, 0, 4, False)]


def dot(L: float) -> List[Prim]:
    return [("circle", 0, 0, 3, True)]


def transistor(L: float, kind: str) -> List[Prim]:
    _, _, cx = _body(L)
    prims = [("path", "M0 0 H%g L%g -8 M%g -8 L%g 0 H%g" % (cx - 14, cx - 6, cx + 6, cx + 14, L)),
             ("path", "M%g -8 H%g" % (cx - 8, cx + 8)),           # base bar, on the -y side
             ("path", "M%g -8 V-20" % cx)]                         # base lead -> pin at (cx, -20)
    if kind == "npn":  # arrow on the emitter pointing away from the base (towards the start pin)
        prims.append(("fill", "M%g 0 l6.5 -1.5 l-2.5 -4.5 Z" % (cx - 13)))
    else:              # pnp: arrow on the emitter pointing into the base
        prims.append(("fill", "M%g -8 l-6.5 1.5 l2.5 4.5 Z" % (cx - 6.5)))
    return prims


def opamp(L: float) -> List[Prim]:
    # the element starts at the inverting input (0,0); in+ is at (0,20); the axis of the triangle is y=10 and
    # the output (the `end` pin, where the cursor continues) is at (L,10)
    cx = L / 2
    prims = [("path", "M%g -10 L%g 10 L%g 30 Z" % (cx - 15, cx + 15, cx - 15)),
             ("path", "M0 0 H%g M0 20 H%g M%g 10 H%g" % (cx - 15, cx - 15, cx + 15, L)),
             ("path", "M%g 0 h5 M%g 20 h5 M%g 17.5 v5" % (cx - 12, cx - 12, cx - 9.5))]
    return prims


@dataclass
class Kind:
    name: str
    draw: Callable[[float], List[Prim]]
    aliases: Tuple[str, ...] = ()
    terminal: bool = False               # one-pin element; the cursor does not advance
    length: float = ELEMENT_LEN          # default length in units
    pin_aliases: Dict[str, str] = field(default_factory=dict)
    extra_pins: Callable[[float], Dict[str, Tuple[float, float]]] = lambda L: {}
    value_inside: bool = False
    end_y: float = 0.0                   # local y of the `end` pin (0 for two-terminal parts)
    axis_y: float = 0.0                  # local y of the symbol's visual centre line
    extent: float = 15.0                 # label clearance from the axis (kept equal across kinds so labels line up)
    thickness: float = 10.0              # how far the drawn symbol really reaches from its axis (collision box)
    doc: str = ""


_POLAR = {"neg": "start", "pos": "end", "-": "start", "+": "end", "minus": "start", "plus": "end"}
_DIODE = {"anode": "start", "cathode": "end", "a": "start", "k": "end"}
_BJT = {"e": "start", "c": "end", "emitter": "start", "collector": "end", "b": "base"}
_OPAMP = {"out": "end", "o": "end"}

_KIND_LIST = [
    Kind("resistor", resistor, ("r", "res"), thickness=6, doc="zigzag resistor"),
    Kind("capacitor", capacitor, ("c", "cap"), thickness=10, doc="two plates"),
    Kind("inductor", inductor, ("l", "ind", "coil"), thickness=4, doc="four arcs"),
    Kind("diode", diode, ("d",), pin_aliases=_DIODE, thickness=7, doc="anode at start, cathode (bar) at end"),
    Kind("led", lambda L: diode(L, "led"), (), pin_aliases=_DIODE, extent=18.0, thickness=17, doc="diode with light arrows"),
    Kind("zener", lambda L: diode(L, "zener"), (), pin_aliases=_DIODE, thickness=8, doc="zener diode"),
    Kind("schottky", lambda L: diode(L, "schottky"), (), pin_aliases=_DIODE, thickness=8, doc="schottky diode"),
    Kind("battery", battery, ("bat", "cell"), pin_aliases=_POLAR, thickness=10, doc="negative (short plate) at start, positive at end"),
    Kind("dc", dc_source, ("vdc", "vsource", "source", "v"), pin_aliases=_POLAR, thickness=12, doc="DC voltage source, + at end"),
    Kind("ac", ac_source, ("vac", "sine"), pin_aliases=_POLAR, thickness=12, doc="AC voltage source"),
    Kind("isource", current_source, ("i", "idc", "current"), pin_aliases=_POLAR, thickness=12, doc="current source, arrow towards end"),
    Kind("switch", switch, ("sw", "s"), thickness=10, doc="open switch"),
    Kind("fuse", fuse, ("f",), thickness=5, doc="fuse"),
    Kind("lamp", lamp, ("bulb", "light"), thickness=10, doc="lamp (circle with X)"),
    Kind("motor", motor, ("m",), thickness=12, doc="motor (circle with M)"),
    Kind("speaker", speaker, ("spk", "buzzer"), thickness=14, doc="speaker / buzzer"),
    Kind("box", box, ("block", "ic", "generic"), value_inside=True, thickness=10, doc="generic rectangular block; the value is written inside"),
    Kind("npn", lambda L: transistor(L, "npn"), (), pin_aliases=_BJT,
         extra_pins=lambda L: {"base": (L / 2, -20)}, extent=20.0, thickness=20, doc="NPN: emitter at start, collector at end, base pin on the left side (use `mirror` for the right)"),
    Kind("pnp", lambda L: transistor(L, "pnp"), (), pin_aliases=_BJT,
         extra_pins=lambda L: {"base": (L / 2, -20)}, extent=20.0, thickness=20, doc="PNP: emitter at start, collector at end, base on the left side"),
    Kind("opamp", opamp, ("amp",), pin_aliases=_OPAMP, extent=25.0, thickness=20, end_y=10.0, axis_y=10.0,
         extra_pins=lambda L: {"in-": (0, 0), "in+": (0, 20), "inm": (0, 0), "inp": (0, 20)},
         doc="op-amp: starts at in- (= .start), .in+ one unit beside it, output (.out = .end) at the far end"),
    Kind("ground", ground, ("gnd", "earth"), terminal=True, length=1.0, extent=10.0, thickness=10, doc="ground symbol; the cursor stays where it was"),
    Kind("terminal", terminal, ("term", "port", "pin"), terminal=True, length=1.0, extent=4.0, thickness=4, doc="open terminal with a label (Vin, Vout...); cursor stays"),
    Kind("dot", dot, ("junction", "j"), terminal=True, length=0.0, extent=3.0, thickness=3, doc="junction dot at the current point"),
]

KINDS: Dict[str, Kind] = {}
for _k in _KIND_LIST:
    KINDS[_k.name] = _k
    for _a in _k.aliases:
        KINDS[_a] = _k


def kind_help() -> str:
    names = sorted({k.name for k in KINDS.values()})
    return "known kinds: " + ", ".join(names)


def kind_table() -> List[Tuple[str, str, str]]:
    seen = []
    for k in _KIND_LIST:
        seen.append((k.name, ", ".join(k.aliases), k.doc))
    return seen
