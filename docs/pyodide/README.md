# Vendored Pyodide

Subset of the Pyodide 0.27.7 distribution (https://github.com/pyodide/pyodide/releases/tag/0.27.7),
served with the website so that the in-browser solver does not depend on a CDN. Recreate it with
`tools/fetch_pyodide.sh`.

- Pyodide runtime (`pyodide.js`, `pyodide.asm.js`, `pyodide.asm.wasm`, `python_stdlib.zip`,
  `pyodide-lock.json`): Mozilla Public License 2.0; includes CPython (PSF licence).
- NumPy, SciPy, OpenBLAS, NetworkX wheels: BSD licences, as distributed by Pyodide.
