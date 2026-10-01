#!/usr/bin/env python3
"""Inline the design kit into an authored HTML file: replaces the /*@kit*/ marker with fonts + kit CSS.

usage: assemble_kit.py SRC.html OUT.html [--no-fonts]
Set <html data-theme=technical|copper|data|devotional> for a theme (default scholar); add open-question|open-quote|open-split to the first unit for an opening.
Author source-specific CSS after the marker (inside the same <style>) to retune tokens per source.
"""
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent / "assets" / "kit"
MARKER = "/*@kit*/"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    src, out = Path(args[0]), Path(args[1])
    html = src.read_text(encoding="utf-8")
    if html.count(MARKER) != 1:
        print(f"expected exactly one {MARKER} marker in {src}", file=sys.stderr)
        return 1
    css = (KIT / "kit.css").read_text(encoding="utf-8") + (KIT / "themes.css").read_text(encoding="utf-8")
    if "--no-fonts" not in sys.argv:
        css = (KIT / "fonts.css").read_text(encoding="utf-8") + css
    out.write_text(html.replace(MARKER, css), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
