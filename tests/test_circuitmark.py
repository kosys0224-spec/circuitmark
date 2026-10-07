import contextlib
import glob
import io
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

from circuitmark import CircuitError, layout, parse, render, render_svg
from circuitmark.cli import main
from circuitmark.markdown import convert
from circuitmark.parser import At, Element, Node, Title, Wire, WireTo
from circuitmark.symbols import KINDS, UNIT

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(os.path.dirname(HERE), "examples")

LOOP = """title loop
V1: battery 9V up
R1: resistor 1k right
wire down 3
wire to V1.neg
"""


def pins(src, ident):
    d = layout(parse(src))
    for e in d.elements:
        if e.element.id == ident:
            return e.pins
    raise KeyError(ident)


class ParserTests(unittest.TestCase):
    def test_statements(self):
        p = parse("# comment\ntitle My circuit  # trailing\nR1: resistor 10k right len 2\nwire up 2\nwire to R1.end vfirst\nnode a\nat a\n\n")
        kinds = [type(s) for s in p.statements]
        self.assertEqual(kinds, [Title, Element, Wire, WireTo, Node, At])
        self.assertEqual(p.title, "My circuit")
        el = p.statements[1]
        self.assertEqual((el.id, el.kind, el.value, el.direction, el.length), ("R1", "resistor", "10k", "right", 2.0))
        self.assertEqual((p.statements[2].direction, p.statements[2].units), ("up", 2.0))
        self.assertTrue(p.statements[3].vfirst)

    def test_aliases_and_modifiers(self):
        el = parse('D1: d "1N4148" d flip mirror noid label "fast" below').elements[0]
        self.assertEqual(el.kind, "diode")
        self.assertEqual(el.value, "1N4148")
        self.assertEqual(el.direction, "down")
        self.assertTrue(el.flip and el.mirror and not el.show_id)
        self.assertEqual((el.label, el.label_pos), ("fast", "below"))
        self.assertEqual(parse("cap 1u").elements[0].kind, "capacitor")
        self.assertEqual(parse("R1: r x2").elements[0].length, 2.0)

    def test_errors_have_lines_and_hints(self):
        with self.assertRaises(CircuitError) as cm:
            parse("R1: resistor 1k\nR2: resistr 2k")
        self.assertEqual(cm.exception.line, 2)
        self.assertIn("resistor", cm.exception.hint)
        with self.assertRaises(CircuitError) as cm:
            parse("R1: resistor\nR1: resistor")
        self.assertIn("duplicate", str(cm.exception))
        with self.assertRaises(CircuitError):
            parse('R1: resistor "unclosed')
        with self.assertRaises(CircuitError) as cm:
            parse("R1: resistor 1k 2k")
        self.assertIn("unexpected token", str(cm.exception))
        with self.assertRaises(CircuitError):
            parse("wire to")
        with self.assertRaises(CircuitError):
            parse("label")
        with self.assertRaises(CircuitError):
            parse("R1: resistor up down")

    def test_every_kind_parses_and_renders(self):
        for name in sorted({k.name for k in KINDS.values()}):
            svg = render("X1: %s 1 right\nwire right" % name)
            ET.fromstring(svg)


class LayoutTests(unittest.TestCase):
    def test_cursor_and_pins(self):
        d = layout(parse(LOOP))
        v1, r1 = d.elements
        self.assertEqual(v1.pins["start"], (0.0, 0.0))
        self.assertEqual(v1.pins["end"], (0.0, -60.0))
        self.assertEqual(v1.pins["neg"], (0.0, 0.0))
        self.assertEqual(v1.pins["pos"], (0.0, -60.0))
        self.assertEqual(r1.pins["start"], (0.0, -60.0))
        self.assertEqual(r1.pins["end"], (60.0, -60.0))
        # wire down 3 then Manhattan back to V1.neg: (60,-60)->(60,0)->(0,0)
        self.assertEqual([(w.a, w.b) for w in d.wires], [((60.0, -60.0), (60.0, 0.0)), ((60.0, 0.0), (0.0, 0.0))])
        self.assertEqual(d.warnings, [])
        self.assertEqual(d.dots, [])

    def test_flip_swaps_polarity_but_not_geometry(self):
        p = pins("V1: battery up flip", "V1")
        self.assertEqual(p["start"], (0.0, 0.0))
        self.assertEqual(p["pos"], (0.0, 0.0))
        self.assertEqual(p["neg"], (0.0, -60.0))
        p = pins("D1: diode right", "D1")
        self.assertEqual((p["anode"], p["cathode"]), ((0.0, 0.0), (60.0, 0.0)))

    def test_heading_continues(self):
        d = layout(parse("R1: resistor up\nR2: resistor\nwire\nwire left"))
        self.assertEqual(d.elements[1].direction, "up")
        self.assertEqual(d.elements[1].pins["end"], (0.0, -120.0))
        self.assertEqual(d.wires[0].b, (0.0, -140.0))
        self.assertEqual(d.wires[1].b, (-20.0, -140.0))

    def test_wire_to_vfirst_and_grid_coordinates(self):
        d = layout(parse("wire right 2\nwire to 0,2 vfirst\nat 5,5\nnode x\nwire to x"))
        self.assertEqual([(w.a, w.b) for w in d.wires][:2], [((0.0, 0.0), (40.0, 0.0)), ((40.0, 0.0), (40.0, 40.0))])
        self.assertEqual(d.wires[2].b, (0.0, 40.0))
        self.assertEqual(d.nodes["x"], (100.0, 100.0))
        self.assertTrue(any("zero length" in str(w) for w in d.warnings))

    def test_anchor_errors(self):
        with self.assertRaises(CircuitError) as cm:
            layout(parse("R1: resistor right\nwire to R1"))
        self.assertIn("two ends", str(cm.exception))
        with self.assertRaises(CircuitError) as cm:
            layout(parse("R1: resistor right\nwire to R1.foo"))
        self.assertIn("no pin", str(cm.exception))
        with self.assertRaises(CircuitError) as cm:
            layout(parse("wire to nowhere"))
        self.assertIn("unknown anchor", str(cm.exception))
        with self.assertRaises(CircuitError):
            layout(parse("label \"x\""))

    def test_junctions_and_dangling(self):
        # T: a wire ending in the middle of another wire
        d = layout(parse("wire right 4\nat 2,-2\nT1: terminal up\nwire down 2\nat 0,0\nwire down\nGND: ground down\nat 4,0\nwire down\nG2: ground down"))
        self.assertIn((40.0, 0.0), d.dots)
        self.assertEqual([w for w in d.warnings], [])
        d = layout(parse("R1: resistor right"))
        self.assertEqual(len(d.warnings), 2)
        self.assertIn("dangling", str(d.warnings[0]))
        self.assertEqual(d.warnings[0].line, 1)
        d = layout(parse("Vin: terminal left\nR1: resistor right\nGND: ground down"))
        self.assertEqual(d.warnings, [])
        d = layout(parse("wire right\nwire down\nwire left\nwire up"))
        self.assertEqual(d.warnings, [])
        self.assertEqual(d.dots, [])

    def test_three_terminal_parts(self):
        p = pins("Q1: npn up", "Q1")
        self.assertEqual(p["e"], (0.0, 0.0))
        self.assertEqual(p["c"], (0.0, -60.0))
        self.assertEqual(p["base"], (-20.0, -30.0))
        self.assertEqual(pins("Q1: npn up mirror", "Q1")["b"], (20.0, -30.0))
        p = pins("U1: opamp right", "U1")
        self.assertEqual((p["in-"], p["in+"], p["out"]), ((0.0, 0.0), (0.0, 20.0), (60.0, 10.0)))
        d = layout(parse("U1: opamp right\nwire right"))
        self.assertEqual(d.wires[0].a, (60.0, 10.0))

    def test_terminal_kinds_do_not_move_cursor(self):
        d = layout(parse("GND: ground down\nR1: resistor right"))
        self.assertEqual(d.elements[1].pins["start"], (0.0, 0.0))

    def test_labels(self):
        d = layout(parse("R1: resistor 10k right"))
        texts = {t.text: t for t in d.labels}
        self.assertEqual(set(texts), {"R1", "10k"})
        self.assertLess(texts["R1"].y, texts["10k"].y)  # id on top of the stack
        d = layout(parse("R1: resistor 10k right\nlabel \"ten k\" below"))
        texts = {t.text: t for t in d.labels}
        self.assertIn("ten k", texts)
        self.assertNotIn("10k", texts)
        self.assertGreater(texts["ten k"].y, 0)
        d = layout(parse("R1: resistor 10k right noid"))
        self.assertEqual([t.text for t in d.labels], ["10k"])
        d = layout(parse("U1: box \"NE555\" right"))
        inside = [t for t in d.labels if t.text == "NE555"][0]
        self.assertEqual((inside.x, inside.y), (30.0, 0.0))

    def test_label_avoids_neighbour(self):
        # R2's default (right) side is occupied by RL, so its labels move to the left
        with open(os.path.join(EXAMPLES, "divider.ckt")) as f:
            d = layout(parse(f.read()))
        r2 = {t.text: t for t in d.labels if t.text in ("R2",)}["R2"]
        self.assertLess(r2.x, 60.0)
        self.assertEqual(r2.anchor, "end")


class RenderTests(unittest.TestCase):
    def test_svg_is_well_formed(self):
        svg = render(LOOP)
        root = ET.fromstring(svg)
        self.assertTrue(root.tag.endswith("svg"))
        self.assertIn("viewBox", root.attrib)
        self.assertEqual(root.find("{http://www.w3.org/2000/svg}title").text, "loop")
        self.assertIn('data-id="R1"', svg)
        self.assertIn('class="element battery"', svg)

    def test_escaping(self):
        svg = render('R1: resistor "<1k & 2k>" right\nwire right\nwire left 4')
        ET.fromstring(svg)
        self.assertIn("&lt;1k &amp; 2k&gt;", svg)

    def test_themes_and_scale(self):
        light = ET.fromstring(render(LOOP))
        auto = ET.fromstring(render(LOOP, theme="auto"))
        self.assertEqual(light.find("{http://www.w3.org/2000/svg}rect").get("fill"), "#ffffff")
        self.assertIsNone(auto.find("{http://www.w3.org/2000/svg}rect"))
        self.assertIn("currentColor", render(LOOP, theme="auto"))
        w1 = float(light.get("width"))
        w2 = float(ET.fromstring(render(LOOP, scale=2)).get("width"))
        self.assertAlmostEqual(w2, 2 * w1)
        with self.assertRaises(ValueError):
            render_svg(layout(parse(LOOP)), theme="neon")

    def test_deterministic(self):
        self.assertEqual(render(LOOP), render(LOOP))


class MarkdownTests(unittest.TestCase):
    MD = "# Doc\n\nText.\n\n```circuit\ntitle Loop\n%s```\n\nAfter.\n\n- item\n\n  ```circuit\n  R1: resistor right\n  wire right\n  wire left 4\n  ```\n" % LOOP.split("\n", 1)[1]

    def test_inline(self):
        out, blocks = convert(self.MD, filename="doc.md")
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].title, "Loop")
        self.assertNotIn("```circuit", out)
        self.assertEqual(out.count("<svg"), 2)
        self.assertIn("\n  <svg", out)  # indentation preserved inside the list item
        self.assertEqual(blocks[0].warnings, [])
        self.assertEqual(blocks[0].start_line, 6)

    def test_files_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, blocks = convert(self.MD, filename="doc.md", svg_dir=os.path.join(tmp, "img"), link_prefix="img", keep_source=True)
            self.assertIn("![Loop](img/loop.svg)", out)
            self.assertIn("![circuit diagram](img/circuit-02.svg)", out)
            self.assertTrue(os.path.exists(os.path.join(tmp, "img", "loop.svg")))
            self.assertIn("<details><summary>circuit source</summary>", out)
            self.assertIn("```circuit\ntitle Loop\n", out)
        out2, _ = convert(self.MD, svg_dir="x", write_files=False)
        self.assertIn("![Loop](x/loop.svg)", out2)

    def test_error_line_is_relative_to_the_markdown_file(self):
        with self.assertRaises(CircuitError) as cm:
            convert("a\n\n```circuit\nR1: resistor\nR2: bogus\n```\n", filename="d.md")
        self.assertEqual(cm.exception.line, 5)
        self.assertEqual(cm.exception.filename, "d.md")

    def test_no_blocks(self):
        text = "nothing here\n```python\nprint(1)\n```\n"
        self.assertEqual(convert(text), (text, []))


class CliTests(unittest.TestCase):
    def run_cli(self, *argv, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            old = __import__("sys").stdin
            __import__("sys").stdin = io.StringIO(stdin)
            try:
                code = main(list(argv))
            finally:
                __import__("sys").stdin = old
        return code, out.getvalue(), err.getvalue()

    def test_render_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "a.ckt")
            with open(src, "w") as f:
                f.write(LOOP)
            code, out, err = self.run_cli("render", src)
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(os.path.join(tmp, "a.svg")))
            code, out, err = self.run_cli("render", src, src, "-o", os.path.join(tmp, "outdir"))
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(os.path.join(tmp, "outdir", "a.svg")))
            code, out, err = self.run_cli("check", src)
            self.assertEqual(code, 0)
            self.assertIn("ok", err)

    def test_stdin_stdout_and_warnings(self):
        code, out, err = self.run_cli("render", "-", stdin="R1: resistor right\n")
        self.assertEqual(code, 0)
        self.assertIn("<svg", out)
        self.assertIn("dangling", err)
        code, out, err = self.run_cli("render", "-", "-W", stdin="R1: resistor right\n")
        self.assertEqual(code, 1)
        code, out, err = self.run_cli("check", "-", "-W", "-q", stdin="R1: resistor right\n")
        self.assertEqual(code, 1)
        self.assertEqual(err, "")

    def test_errors(self):
        code, out, err = self.run_cli("render", "-", stdin="R1: resistr\n")
        self.assertEqual(code, 1)
        self.assertIn("<stdin>", err) if "<stdin>" in err else self.assertIn("error", err)
        code, out, err = self.run_cli("render", "/nonexistent/x.ckt")
        self.assertEqual(code, 2)
        code, out, err = self.run_cli()
        self.assertEqual(code, 2)

    def test_md_in_place_and_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = os.path.join(tmp, "r.md")
            with open(md, "w") as f:
                f.write("x\n\n```circuit\n%s```\n" % LOOP)
            code, out, err = self.run_cli("md", md, "-i", "--svg-dir", os.path.join(tmp, "svg"), "--link-prefix", "svg")
            self.assertEqual(code, 0)
            text = open(md).read()
            self.assertIn("![loop](svg/loop.svg)", text)
            self.assertTrue(os.path.exists(os.path.join(tmp, "svg", "loop.svg")))
            code, out, err = self.run_cli("check", md)
            self.assertEqual(code, 0)
        code, out, err = self.run_cli("symbols")
        self.assertEqual(code, 0)
        self.assertIn("resistor", out)
        self.assertIn("opamp", out)


class ExampleTests(unittest.TestCase):
    def test_examples_render_without_warnings(self):
        files = sorted(glob.glob(os.path.join(EXAMPLES, "*.ckt")))
        self.assertGreaterEqual(len(files), 5)
        for path in files:
            with open(path, encoding="utf-8") as f:
                d = layout(parse(f.read(), filename=path))
            self.assertEqual(d.warnings, [], path)
            ET.fromstring(render_svg(d))


if __name__ == "__main__":
    unittest.main()
