"""Drawing -> SVG string."""
from __future__ import annotations

from typing import Dict, List
from xml.sax.saxutils import escape

from .layout import Drawing, TextLabel, _r

THEMES: Dict[str, Dict[str, str]] = {
    "light": {"stroke": "#1a1a1a", "text": "#1a1a1a", "id": "#1a1a1a", "value": "#4a4a4a", "bg": "#ffffff"},
    "dark": {"stroke": "#e6e6e6", "text": "#e6e6e6", "id": "#e6e6e6", "value": "#b8b8b8", "bg": "#0d1117"},
    "blueprint": {"stroke": "#dbe9ff", "text": "#ffffff", "id": "#ffffff", "value": "#bcd3ff", "bg": "#1f4e9c"},
    "transparent": {"stroke": "#1a1a1a", "text": "#1a1a1a", "id": "#1a1a1a", "value": "#4a4a4a", "bg": "none"},
    "auto": {"stroke": "currentColor", "text": "currentColor", "id": "currentColor", "value": "currentColor", "bg": "none"},
}
PAD = 16.0
FONT_FAMILY = "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"


def _fmt(v: float) -> str:
    return ("%.3f" % v).rstrip("0").rstrip(".") if v != int(v) else str(int(v))


def render_svg(d: Drawing, theme: str = "light", scale: float = 1.0, stroke_width: float = 2.0) -> str:
    if theme not in THEMES:
        raise ValueError("unknown theme %r (known: %s)" % (theme, ", ".join(sorted(THEMES))))
    th = THEMES[theme]
    x0, y0, x1, y1 = d.bbox()
    x0, y0, x1, y1 = x0 - PAD, y0 - PAD, x1 + PAD, y1 + PAD
    w, h = x1 - x0, y1 - y0
    out: List[str] = []
    out.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="%s %s %s %s" width="%s" height="%s" '
               'font-family="%s" font-size="12" role="img" data-generator="circuitmark">'
               % (_fmt(x0), _fmt(y0), _fmt(w), _fmt(h), _fmt(w * scale), _fmt(h * scale), FONT_FAMILY))
    if d.title:
        out.append("<title>%s</title>" % escape(d.title))
    if th["bg"] != "none":
        out.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s"/>' % (_fmt(x0), _fmt(y0), _fmt(w), _fmt(h), th["bg"]))
    out.append('<g fill="none" stroke="%s" stroke-width="%s" stroke-linecap="round" stroke-linejoin="round">'
               % (th["stroke"], _fmt(stroke_width)))
    # wires
    if d.wires:
        path = " ".join("M%s %s L%s %s" % (_fmt(s.a[0]), _fmt(s.a[1]), _fmt(s.b[0]), _fmt(s.b[1])) for s in d.wires)
        out.append('<path class="wire" d="%s"/>' % path)
    # elements
    symbol_texts: List[TextLabel] = []
    for pl in d.elements:
        attrs = ' class="element %s"' % pl.kind.name
        if pl.element.id:
            attrs += ' data-id="%s"' % escape(pl.element.id, {'"': "&quot;"})
        out.append("<g%s transform=\"%s\">" % (attrs, pl.transform()))
        for prim in pl.kind.draw(pl.length_px):
            if prim[0] == "path":
                out.append('<path d="%s"/>' % prim[1])
            elif prim[0] == "fill":
                out.append('<path d="%s" fill="%s" stroke="none"/>' % (prim[1], th["stroke"]))
            elif prim[0] == "circle":
                _, cx, cy, r, filled = prim
                out.append('<circle cx="%s" cy="%s" r="%s"%s/>' % (_fmt(cx), _fmt(cy), _fmt(r),
                                                                   ' fill="%s" stroke="none"' % th["stroke"] if filled else ""))
            elif prim[0] == "text":
                gx, gy = pl.to_global(prim[1], prim[2])
                symbol_texts.append(TextLabel(prim[3], gx, gy, "middle", "central", "symbol"))
        out.append("</g>")
    for p in d.dots:
        out.append('<circle class="junction" cx="%s" cy="%s" r="3" fill="%s" stroke="none"/>' % (_fmt(p[0]), _fmt(p[1]), th["stroke"]))
    out.append("</g>")
    # text
    for t in d.labels + symbol_texts:
        color = th["value"] if t.cls == "value" else th["text"]
        weight = ' font-weight="600"' if t.cls in ("id", "title") else ""
        size = ' font-size="%s"' % _fmt(t.size) if t.size != 12 else ""
        out.append('<text class="%s" x="%s" y="%s" text-anchor="%s" dominant-baseline="%s" fill="%s"%s%s>%s</text>'
                   % (t.cls, _fmt(_r(t.x)), _fmt(_r(t.y)), t.anchor, t.baseline, color, weight, size, escape(t.text)))
    out.append("</svg>")
    return "\n".join(out) + "\n"
