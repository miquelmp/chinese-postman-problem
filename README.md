# The Chinese Postman Problem — 1997 and 2026

The shortest closed walk that covers every street of a network. This repository revisits a 1997
final-year engineering project (Miquel Monserrat Pons, ETSEIB, supervised by Ramón Companys
Pascual) with thirty years of algorithmic progress.

**Website: https://miquelmp.github.io/chinese-postman-problem/**


- **Website** (`docs/`): the story, both reports, and a solver that runs in your browser.
- **Python package** `cartero`: undirected, directed and mixed Chinese Postman solvers, all with
  proven optimality or a certified gap.
- **Reports** (`report/`): the 2026 revision (Markdown and PDF) and the original 1997 report (PDF, Spanish).
- **Data and results**: 92 classical benchmark road networks and every result file behind the report.

## What the solver does

| Network | Method | Guarantee |
|---|---|---|
| Two-way streets | Shortest paths + minimum-weight perfect matching (Edmonds' blossom) + Hierholzer | Optimal, polynomial time |
| One-way streets | Minimum-cost flow + Hierholzer | Optimal, polynomial time |
| One-way and two-way mixed (NP-hard) | Heuristic, then branch-and-cut (HiGHS) | Optimal, or within a certified gap at the time limit |

## Install and use

```bash
pip install -e ".[test]"
pytest -q                            # 115 tests (170 with the optional Blossom V library)
```

```python
from cartero import read_gra, solve_undirected
sol = solve_undirected(read_gra("examples/pfc_1997.gra"), start=1)
print(sol.summary())                 # total 63 = 54 + 9, as in the 1997 report

from cartero.mixed import city_grid, solve_mixed
M = city_grid(20, 20, seed=0)        # whole streets one-way with probability 0.6
sol = solve_mixed(M, time_limit=300) # heuristic first, then branch-and-cut while it pays
print(sol.total_cost, sol.optimal, sol.info["gap_pct"])
```

`solve_mixed` returns the best tour found together with a proven lower bound. Pass `gap_tol=0.005`
to stop as soon as the tour is certified within 0.5% of the optimum.

## Layout

| Path | Contents |
|---|---|
| `cartero/cpp.py` | Undirected CPP (Edmonds' method) and directed CPP (minimum-cost flow) |
| `cartero/mixed.py` | Mixed CPP: bounds, exact branch-and-cut, heuristic with local search, combined `solve_mixed` |
| `cartero/euler.py` | Hierholzer's algorithm for directed and undirected multigraphs |
| `cartero/fast.py` | Optional fast backend: SciPy Dijkstra + Blossom V with dual pricing |
| `cartero/web.py` | JSON entry points used by the website's exact proof (examples, `.GRA`, OpenStreetMap) |
| `site/assets/cpp.js`, `networks.js` | JavaScript port of the solver and the network builders, used by the website |
| `cartero/io.py`, `instances.py` | File formats; test-network generators |
| `experiments.py` | Reproduces every experiment in the 2026 report; writes `results/*.csv` |
| `data/carp/` | Classical CARP benchmark instances (gdb, val, egl, Beullens, kshs) from [CARPData.jl](https://github.com/rafaelmartinelli/CARPData.jl) |
| `examples/pfc_1997.gra` | The worked example of the 1997 report |
| `report/` | 2026 report (Markdown source and PDF) and the 1997 report (PDF) |
| `site/` | Website sources; `tools/build_site.py` builds them into `docs/` |
| `native/` | C wrapper and build script for the optional Blossom V backend |

## Website

`docs/` is a static site with no server-side code. The *Solve a network* page runs a JavaScript port
of the solver (`site/assets/cpp.js` and `networks.js`), so it is ready in under a second. For networks
mixing one-way and two-way streets, an optional *Prove optimality* button loads this Python package in
the browser through [Pyodide](https://pyodide.org) (vendored in `docs/pyodide`, about 37 MB) and runs
the exact branch-and-cut.

The JavaScript solver is checked against the Python package on 243 networks (every benchmark, as
two-way and as mixed, plus generated towns): `python3 tests/js/make_cases.py` computes the optima in
Python, and `node tests/js/test_cpp.mjs` checks that the JavaScript finds the same ones.

Publish it with GitHub Pages: *Settings → Pages → Build and deployment → Deploy from a branch →
`main` / `/docs`*.

Rebuild it after changing the code, the reports or the site sources (`tools/fetch_pyodide.sh` restores `docs/pyodide` if needed):

```bash
pip install markdown
python3 tools/build_site.py --repo https://github.com/miquelmp/chinese-postman-problem
```

To try the site locally, serve `docs/` with any static server, for example
`python3 -m http.server -d docs`, and open http://localhost:8000.

## Fast backend (optional)

`solve_undirected(G, backend="auto")` uses Kolmogorov's Blossom V when it has been built:
a 40,000-junction network with 12,066 odd junctions solves in 102 seconds, against about 800 odd
junctions in the same time in pure Python.

```bash
bash native/build_blossom5.sh        # downloads Blossom V and builds native/libblossom5.so
```

Blossom V may be used for evaluation and non-commercial research only, and may not be
redistributed; commercial use needs a licence from UCL Business. It is therefore not included here.
Everything else works without it.

## Licences and citation

- Code: MIT (`LICENSE`).
- Reports, website texts and figures: CC BY 4.0 (`LICENSE-docs.md`).
- Benchmark instances: MIT, via CARPData.jl; cite the original papers listed in the report.
- Street data fetched by the website: © OpenStreetMap contributors, ODbL.

See `CITATION.cff` for how to cite this work.
