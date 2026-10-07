# Security policy

circuitmark reads text files and writes SVG/Markdown files. It makes no network requests and executes nothing from its input. The SVG it writes contains only paths, circles, rects and text (no scripts, no external references), so it is safe to inline in pages.

Report security issues (crafted input that hangs or crashes the parser, path handling in `--svg-dir` / `--in-place`) through GitHub's private vulnerability reporting on this repository's Security tab. Acknowledgement within 7 days; only the latest release receives fixes.
