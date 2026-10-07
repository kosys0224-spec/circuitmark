"""Walk the statements with a cursor and produce absolute geometry (a `Drawing`)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .errors import CircuitError, Warning
from .parser import At, Element, Label, Node, Program, Title, Wire, WireTo, _ANCHOR_RE
from .symbols import KINDS, UNIT, Kind

Point = Tuple[float, float]

VEC = {"right": (1.0, 0.0), "down": (0.0, 1.0), "left": (-1.0, 0.0), "up": (0.0, -1.0)}
ANGLE = {"right": 0, "down": 90, "left": 180, "up": 270}
FONT = 12.0
CHAR_W = 6.8  # average glyph advance at 12 px for the bbox estimate


def _r(v: float) -> float:
    return round(v, 3) + 0.0


def rp(p: Point) -> Point:
    return (_r(p[0]), _r(p[1]))


@dataclass
class TextLabel:
    text: str
    x: float
    y: float
    anchor: str = "middle"      # start | middle | end
    baseline: str = "middle"    # SVG dominant-baseline
    cls: str = "value"          # id | value | title | symbol
    size: float = FONT
    owner: int = -1             # id() of the Placed element the label belongs to

    def bbox(self) -> Tuple[float, float, float, float]:
        w = len(self.text) * CHAR_W * (self.size / FONT)
        h = self.size
        if self.anchor == "start":
            x0 = self.x
        elif self.anchor == "end":
            x0 = self.x - w
        else:
            x0 = self.x - w / 2
        if self.baseline == "hanging":
            y0 = self.y
        elif self.baseline == "alphabetic":
            y0 = self.y - h
        else:
            y0 = self.y - h / 2
        return (x0, y0, x0 + w, y0 + h)


@dataclass
class Placed:
    element: Element
    kind: Kind
    x: float
    y: float
    direction: str
    length_px: float
    pins: Dict[str, Point] = field(default_factory=dict)

    @property
    def angle(self) -> int:
        return ANGLE[self.direction]

    def transform(self) -> str:
        parts = ["translate(%g %g)" % (_r(self.x), _r(self.y))]
        if self.angle:
            parts.append("rotate(%d)" % self.angle)
        if self.element.flip:
            parts.append("translate(%g 0) scale(-1 1)" % _r(self.length_px))
        if self.element.mirror:
            parts.append("scale(1 -1)")
        return " ".join(parts)

    def to_global(self, px: float, py: float, flip: Optional[bool] = None, mirror: Optional[bool] = None) -> Point:
        flip = self.element.flip if flip is None else flip
        mirror = self.element.mirror if mirror is None else mirror
        if flip:
            px = self.length_px - px
        if mirror:
            py = -py
        a = math.radians(self.angle)
        c, s = round(math.cos(a)), round(math.sin(a))
        return rp((self.x + px * c - py * s, self.y + px * s + py * c))

    @property
    def center(self) -> Point:
        return self.to_global(self.length_px / 2, self.kind.axis_y, flip=False)

    @property
    def end(self) -> Point:
        return self.to_global(self.length_px, self.kind.end_y, flip=False)


@dataclass
class Segment:
    a: Point
    b: Point
    line: int = 0


@dataclass
class Drawing:
    title: Optional[str] = None
    elements: List[Placed] = field(default_factory=list)
    wires: List[Segment] = field(default_factory=list)
    nodes: Dict[str, Point] = field(default_factory=dict)
    dots: List[Point] = field(default_factory=list)
    labels: List[TextLabel] = field(default_factory=list)
    warnings: List[Warning] = field(default_factory=list)
    filename: str = "<string>"

    def bbox(self) -> Tuple[float, float, float, float]:
        xs: List[float] = []
        ys: List[float] = []
        for e in self.elements:
            h = 24.0
            for px, py in ((0, -h), (0, h), (e.length_px, -h), (e.length_px, h)):
                gx, gy = e.to_global(px, py, flip=False, mirror=False)
                xs.append(gx)
                ys.append(gy)
            for p in e.pins.values():
                xs.append(p[0])
                ys.append(p[1])
        for w in self.wires:
            xs += [w.a[0], w.b[0]]
            ys += [w.a[1], w.b[1]]
        for d in self.dots:
            xs.append(d[0])
            ys.append(d[1])
        for t in self.labels:
            x0, y0, x1, y1 = t.bbox()
            xs += [x0, x1]
            ys += [y0, y1]
        if not xs:
            return (0.0, 0.0, 2 * UNIT, 2 * UNIT)
        return (min(xs), min(ys), max(xs), max(ys))


class _Cursor:
    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self.heading = "right"

    @property
    def pos(self) -> Point:
        return rp((self.x, self.y))


def layout(prog: Program) -> Drawing:
    d = Drawing(title=prog.title, filename=prog.filename)
    cur = _Cursor()
    by_id: Dict[str, Placed] = {}
    conn: Dict[Point, int] = {}
    conn_line: Dict[Point, int] = {}
    terminal_points: set = set()
    last_element: Optional[Placed] = None

    def touch(p: Point, line: int, n: int = 1) -> None:
        p = rp(p)
        conn[p] = conn.get(p, 0) + n
        conn_line.setdefault(p, line)

    def resolve(anchor: str, line: int) -> Point:
        m = _ANCHOR_RE.match(anchor)
        if m:
            return rp((float(m.group(1)) * UNIT, float(m.group(2)) * UNIT))
        if anchor in d.nodes:
            return d.nodes[anchor]
        ident, _, pin = anchor.partition(".")
        if ident not in by_id:
            known = sorted(list(d.nodes) + list(by_id))
            raise CircuitError("unknown anchor %r" % anchor, line, prog.filename,
                               hint=("known names: " + ", ".join(known)) if known else "define a node with `node NAME` or give the element an id first")
        pl = by_id[ident]
        if not pin:
            if pl.kind.terminal:
                return pl.pins["start"]
            raise CircuitError("%r has two ends; use %s.start / %s.end (or .1 / .2, .pos / .neg, .anode / .cathode ...)"
                               % (ident, ident, ident), line, prog.filename)
        key = pl.kind.pin_aliases.get(pin, pin)
        key = {"1": "start", "2": "end", "a": key if key in pl.pins else "start", "b": "end", "s": "start", "e": key if key in pl.pins else "end"}.get(key, key)
        if key not in pl.pins:
            raise CircuitError("%r has no pin %r" % (ident, pin), line, prog.filename,
                               hint="pins of %s: %s" % (ident, ", ".join(sorted(pl.pins))))
        return pl.pins[key]

    for st in prog.statements:
        if isinstance(st, Title):
            continue
        if isinstance(st, Node):
            if st.name in d.nodes and d.nodes[st.name] != cur.pos:
                d.warnings.append(Warning("node %r redefined at a different point" % st.name, st.line, prog.filename))
            d.nodes[st.name] = cur.pos
            continue
        if isinstance(st, At):
            p = resolve(st.anchor, st.line)
            cur.x, cur.y = p
            continue
        if isinstance(st, Wire):
            direction = st.direction or cur.heading
            vx, vy = VEC[direction]
            a = cur.pos
            cur.x += vx * st.units * UNIT
            cur.y += vy * st.units * UNIT
            cur.heading = direction
            d.wires.append(Segment(a, cur.pos, st.line))
            touch(a, st.line)
            touch(cur.pos, st.line)
            continue
        if isinstance(st, WireTo):
            target = resolve(st.anchor, st.line)
            a = cur.pos
            if a == target:
                d.warnings.append(Warning("wire to %s has zero length" % st.anchor, st.line, prog.filename))
                continue
            corner = (a[0], target[1]) if st.vfirst else (target[0], a[1])
            corner = rp(corner)
            pts = [a, corner, target] if corner not in (a, target) else [a, target]
            for p, q in zip(pts, pts[1:]):
                d.wires.append(Segment(p, q, st.line))
            touch(a, st.line)
            touch(target, st.line)
            last = pts[-2], pts[-1]
            dx, dy = last[1][0] - last[0][0], last[1][1] - last[0][1]
            cur.heading = ("right" if dx > 0 else "left") if abs(dx) > abs(dy) else ("down" if dy > 0 else "up")
            cur.x, cur.y = target
            continue
        if isinstance(st, Label):
            if last_element is None:
                raise CircuitError("`label` must follow an element", st.line, prog.filename)
            if st.text is not None:
                last_element.element.label = st.text
            if st.pos is not None:
                last_element.element.label_pos = st.pos
            continue
        if isinstance(st, Element):
            kind = KINDS[st.kind]
            direction = st.direction or cur.heading
            L = (kind.length if kind.length else 0.0) * st.length * UNIT
            pl = Placed(st, kind, cur.x, cur.y, direction, L)
            # geometric pins (unaffected by flip/mirror)
            pl.pins["start"] = pl.to_global(0, 0, flip=False, mirror=False)
            if not kind.terminal:
                pl.pins["end"] = pl.end
            # electrical pins (follow flip/mirror)
            for name, (px, py) in kind.extra_pins(L).items():
                pl.pins[name] = pl.to_global(px, py)
            for alias, base in kind.pin_aliases.items():
                if base in ("start", "end"):
                    pl.pins[alias] = pl.to_global(0, 0) if base == "start" else pl.to_global(L, kind.end_y)
                elif base in pl.pins:
                    pl.pins[alias] = pl.pins[base]
            d.elements.append(pl)
            if st.id:
                by_id[st.id] = pl
            if kind.name != "dot":
                for p in sorted({p for n, p in pl.pins.items() if n in ("start", "end") or n in kind.extra_pins(L)}):
                    touch(p, st.line)
                    if kind.terminal:
                        terminal_points.add(p)
            if kind.name == "dot":
                d.dots.append(pl.pins["start"])
            last_element = pl
            cur.heading = direction
            if not kind.terminal:
                cur.x, cur.y = pl.pins["end"]
            continue
        raise CircuitError("unsupported statement %r" % (st,), getattr(st, "line", 0), prog.filename)

    # T-junctions: an endpoint resting on the interior of a segment joins that segment (2 more connections)
    for p in list(conn):
        for seg in d.wires:
            if _interior(p, seg):
                conn[p] += 2
                break
    for p, n in conn.items():
        if n >= 3 and p not in d.dots:
            d.dots.append(p)
        elif n == 1 and p not in terminal_points:
            d.warnings.append(Warning("dangling connection at grid (%g, %g); add a wire, a `terminal` or a `ground`"
                                      % (p[0] / UNIT, p[1] / UNIT), conn_line.get(p, 0), prog.filename))
    for pl in d.elements:
        _auto_labels(d, pl)
    if d.title:
        x0, y0, _, _ = d.bbox()
        d.labels.insert(0, TextLabel(d.title, x0, y0 - 14, "start", "alphabetic", "title", 14.0))
    return d


def _interior(p: Point, seg: Segment) -> bool:
    (ax, ay), (bx, by) = seg.a, seg.b
    if ax == bx and p[0] == ax:
        lo, hi = sorted((ay, by))
        return lo < p[1] < hi
    if ay == by and p[1] == ay:
        lo, hi = sorted((ax, bx))
        return lo < p[0] < hi
    return False


def _place_text(pl: Placed, text: str, side: str, cls: str, slot: int = 0, nslots: int = 1) -> TextLabel:
    """Put `text` beside the element on `side` (above/below/left/right/inside/beyond)."""
    t = _place_text_raw(pl, text, side, cls, slot, nslots)
    t.owner = id(pl)
    return t


def _place_text_raw(pl: Placed, text: str, side: str, cls: str, slot: int = 0, nslots: int = 1) -> TextLabel:
    """slot/nslots stack several labels on the same side (0 = first line)."""
    cx, cy = pl.center
    horizontal = pl.direction in ("left", "right")
    off = pl.kind.extent + 5  # half body (or the widest part of the symbol) + gap
    line = 14.0
    if side == "inside":
        return TextLabel(text, cx, cy, "middle", "middle", cls)
    if side == "beyond":  # terminals: past the end of the symbol, in the drawing direction
        vx, vy = VEC[pl.direction]
        ex, ey = pl.to_global(28, 0, flip=False, mirror=False)
        if vx > 0:
            return TextLabel(text, ex, ey, "start", "middle", cls)
        if vx < 0:
            return TextLabel(text, ex, ey, "end", "middle", cls)
        return TextLabel(text, ex, ey + (8 if vy > 0 else -8), "middle", "hanging" if vy > 0 else "alphabetic", cls)
    if side in ("above", "below"):
        # lines stack away from the element: slot 0 is nearest
        gap = off + (0 if horizontal else 14)
        if side == "above":
            return TextLabel(text, cx, cy - gap - (nslots - 1 - slot) * line, "middle", "alphabetic", cls)
        return TextLabel(text, cx, cy + gap + slot * line, "middle", "hanging", cls)
    # left / right: lines are centred vertically on the element
    gap = off + (0 if not horizontal else 10)
    y = cy + (slot - (nslots - 1) / 2.0) * line
    if side == "left":
        return TextLabel(text, cx - gap, y, "end", "middle", cls)
    return TextLabel(text, cx + gap, y, "start", "middle", cls)


def _overlaps(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float], pad: float = 1.0) -> bool:
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0] or a[3] + pad <= b[1] or b[3] + pad <= a[1])


def _obstacles(d: Drawing, pl: Placed) -> List[Tuple[float, float, float, float]]:
    boxes = [t.bbox() for t in d.labels if t.owner != id(pl)]
    for w in d.wires:
        boxes.append((min(w.a[0], w.b[0]) - 1, min(w.a[1], w.b[1]) - 1, max(w.a[0], w.b[0]) + 1, max(w.a[1], w.b[1]) + 1))
    for other in d.elements:
        if other is pl or other.kind.name == "dot":
            continue
        cx, cy = other.center
        half = other.length_px / 2 if not other.kind.terminal else 12
        ext = other.kind.thickness
        if other.direction in ("left", "right"):
            boxes.append((cx - half, cy - ext, cx + half, cy + ext))
        else:
            boxes.append((cx - ext, cy - half, cx + ext, cy + half))
    return boxes


def _opposite(side: str) -> str:
    return {"above": "below", "below": "above", "left": "right", "right": "left"}.get(side, side)


def _stack(d: Drawing, pl: Placed, items: List[Tuple[str, str]], side: str, fixed: bool) -> None:
    """Place `items` [(text, cls), ...] stacked on `side`; if they collide, try the opposite side."""
    obstacles = _obstacles(d, pl)
    choice = None
    for s in ([side] if fixed else [side, _opposite(side)]):
        labels = [_place_text(pl, text, s, cls, i, len(items)) for i, (text, cls) in enumerate(items)]
        if not any(_overlaps(t.bbox(), ob) for t in labels for ob in obstacles):
            choice = labels
            break
        if choice is None:
            choice = labels  # keep the first attempt as the fallback
    d.labels.extend(choice)


def _auto_labels(d: Drawing, pl: Placed) -> None:
    el = pl.element
    kind = pl.kind
    horizontal = pl.direction in ("left", "right")
    default_side = "above" if horizontal else "right"
    value_text = el.label if el.label is not None else el.value
    if kind.name == "dot":
        if value_text:
            _stack(d, pl, [(value_text, "value")], el.label_pos or "above", el.label_pos is not None)
        return
    if kind.name == "terminal":
        text = value_text or (el.id if el.show_id else None)
        if text and el.label_pos != "none":
            side = el.label_pos if el.label_pos not in (None, "inside") else "beyond"
            d.labels.append(_place_text(pl, text, side, "id"))
        return
    if kind.name == "ground":
        if value_text and el.label_pos != "none":
            d.labels.append(_place_text(pl, value_text, el.label_pos or "beyond", "value"))
        return
    show_id = bool(el.id) and el.show_id
    show_value = value_text is not None and el.label_pos != "none"
    if kind.value_inside and show_value and el.label_pos in (None, "inside"):
        d.labels.append(_place_text(pl, value_text, "inside", "value"))
        if show_id:
            _stack(d, pl, [(el.id, "id")], default_side, False)
        return
    items: List[Tuple[str, str]] = []
    if show_id:
        items.append((el.id, "id"))
    if show_value:
        items.append((value_text, "value"))
    if not items:
        return
    if el.label_pos and el.label_pos != "inside" and show_value:
        if show_id and el.label_pos != default_side:
            _stack(d, pl, [(el.id, "id")], default_side, False)
            _stack(d, pl, [(value_text, "value")], el.label_pos, True)
        else:
            _stack(d, pl, items, el.label_pos, True)
        return
    _stack(d, pl, items, default_side, False)
