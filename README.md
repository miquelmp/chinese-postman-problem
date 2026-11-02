# The Chinese Postman Problem — 1997 and 2026

The shortest closed walk that covers every street of a network. This repository revisits a 1997
final-year engineering project (Miquel Monserrat Pons, ETSEIB, supervised by Ramón Companys
Pascual) with today's implementations.

**Website: https://miquelmp.github.io/chinese-postman-problem/**


- **Website** (`docs/`): the story, both reports, and a solver that runs in your browser.
- **Python package** `chinese_postman`: undirected, directed and mixed Chinese Postman solvers, all with
  proven optimality or a certified gap, and the paths left open in 1997: streets that need service
  only once (rural postman), several postmen, and capacitated fleets.
- **Reports** (`report/`): the 2026 revision (Markdown and PDF) and the original 1997 report (PDF, Spanish).
- **Data and results**: 92 classical benchmark networks and every result file behind the report.

## Statement of need

Street services must cover streets rather than visit points, and researchers in arc routing need solvers
they can run, check and extend. The classical problems are well understood, but open tools with proofs
of optimality are scarce: a practitioner usually needs a commercial solver, or a heuristic with no
measure of its quality. This package targets researchers and students in operations research, and
engineers planning street services. It solves the Chinese, mixed and rural postman problems exactly where
it can, and otherwise returns a heuristic tour with a proven lower bound, using open-source solvers only.

## Related software

| Tool | Language | Scope | Exact methods | Last activity |
| --- | --- | --- | --- | --- |
| This package | Python, JavaScript | Undirected, directed, mixed, rural, several postmen, CARP | Matching, minimum-cost flow, branch-and-cut (HiGHS) | 2026 |
| [OAR Lib](https://github.com/Olibear/ArcRoutingLibrary) (Lum, Golden and Wasil, 2019) | Java | Undirected, directed, mixed, windy rural, directed rural, several vehicles | Undirected and directed only; heuristics elsewhere | 2019 |
| [postman_problems](https://github.com/brooksandrew/postman_problems) (Brooks) | Python | Undirected, and rural when the required streets form one component | Not stated | 2018 |

OAR Lib is the closest project, and is broader in some ways: it covers windy and directed rural problems,
which this package does not. A new package rather than a contribution to it was chosen because it is
written in Java and has been inactive since 2019, while this work needed exact mixed and rural methods
on open-source solvers, a Python interface and a version that runs in the browser. NetworkX provides
building blocks, Eulerian circuits and matchings, which this package uses.

## What the solver does

| Network | Method | Guarantee |
|---|---|---|
| Two-way streets | Shortest paths + minimum-weight perfect matching (Edmonds' blossom) + Hierholzer | Optimal, polynomial time |
| One-way streets | Minimum-cost flow + Hierholzer | Optimal, polynomial time |
| One-way and two-way mixed (NP-hard) | Heuristic, then branch-and-cut (HiGHS) | Optimal, or within a certified gap at the time limit |
| First pass dearer than later ones, every street | Matching on the cost of later passes | Optimal, polynomial time |
| Only some streets need service (rural postman, NP-hard) | Frederickson + local search, then branch-and-cut | Optimal, or within a certified gap; heuristic never above 3/2 of the optimum |
| k postmen, longest route as short as possible (NP-hard) | One tour split optimally into k routes + local search | Within a certified gap; split never above 2 − 1/k of the optimum |
| Vehicles with a capacity (CARP, NP-hard) | One tour split by capacity (Ulusoy) + moves between routes | Compared with the best known solutions |

## Install and use

```bash
pip install -e ".[test]"
pytest -q                            # 235 tests (294 once the optional LEMON library is built)
```

```python
from chinese_postman import read_gra, solve_undirected
sol = solve_undirected(read_gra("examples/example_1997.gra"), start=1)
print(sol.summary())                 # total 63 = 54 + 9, as in the 1997 report

from chinese_postman.mixed import city_grid, solve_mixed
M = city_grid(20, 20, seed=0)        # whole streets one-way with probability 0.6
sol = solve_mixed(M, time_limit=300) # heuristic first, then branch-and-cut while it pays
print(sol.total_cost, sol.optimal, sol.info["gap_pct"])
```

`solve_mixed` returns the best tour found together with a proven lower bound. Pass `gap_tol=0.005`
to stop as soon as the tour is certified within 0.5% of the optimum.

The extensions work on any NetworkX multigraph whose edges carry `weight` (the cost of travelling
along a street), and optionally `service` (the cost of the pass that serves it) and `required`:

```python
from chinese_postman import rural, fleet
sol = rural.solve_rural(G, depot=1, time_limit=60)   # serve the streets marked required=True
print(sol.total_cost, sol.lower_bound, sol.optimal)
team = fleet.solve_k_postmen(G, k=3, depot=1)        # three routes, longest as short as possible
print(team.route_costs, team.lower_bound)
```

## Layout

| Path | Contents |
|---|---|
| `chinese_postman/cpp.py` | Undirected CPP (Edmonds' method) and directed CPP (minimum-cost flow) |
| `chinese_postman/mixed.py` | Mixed CPP: bounds, exact branch-and-cut, heuristic with local search, combined `solve_mixed` |
| `chinese_postman/rural.py` | Service and travel costs; rural postman: Frederickson, bounds, branch-and-cut, combined `solve_rural` |
| `chinese_postman/fleet.py` | Several postmen (min-max k-postmen), exact model for small cases, capacitated fleets (CARP) |
| `chinese_postman/sequence.py` | Routes as sequences of served streets: cost, best directions, insertion, local search |
| `chinese_postman/bnb.py` | The 1997 branch-and-bound and the tightened bound of section 8.3, kept for measurement |
| `chinese_postman/euler.py` | Hierholzer's algorithm for directed and undirected multigraphs |
| `chinese_postman/fast.py` | Optional fast backend: SciPy Dijkstra + LEMON with dual pricing and a certificate |
| `chinese_postman/web.py` | JSON entry points used by the website's exact proof (examples, `.GRA`, OpenStreetMap) |
| `site/assets/cpp.js`, `extensions.js`, `networks.js` | JavaScript port of the solvers and the network builders, used by the website |
| `chinese_postman/io.py`, `instances.py` | File formats; test-network generators |
| `experiments.py` | Reproduces the experiments of chapters 7 to 10 of the 2026 report; writes `results/*.csv` |
| `tools/certify_matching.py`, `tools/match_sparse.mjs` | Repeats the large matchings with the JavaScript blossom code |
| `tools/fetch_mcpp.sh` | Downloads the published mixed instances into `data/mcpp/` (not stored here) |
| `data/carp/` | Classical CARP benchmark instances (gdb, val, egl, Beullens, kshs) from [CARPData.jl](https://github.com/rafaelmartinelli/CARPData.jl) |
| `examples/example_1997.gra` | The worked example of the 1997 report |
| `report/` | 2026 report (Markdown source and PDF) and the 1997 report (PDF) |
| `site/` | Website sources; `tools/build_site.py` builds them into `docs/` |
| `native/` | C wrapper, build script and LEMON sources for the optional fast backend |

## Website

`docs/` is a static site with no server-side code. The *Solve a network* page runs a JavaScript port
of the solver (`site/assets/cpp.js` and `networks.js`), so it is ready in under a second. For networks
mixing one-way and two-way streets, an optional *Prove optimality* button loads this Python package in
the browser through [Pyodide](https://pyodide.org) (vendored in `docs/pyodide`, about 37 MB) and runs
the exact branch-and-cut.

The JavaScript solver is checked against the Python package on 243 networks (every benchmark, as
two-way and as mixed, plus generated towns): `python3 tests/js/make_cases.py` computes the optima in
Python, and `node tests/js/test_cpp.mjs` checks that the JavaScript finds the same ones. The extensions
are checked the same way (`tests/js/make_ext_cases.py`, `node tests/js/test_extensions.mjs`) on 52
rural-postman and 39 several-postmen networks with optima proved in Python. `tests/js/test_matching.mjs` checks the matching alone on 3,000
random cost matrices, with optima from NetworkX (`tests/js/make_matchings.py`).

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

`solve_undirected(G, backend="auto")` uses LEMON's matching code when it has been built:
a 40,000-junction network with 12,066 odd junctions solves in a median 110 seconds, against about 800 odd
junctions in the same time in pure Python. Every result is checked by a dual certificate, and
`python3 tools/certify_matching.py` repeats those optima with a second blossom code.

```bash
bash native/build_lemon.sh           # needs a C++ compiler; builds native/liblemon_match.so
```

The LEMON sources in `native/lemon_src` are under the Boost Software License 1.0. Everything else
works without building them.

## Documentation and support

- [API reference](https://miquelmp.github.io/chinese-postman-problem/api/), [`ARCHITECTURE.md`](ARCHITECTURE.md) for the design decisions, and the [2026 report](https://miquelmp.github.io/chinese-postman-problem/report/) for the methods.
- [`REPRODUCING.md`](REPRODUCING.md) maps every table of the report to the command that produces it.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) explains how to report problems, ask for help and contribute. See also the [code of conduct](CODE_OF_CONDUCT.md) and the [changelog](CHANGELOG.md).

## Use of generative AI

The 2026 revision was prepared with generative AI assistance (Claude, by Anthropic), in the code, the
experiments, the documentation and the audit of the report. The 1997 project was not. Commits co-authored
by Claude are marked as such.

## Licences and citation

- Code: MIT (`LICENSE`).
- Reports, website texts and figures: CC BY 4.0 (`LICENSE-docs.md`).
- Benchmark instances: MIT, via CARPData.jl; cite the original papers listed in the report.
- Street data fetched by the website: © OpenStreetMap contributors, ODbL.

See `CITATION.cff` for how to cite this work.
