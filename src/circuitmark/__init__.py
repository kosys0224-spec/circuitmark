"""circuitmark - write a circuit diagram as text, get an SVG.

    >>> from circuitmark import render
    >>> svg = render("V1: battery 9V up\\nR1: resistor 1k right\\nwire down 3\\nwire to V1.neg")
"""
from __future__ import annotations

__version__ = "0.1.0"

from .errors import CircuitError, Warning  # noqa: E402,F401
from .parser import parse  # noqa: E402,F401
from .layout import layout  # noqa: E402,F401
from .render import render_svg  # noqa: E402,F401


def render(source: str, theme: str = "light", scale: float = 1.0, filename: str = "<string>") -> str:
    """Parse, lay out and render `source` (circuitmark text) to an SVG string."""
    program = parse(source, filename=filename)
    drawing = layout(program)
    return render_svg(drawing, theme=theme, scale=scale)


__all__ = ["render", "render_svg", "parse", "layout", "CircuitError", "Warning", "__version__"]
