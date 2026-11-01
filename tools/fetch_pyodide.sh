#!/usr/bin/env bash
# Vendors the part of Pyodide the website needs into docs/pyodide (about 37 MB):
# the Python runtime plus the NumPy, SciPy, OpenBLAS and NetworkX packages.
set -euo pipefail
VERSION="${1:-0.27.7}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
curl -sSL -o "$TMP/p.tar.bz2" "https://github.com/pyodide/pyodide/releases/download/$VERSION/pyodide-$VERSION.tar.bz2"
tar xjf "$TMP/p.tar.bz2" -C "$TMP"
SRC="$TMP/pyodide"
DST="$ROOT/docs/pyodide"
rm -rf "$DST" && mkdir -p "$DST"
cp "$SRC"/{pyodide.js,pyodide.asm.js,pyodide.asm.wasm,python_stdlib.zip,pyodide-lock.json} "$DST"/
for pkg in numpy scipy openblas networkx; do
  f=$(python3 -c "import json,sys; print(json.load(open('$SRC/pyodide-lock.json'))['packages']['$pkg']['file_name'])")
  cp "$SRC/$f" "$DST/"
done
rm -rf "$TMP"
cp "$ROOT/tools/pyodide-README.md" "$DST/README.md"
du -sh "$DST"
