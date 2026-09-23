#!/usr/bin/env python3
"""Generate README-light.md from README.md.

    python3 scripts/build_light_readme.py

GitHub has no theme toggle, so the toggle is a pair of pages that link to each
other. The two must stay identical apart from the screenshot paths and the
toggle line, which is why the light page is generated rather than maintained by
hand: edit README.md, run this, commit both. CI regenerates it and fails on a
diff, so the pair cannot drift.

The dark-mode ``<source>`` inside the logo ``<picture>`` is deliberately left
alone. It points at docs/assets/, not docs/screenshots/, and it is the reader's
own browser preference that picks it, not the page.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "README.md"
OUT = ROOT / "README-light.md"

#: Every replacement has to fire at least once, so a renamed marker fails loudly
#: instead of quietly producing a light page identical to the dark one.
REQUIRED: list[tuple[str, str]] = [
    ("docs/screenshots/dark/", "docs/screenshots/light/"),
    (
        '<p><b>Dark mode</b> &middot; '
        '<a href="./README-light.md">View this page in light mode</a></p>',
        '<p><b>Light mode</b> &middot; '
        '<a href="./README.md">View this page in dark mode</a></p>',
    ),
]

HEADER = (
    "<!-- Generated from README.md by scripts/build_light_readme.py. "
    "Do not edit by hand. -->\n\n"
)


def main() -> int:
    """Write README-light.md, or say which marker went missing."""
    text = SRC.read_text(encoding="utf-8")
    for old, new in REQUIRED:
        if old not in text:
            print(f"README.md is missing the expected marker: {old}", file=sys.stderr)
            return 1
        text = text.replace(old, new)

    OUT.write_text(HEADER + text, encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} from {SRC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
