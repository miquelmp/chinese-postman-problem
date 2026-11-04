# Changelog

## Unreleased

- The solver has a new service setting, Choose on the map: click streets to add or remove them, with Select all, Clear and a count.
- The home page describes the whole 2026 scope, offers three routes (Understand, Try, Research), and replaces the long comparison table with four indicators and five advances that separate proved guarantees from measurements. The animated example and the citation section are unchanged.
- The abstract is split by problem, method, contributions, results and conclusions, and limits its claims of optimality and guarantees. No result changes.
- Section 10.1 separates a lower bound on one solution from an approximation guarantee, and the README states the type of guarantee of each method, with its assumptions.
- On windy networks the solver reports costs, not distances: the labels, units and proof text now say so, and the proof text no longer blames one-way streets.
- `results/dgrp_lap.csv` holds all 70 large files, including the 3 stopped by the 5-minute limit.
- The abstract covers the windy postman and the rural and several-postmen problems on every network.
- Section 10.7 compares the mixed rural results with the 36 published optima: every proved value equals its published value, and no route or bound crosses one.
- Section 10.7 adds the published directed general routing and stacker crane instances: 113 of 150 proved, each equal to the published optimum. Sixty stacker crane files, which hold fewer arcs than their headers count, were left out.
- `RuralProblem` takes vertices that must be visited, `read_directed_general` reads these files, and above 10,000 links `solve` runs branch-and-cut first.
- A 5-minute run proves 14 of the 16 directed rural files that 20 seconds left open.

## 2026.11.0 — 3 November 2026

- Adds the rural postman and several postmen on one-way, mixed and windy networks: `chinese_postman/windyrural.py`, `chinese_postman/kpostmen.py`, section 10.7 of the report, and the solver page. The coverage table on the extensions page is complete.
- On published instances: windy rural best routes a mean 0.62% above the optimum (worst 7.6%, 47 instances); several postmen a mean 2.15% above (worst 17.2%, 629 optima, with the depot assumed at vertex 1). Directed rural instances have no published values here and were measured against the bound.
- The solver shows which problem is being solved, its complexity, the kind of solution and a link to the report.
- Streets show their cost: on a label when all labels fit, otherwise when the pointer rests on them, with both costs on a windy street.
- The extensions page has a table of the network and service combinations solved so far, and the solver disables the others.
- Partial service and several postmen now refuse windy networks, instead of ignoring the second cost.

## 2026.10.0 — 3 November 2026

- Adds the windy postman: `chinese_postman/windy.py`, section 10.6 of the report, a section on the extensions page, and a hilly town in the solver.
- Win's method is a mean 0.10% above the 99 published optima, with a worst case of 0.44%. Ten tours improve on the list of published bounds.
- Section 6.8 mentions Route Crafter.
- The page of the 1997 report says why branch-and-bound was chosen.
- Removes from section 7.1 a description of the Delaunay towns that 2026.9.0 made obsolete.

## 2026.9.0 — 3 November 2026

- Delaunay towns keep a constant density of junctions at any size, with lengths of at least 1 m. The old towns had streets of 4 m at 40,000 junctions, and 595 zero costs. All Delaunay measurements are rerun, and the optima change because the lengths do.
- The home page and the summaries state that CARP results leave the number of vehicles free.
- Section 8.2 explains why branch-and-bound was chosen in 1997.
- Corrected a stale count of automated tests.

## 2026.8.0 — 3 November 2026

- Five real street networks from OpenStreetMap are solved and reported (`data/osm`, `results/mixed_osm.csv`).
- `native/lemon_src/README.md` records a further comparison: 22 of the 26 LEMON files match a copy with the older code.

## 2026.7.0 — 2 November 2026

- Run times are the median of five repeats (`results/timing_repeats.csv`), with their range: 110 s for 12,066 odd vertices and 266 s for 19,942.
- The CARP comparison now separates tight fleets from the nominal 100 vehicles of the Beullens files, and states the two conventions on fleet size. It no longer gives the 4.7% median, which mixed the two.

## 2026.6.0 — 2 November 2026

- Results on the mixed instances of Corberán et al. (2012) are compared with the published values. All 39 optima proved here equal them.
- The sample is complete at 30 instances, and all 48 instances of 500 and 1,000 junctions are added. They separate street density from the one-way share, which the sample had linked.
- The heuristic's published figures change: mean 2.09% and worst 5.79% against the published optima, in place of 1.50% and 5.33% on the instances proved here.
- `native/lemon_src` now carries LEMON's own `LICENSE` file, and its notes list the compiler fixes in the rlemon copy.

## 2026.5.0 — 2 November 2026

- LEMON replaces Blossom V in the fast backend. Its sources are included, so anyone can build the backend and run its tests.
- Every result of the fast backend is checked by a dual certificate. 19,942 odd vertices now solve in 271 s.
- The largest grid takes 115 s, against the 102 s measured earlier with Blossom V, which was not reproduced. Both give the same optima.
- The report and the website now state that the 2026 revision used AI assistance.

## 2026.4.0 — 2 November 2026

- `tools/certify_matching.py` confirms every optimum of the fast backend with a dual certificate, without Blossom V, and reaches 19,942 odd vertices.
- Mixed heuristic and exact method measured on 25 published instances (`results/mixed_published.csv`). The heuristic is weaker and slower there than on the project's own networks.
- API reference, docstrings, contributing guide, code of conduct, architecture notes, reproduction guide and pinned dependencies.
- The report now separates established methods from new work and states tolerances and the hypotheses of the guarantees.
- The CARP comparison on the 65 instances with more vehicles no longer says which way the difference goes, because that was not checked.

## 2026.3.0 — 2 November 2026

- Mixed towns measured on five seeds per size. All towns of up to 400 junctions are proved, and 8 of the 10 at 900 and 1,600.
- The machine behind the results is recorded in `results/environment.json`.

## 2026.2.0 — 2 November 2026

- Full audit of the site, the report, the code and the data.
- `solve_exact` for mixed and rural networks and `solve_k_exact` now use a zero relative gap.
- Added `chinese_postman/bnb.py` and the experiments behind sections 8.3 and 9.3.
- Fleet bound measured on all 63 all-required instances.
- JavaScript matching tested against NetworkX on 3,000 random cases.

## 2026.1.0 — 1 November 2026

- First public version: undirected, directed and mixed solvers, rural postman, several postmen and capacitated fleets, the website and the report.
