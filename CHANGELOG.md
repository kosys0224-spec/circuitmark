# Changelog

## 0.1.0 - 2026-10-07

First release.

- Line-based language: elements with id/value/direction/length, `wire`, `wire to` (Manhattan), `node`, `at`, `label`, `title`.
- 23 element kinds: resistor, capacitor, inductor, diode, led, zener, schottky, battery, dc, ac, isource, switch, fuse, lamp, motor, speaker, box, npn, pnp, opamp, ground, terminal, dot.
- Automatic junction dots, dangling-connection warnings with line numbers, label placement that avoids neighbours.
- `circuitmark render`, `md` (inline SVG or files + image links, `--keep-source`), `check -W`, `symbols`; stdin/stdout.
- Themes: light, dark, blueprint, transparent, auto (currentColor).
- Python API: `render()`, `parse()`, `layout()`, `render_svg()`.
