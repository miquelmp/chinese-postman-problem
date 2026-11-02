# Architecture

## Layers

| Layer | Files | Role |
| --- | --- | --- |
| Formats and instances | `io.py`, `instances.py` | Files and test-network generators |
| Tours | `euler.py`, `sequence.py` | Eulerian circuits; routes as sequences of served streets |
| Polynomial problems | `cpp.py`, `fast.py` | Undirected and directed CPP |
| NP-hard problems | `mixed.py`, `rural.py`, `fleet.py` | Exact models, bounds and heuristics |
| Measurement | `bnb.py`, `experiments.py`, `tools/certify_matching.py` | The 1997 search; experiments; certificates |
| Web | `web.py`, `site/assets/cpp.js`, `extensions.js`, `networks.js` | The browser version |

## Design decisions

**NetworkX multigraphs as the common input.** Graphs are simple to build and inspect, and parallel streets are kept. Solvers
convert to a compact form internally where speed matters. The cost is speed: the default matching is pure Python.

**Blossom V is optional.** Its licence forbids redistribution and commercial use, so NetworkX stays the default, and the
package works without any compiled code. `tools/certify_matching.py` checks large optima without Blossom V.

**HiGHS through SciPy for integer programs.** It is open source and installs with SciPy, so an exact mixed or rural solve
needs no commercial solver. A dedicated branch-and-cut would scale further, but would be far more code to verify.

**Exact results carry their evidence.** A solution reports a lower bound and whether it is proven optimal, and a heuristic
always comes with its bound. The relative gap of the integer solver is set to zero, so "optimal" means proved.

**Certificates over trust.** A dual certificate needs only the distances and a few numbers, so the check does not depend on
the solver that produced the matching.

**Two languages for the website.** The browser solver is a JavaScript port, ready in under a second, and Pyodide is loaded
only to prove a mixed optimum. The port must be kept in step, so tests in `tests/js/` compare it with Python.

**Routes as sequences of served streets.** For the rural postman and fleets, a route is the order of its streets, joined by
shortest paths. Local search then needs no graph surgery, and any closed walk can be written this way at no greater cost.

## Trade-offs and limits

- Distances between odd vertices are stored as a dense table, so memory grows with the square of their number.
- The heuristics are simple by design, and are weaker on some published instances than on the towns: see chapter 9 of the report.
- CARP routes are found by splitting one tour, and the number of vehicles is left free.
