"""Download the web fonts into `static/fonts/` and emit `static/css/fonts.css`.

Self-hosting the fonts removes a third-party request from first paint, avoids
sending visitor IPs to a font CDN, and keeps the typography intact offline.
Only the latin and latin-ext subsets are kept — the app's UI is Spanish.

The downloads are not committed to git; `npm run build` runs this script.

    python scripts/fetch_fonts.py [--force]
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "static" / "fonts"
CSS_OUT = ROOT / "static" / "css" / "fonts.css"

GOOGLE_CSS = (
    "https://fonts.googleapis.com/css2"
    "?family=Instrument+Sans:ital,wght@0,400..700;1,400..700"
    "&family=JetBrains+Mono:wght@400..600"
    "&display=swap"
)

# Google serves woff2 only to browsers that advertise support.
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# The UI is Spanish; these two subsets cover it with room to spare.
WANTED_SUBSETS = {"latin", "latin-ext"}

STAMP = FONT_DIR / ".fetched"


def fetch(url: str, binary: bool = False) -> bytes | str:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        sys.exit(f"error: no se pudo descargar {url} ({exc})")
    return data if binary else data.decode("utf-8")


def parse_blocks(css: str) -> list[tuple[str, str]]:
    """Split the stylesheet into (subset-comment, @font-face block) pairs."""
    blocks: list[tuple[str, str]] = []
    subset = "latin"
    for chunk in re.split(r"(?=/\*)", css):
        comment = re.match(r"/\*\s*([\w-]+)\s*\*/", chunk.strip())
        if comment:
            subset = comment.group(1)
        for face in re.findall(r"@font-face\s*\{[^}]*\}", chunk):
            blocks.append((subset, face))
    return blocks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="volver a descargar")
    args = parser.parse_args()

    if STAMP.exists() and CSS_OUT.exists() and not args.force:
        print("Fuentes ya presentes en static/fonts/ — nada que hacer.")
        return

    print("Descargando fuentes")
    css = fetch(GOOGLE_CSS)

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    CSS_OUT.parent.mkdir(parents=True, exist_ok=True)

    rules: list[str] = []
    total = 0
    seen: set[str] = set()

    for subset, block in parse_blocks(css):
        if subset not in WANTED_SUBSETS:
            continue

        url_match = re.search(r"url\((https://[^)]+\.woff2)\)", block)
        family_match = re.search(r"font-family:\s*'([^']+)'", block)
        if not url_match or not family_match:
            continue

        url = url_match.group(1)
        family = family_match.group(1)
        italic = "font-style: italic" in block
        slug = family.lower().replace(" ", "-")
        name = f"{slug}-{subset}{'-italic' if italic else ''}.woff2"

        if name in seen:
            continue
        seen.add(name)

        destination = FONT_DIR / name
        if not destination.exists() or args.force:
            destination.write_bytes(fetch(url, binary=True))
        size = destination.stat().st_size
        total += size
        print(f"  {name:38} {size / 1024:6.1f} KB")

        # Rewrite the remote URL to the local one, keep everything else.
        rules.append(
            block.replace(url_match.group(0), f"url(../fonts/{name}) format('woff2')")
                 .replace("  ", "  ")
        )

    if not rules:
        sys.exit("error: no se encontró ningún @font-face utilizable")

    CSS_OUT.write_text(
        "/* Generado por scripts/fetch_fonts.py — no editar a mano. */\n\n"
        + "\n".join(rules)
        + "\n",
        encoding="utf-8",
    )

    STAMP.write_text("ok\n", encoding="utf-8")
    print(f"\nlisto — {len(rules)} @font-face, {total / 1024:.0f} KB")
    print(f"       {CSS_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
