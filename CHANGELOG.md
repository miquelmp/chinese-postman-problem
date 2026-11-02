# Changelog

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
