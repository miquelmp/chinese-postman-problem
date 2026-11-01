"""Computational study for the 2026 revision. Writes CSV files to results/.

    python3 experiments.py            # all families
    python3 experiments.py scaling    # one family
"""
import csv
import glob
import os
import sys
import time

from chinese_postman import read_carp, read_gra, solve_directed, solve_undirected
from chinese_postman import instances as I

OUT = "results"
os.makedirs(OUT, exist_ok=True)


def row(family, name, G, sol, extra=None):
    r = dict(family=family, instance=name, vertices=G.number_of_nodes(), edges=G.number_of_edges(),
             odd=sol.odd_vertices, original=sol.original_cost, added=sol.added_cost,
             total=sol.total_cost, added_pct=round(100 * sol.added_cost / sol.original_cost, 2),
             seconds=round(sum(sol.seconds.values()), 4),
             **{f"t_{k.replace(' ', '_').replace('-', '_')}": round(v, 4) for k, v in sol.seconds.items()})
    r.update(extra or {})
    return r


def save(name, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(f"{OUT}/{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"-> {OUT}/{name}.csv ({len(rows)} rows)", flush=True)


def classic():
    rows = []
    cases = [("1997 example", read_gra("examples/example_1997.gra")), ("Königsberg", I.konigsberg()),
             ("Petersen", I.petersen()), ("Dodecahedron", I.dodecahedron())]
    for name, G in cases:
        sol = solve_undirected(G)
        rows.append(row("classic", name, G, sol))
        print(name, sol.total_cost, "|", " - ".join(map(str, sol.circuit)), flush=True)
    save("classic", rows)


FAMILIES = {"gdb": "gdb", "val": "val", "egl-e": "egl-e", "egl-s": "egl-s", "egl-g": "egl-g",
            "kshs": "kshs", "beullens-C": "C", "beullens-D": "D", "beullens-E": "E", "beullens-F": "F"}


def benchmarks():
    """Full road graph of every classical CARP instance, solved as a CPP.
    Instances that share a graph (e.g. val1A/1B/1C) are solved once."""
    rows, seen = [], {}
    for fam, prefix in FAMILIES.items():
        for path in sorted(glob.glob(f"data/carp/{prefix}*.dat")):
            inst = read_carp(path)
            if fam.startswith("beullens") and not inst.name[1:].isdigit():
                continue
            G = inst.graph
            sig = (G.number_of_nodes(), tuple(sorted((min(u, v), max(u, v), w)
                                                     for u, v, w in G.edges(data="weight"))))
            if sig in seen:
                continue
            seen[sig] = inst.name
            sol = solve_undirected(G, start=1)
            all_req = inst.required == G.number_of_edges()
            rows.append(row(fam, inst.name, G, sol, dict(
                required=inst.required, all_required=all_req, carp_lb=inst.lower_bound,
                carp_ub=inst.upper_bound, vehicles=inst.vehicles,
                cpp_over_carp_ub_pct=round(100 * sol.total_cost / inst.upper_bound, 1) if all_req else "")))
            print(f"{fam:11} {inst.name:10} n={G.number_of_nodes():4} m={G.number_of_edges():4} "
                  f"odd={sol.odd_vertices:4} total={sol.total_cost:7} t={sum(sol.seconds.values()):.3f}s",
                  flush=True)
    save("benchmarks", rows)


def scaling(budget=90.0):
    rows = []
    for kind in ("manhattan", "delaunay"):
        for size in (10, 15, 20, 25, 30, 35, 40, 45):
            G = (I.manhattan(size, size, drop=0.1, seed=size) if kind == "manhattan"
                 else I.delaunay_town(size * size, seed=size))
            t = time.perf_counter()
            sol = solve_undirected(G)
            el = time.perf_counter() - t
            rows.append(row("scaling-" + kind, f"{kind}-{size}x{size}", G, sol))
            print(f"{kind:9} n={G.number_of_nodes():5} m={G.number_of_edges():5} odd={sol.odd_vertices:4} "
                  f"{sol.seconds}", flush=True)
            if el > budget:
                break
    save("scaling", rows)


def directed():
    rows = []
    for r, c in ((6, 8), (10, 12), (20, 20), (40, 40), (60, 60)):
        G = I.one_way_grid(r, c, seed=r)
        sol = solve_directed(G)
        rows.append(row("directed", f"one-way-{r}x{c}", G, sol))
        print(f"one-way {r}x{c} n={G.number_of_nodes()} unbalanced={sol.odd_vertices} "
              f"added%={100 * sol.added_cost / sol.original_cost:.1f} {sol.seconds}", flush=True)
    save("directed", rows)


def scaling_fast(budget=600.0):
    """Same generators, much larger, with the Blossom V backend (SciPy Dijkstra + pricing)."""
    import resource
    from chinese_postman.fast import solve_undirected_fast
    rows = []
    plans = {"manhattan": (45, 70, 100, 140, 200), "delaunay": (2025, 5000, 10000, 20000, 40000)}
    for kind, sizes in plans.items():
        for size in sizes:
            G = (I.manhattan(size, size, drop=0.1, seed=size) if kind == "manhattan"
                 else I.delaunay_town(size, seed=size))
            t = time.perf_counter()
            sol = solve_undirected_fast(G)
            el = time.perf_counter() - t
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 2
            name = f"{kind}-{size}x{size}" if kind == "manhattan" else f"{kind}-{size}"
            rows.append(row("blossom5-" + kind, name, G, sol, dict(
                rounds=sol.matching_stats["rounds"], added_edges=sol.matching_stats["added_edges"],
                initial_edges=sol.matching_stats["initial_edges"], peak_rss_gb=round(rss, 2))))
            print(f"{kind:9} n={G.number_of_nodes():6} m={G.number_of_edges():6} odd={sol.odd_vertices:6} "
                  f"total {el:7.1f}s  " + " ".join(f"{k}={v:.1f}s" for k, v in sol.seconds.items())
                  + f"  rounds={sol.matching_stats['rounds']} peakGB={rss:.2f}", flush=True)
            save("scaling_blossom5", rows)
            if el > budget:
                break


def _mixed_row(family, name, M, limit):
    from chinese_postman.mixed import bounds, solve_exact, solve_heuristic
    n, two, one = M.counts()
    t = time.perf_counter(); pre = bounds(M); tb = time.perf_counter() - t
    he = solve_heuristic(M, pre=pre)
    try:
        ex = solve_exact(M, time_limit=limit)
        ex_cost, ex_opt, ex_s, ex_bound = ex.total_cost, ex.optimal, ex.seconds, ex.lower_bound
    except RuntimeError:
        ex_cost, ex_opt, ex_s, ex_bound = "", False, limit, ""
    best_lb = max(pre[0], ex_bound) if ex_bound != "" else pre[0]
    r = dict(family=family, instance=name, vertices=n, two_way=two, one_way=one,
             original=he.original_cost, lp_bound=pre[1], undirected_bound=pre[2],
             heuristic=he.total_cost, heuristic_s=round(he.seconds + tb, 3), flips=he.info["flips"],
             exact=ex_cost, exact_optimal=ex_opt, exact_s=round(ex_s, 3), exact_bound=ex_bound,
             heur_gap_pct=round(100 * (he.total_cost - ex_cost) / ex_cost, 2) if ex_opt else "",
             heur_gap_to_bound_pct=round(100 * (he.total_cost - best_lb) / best_lb, 2))
    print(f"{family:10} {name:14} n={n:5} two={two:5} one={one:5} heur={he.total_cost:9} "
          f"({r['heuristic_s']:.1f}s) exact={ex_cost} opt={ex_opt} ({r['exact_s']:.1f}s) "
          f"gap={r['heur_gap_pct']}", flush=True)
    return r


def mixed(limit=300.0):
    from chinese_postman.mixed import city_grid, from_graph
    rows = []
    for size in (8, 12, 16, 20, 30, 40, 60, 80):
        for seed in range(3 if size <= 20 else 1):
            M = city_grid(size, size, seed=seed)
            rows.append(_mixed_row("mixed-city", f"city-{size}x{size}-s{seed}", M, limit))
            save("mixed_city", rows)
    rows = []
    seen = set()
    for fam, prefix in FAMILIES.items():
        for path in sorted(glob.glob(f"data/carp/{prefix}*.dat")):
            inst = read_carp(path)
            if fam.startswith("beullens") and not inst.name[1:].isdigit():
                continue
            G = inst.graph
            sig = (G.number_of_nodes(), tuple(sorted((min(u, v), max(u, v), w)
                                                     for u, v, w in G.edges(data="weight"))))
            if sig in seen:
                continue
            seen.add(sig)
            M = from_graph(G, oneway_frac=0.4, seed=1)
            rows.append(_mixed_row("mixed-" + fam, inst.name, M, limit))
    save("mixed_benchmarks", rows)


if __name__ == "__main__":
    todo = sys.argv[1:] or ["classic", "benchmarks", "directed", "scaling"]
    for name in todo:
        globals()[name]()
