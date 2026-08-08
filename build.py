"""Build the static site into `dist/` for deployment.

Renders the Jinja templates with relative asset paths, then copies the
stylesheet, the JS and the Python engine. The output is a plain static
directory — no server required, which is what Netlify hosts.

    python build.py

Run `npm run build:css` first (or use `npm run build`, which does both).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from core import __version__

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

# Engine modules published for the browser runtime to import. Must match
# CORE_MODULES in static/js/app.js.
CORE_MODULES = [
    "__init__.py",
    "fmt.py",
    "dataset.py",
    "analysis.py",
    "charts.py",
    "sample.py",
    "api.py",
]

PAGES = {"index.html": "index.html"}


def rel_url(path: str) -> str:
    """Mirror of the `url()` helper in app.py, so both render identical markup."""
    return "/" + path.lstrip("/")


def render() -> None:
    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    env.globals.update(url=rel_url, version=__version__)

    for template_name, output_name in PAGES.items():
        html = env.get_template(template_name).render()
        target = DIST / output_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        print(f"  rendered {output_name}  ({len(html):,} bytes)")


def copy_tree(source: Path, destination: Path, label: str) -> None:
    """Copy a directory, skipping dotfiles used only as local build stamps."""
    if not source.exists():
        return
    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    total = 0
    for item in sorted(source.iterdir()):
        if not item.is_file() or item.name.startswith("."):
            continue
        shutil.copy2(item, destination / item.name)
        count += 1
        total += item.stat().st_size
    print(f"  copied {label}/ ({count} archivos, {total:,} bytes)")


def copy_assets() -> None:
    css = ROOT / "static" / "css" / "app.css"
    if not css.exists():
        sys.exit(
            "error: static/css/app.css no existe.\n"
            "       Ejecute primero: npm run build:css"
        )

    (DIST / "static" / "css").mkdir(parents=True, exist_ok=True)
    shutil.copy2(css, DIST / "static" / "css" / "app.css")
    print(f"  copied static/css/app.css  ({css.stat().st_size:,} bytes)")

    fonts_css = ROOT / "static" / "css" / "fonts.css"
    if not fonts_css.exists():
        sys.exit(
            "error: static/css/fonts.css no existe.\n"
            "       Ejecute primero: python scripts/fetch_fonts.py"
        )
    shutil.copy2(fonts_css, DIST / "static" / "css" / "fonts.css")
    print(f"  copied static/css/fonts.css  ({fonts_css.stat().st_size:,} bytes)")

    (DIST / "static" / "js").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "static" / "js" / "app.js", DIST / "static" / "js" / "app.js")
    print("  copied static/js/app.js")

    copy_tree(ROOT / "static" / "fonts", DIST / "static" / "fonts", "static/fonts")

    # The Pyodide runtime, served from our own origin rather than a CDN.
    runtime = ROOT / "static" / "pyodide"
    if not runtime.exists():
        sys.exit(
            "error: static/pyodide/ no existe.\n"
            "       Ejecute primero: python scripts/fetch_pyodide.py"
        )
    copy_tree(runtime, DIST / "static" / "pyodide", "static/pyodide")

    favicon = ROOT / "static" / "favicon.svg"
    if favicon.exists():
        shutil.copy2(favicon, DIST / "static" / "favicon.svg")
        print("  copied static/favicon.svg")

    # The Python engine, fetched at runtime by the Pyodide bridge.
    (DIST / "core").mkdir(parents=True, exist_ok=True)
    total = 0
    for name in CORE_MODULES:
        source = ROOT / "core" / name
        if not source.exists():
            sys.exit(f"error: falta core/{name}")
        shutil.copy2(source, DIST / "core" / name)
        total += source.stat().st_size
    print(f"  copied core/ ({len(CORE_MODULES)} módulos, {total:,} bytes)")

    # The sample tables are also embedded in core/sample.py; these copies exist
    # so the CSVs can be linked and re-uploaded as ordinary files.
    copy_tree(ROOT / "sample_data", DIST / "sample_data", "sample_data")


def write_headers() -> None:
    """Netlify `_headers`: long-lived caching for the engine, none for HTML."""
    (DIST / "_headers").write_text(
        "\n".join([
            "/*",
            "  X-Content-Type-Options: nosniff",
            "  Referrer-Policy: strict-origin-when-cross-origin",
            "",
            "/core/*",
            "  Content-Type: text/x-python; charset=utf-8",
            "  Cache-Control: public, max-age=300",
            "",
            "/static/*",
            "  Cache-Control: public, max-age=3600",
            "",
            "/index.html",
            "  Cache-Control: public, max-age=0, must-revalidate",
            "",
        ]),
        encoding="utf-8",
    )
    print("  wrote _headers")


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    print("building dist/")
    render()
    copy_assets()
    write_headers()

    files = sum(1 for p in DIST.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"\ndone — {files} archivos, {size:,} bytes en dist/")


if __name__ == "__main__":
    main()
