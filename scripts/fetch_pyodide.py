"""Download the Pyodide runtime into `static/pyodide/`.

The app serves the Python runtime from its own origin rather than a CDN: it
loads faster, keeps working offline, and removes a third-party dependency from
the critical path. The download is ~5 MB compressed and is not committed to
git — this script fetches it, and `npm run build` runs it automatically.

    python scripts/fetch_pyodide.py [--force]
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

VERSION = "0.28.0"
URL = (
    f"https://github.com/pyodide/pyodide/releases/download/{VERSION}"
    f"/pyodide-core-{VERSION}.tar.bz2"
)

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "static" / "pyodide"

# Only the files the runtime actually needs at load time. The archive also
# carries .d.ts typings and an .mjs build we do not use.
KEEP = {
    "pyodide.js",
    "pyodide.asm.js",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
    "package.json",
}

STAMP = TARGET / ".version"


def already_present() -> bool:
    if not STAMP.exists() or STAMP.read_text().strip() != VERSION:
        return False
    return all((TARGET / name).exists() for name in KEEP)


def download(url: str, destination: Path) -> None:
    print(f"  descargando {url}")
    try:
        with urllib.request.urlopen(url, timeout=180) as response:
            total = int(response.headers.get("Content-Length") or 0)
            read = 0
            with destination.open("wb") as out:
                while True:
                    chunk = response.read(1 << 16)
                    if not chunk:
                        break
                    out.write(chunk)
                    read += len(chunk)
                    if total:
                        pct = read / total * 100
                        print(f"\r  {read / 1e6:5.1f} / {total / 1e6:.1f} MB ({pct:.0f}%)",
                              end="", flush=True)
            print()
    except (urllib.error.URLError, TimeoutError) as exc:
        sys.exit(
            f"\nerror: no se pudo descargar Pyodide ({exc}).\n"
            "       Verifique su conexión y reintente."
        )


def extract(archive: Path) -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    written = 0

    with tarfile.open(archive, "r:bz2") as tar:
        for member in tar.getmembers():
            name = Path(member.name).name
            if not member.isfile() or name not in KEEP:
                continue
            source = tar.extractfile(member)
            if source is None:
                continue
            destination = TARGET / name
            with destination.open("wb") as out:
                shutil.copyfileobj(source, out)
            written += destination.stat().st_size
            print(f"  {name:24} {destination.stat().st_size / 1e6:6.2f} MB")

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="volver a descargar aunque ya exista")
    args = parser.parse_args()

    if already_present() and not args.force:
        print(f"Pyodide {VERSION} ya está en static/pyodide/ — nada que hacer.")
        return

    print(f"Instalando Pyodide {VERSION}")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "pyodide.tar.bz2"
        download(URL, archive)
        total = extract(archive)

    missing = [name for name in KEEP if not (TARGET / name).exists()]
    if missing:
        sys.exit(f"error: faltan archivos tras la extracción: {', '.join(missing)}")

    STAMP.write_text(VERSION + "\n", encoding="utf-8")
    print(f"\nlisto — {total / 1e6:.1f} MB en static/pyodide/")


if __name__ == "__main__":
    main()
