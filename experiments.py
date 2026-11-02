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


def cpp_bound():
    """CPP optimum against the best known CARP solution on every gdb, val and kshs file in
    which all streets are required. Files sharing a road network are kept here: they differ in
    capacity and vehicles, and that difference is what this study measures."""
    rows = []
    for prefix in ("gdb", "val", "kshs"):
        for path in sorted(glob.glob(f"data/carp/{prefix}*.dat")):
            inst = read_carp(path)
            if inst.required != inst.graph.number_of_edges():
                continue
            sol = solve_undirected(inst.graph, start=1)
            rows.append(dict(family=prefix, instance=inst.name, vertices=inst.graph.number_of_nodes(),
                             edges=inst.graph.number_of_edges(), vehicles=inst.vehicles, capacity=inst.capacity,
                             cpp=sol.total_cost, carp_lb=inst.lower_bound, carp_ub=inst.upper_bound,
                             cpp_over_carp_ub_pct=round(100 * sol.total_cost / inst.upper_bound, 2)))
    save("cpp_bound", rows)


def bnb(limit=200_000, per_size=5):
    """Section 8.3: nodes explored by the branch-and-bound on grid towns with a given number of
    odd vertices. The limit counts explored nodes, so the runs do not depend on machine speed."""
    import networkx as nx
    import numpy as np
    from chinese_postman.bnb import branch_and_bound
    from chinese_postman.cpp import min_weight_pairing
    variants = {"1997": dict(bound="1997"), "tightened": dict(bound="tight"),
                "improved": dict(bound="tight", branch="constrained", start=True)}
    plans = {"1997": (8, 12, 16, 20, 24, 30), "tightened": (8, 12, 16, 20, 24, 30, 40, 50, 60),
             "improved": (8, 12, 16, 20, 24, 30, 40, 50, 60)}
    found = {}
    for size in range(4, 15):
        for seed in range(300):
            G = I.manhattan(size, size, drop=0.1, seed=seed)
            odd = [v for v in G if G.degree(v) % 2]
            if len(found.setdefault(len(odd), [])) < per_size:
                found[len(odd)].append((size, seed, G, odd))
    rows = []
    for name, kw in variants.items():
        for target in plans[name]:
            for size, seed, G, odd in found[target]:
                H = nx.Graph()
                H.add_weighted_edges_from(G.edges(data="weight"))
                d = dict(nx.all_pairs_dijkstra_path_length(H))
                D = np.array([[d[u][v] for v in odd] for u in odd])
                t = time.perf_counter()
                exact = sum(d[u][v] for u, v in min_weight_pairing(odd, {(u, v): d[u][v] for u in odd for v in odd}))
                blossom_s = time.perf_counter() - t
                r = branch_and_bound(D, max_nodes=limit, **kw)
                rows.append(dict(variant=name, odd=target, size=size, seed=seed, proven=r.proven,
                                 explored=r.explored, generated=r.generated, cost=r.cost, optimum=exact,
                                 seconds=round(r.seconds, 3), blossom_seconds=round(blossom_s, 4)))
                print(rows[-1], flush=True)
                save("bnb", rows)


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
    """Same generators, much larger, with the LEMON backend (SciPy Dijkstra + pricing)."""
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
            rows.append(row("lemon-" + kind, name, G, sol, dict(
                rounds=sol.matching_stats["rounds"], added_edges=sol.matching_stats["added_edges"],
                initial_edges=sol.matching_stats["initial_edges"], peak_rss_gb=round(rss, 2))))
            print(f"{kind:9} n={G.number_of_nodes():6} m={G.number_of_edges():6} odd={sol.odd_vertices:6} "
                  f"total {el:7.1f}s  " + " ".join(f"{k}={v:.1f}s" for k, v in sol.seconds.items())
                  + f"  rounds={sol.matching_stats['rounds']} peakGB={rss:.2f}", flush=True)
            save("scaling_lemon", rows)
            if el > budget:
                break


def local_search():
    """Section 9.3: gap to the proven optimum of the best starting orientation, before and after
    the local search, on every instance of results/mixed_*.csv with a proven optimum."""
    from chinese_postman.mixed import city_grid, from_graph, solve_heuristic
    rows = []

    def add(family, name, M, exact):
        he = solve_heuristic(M)
        before = min(he.info["candidates"].values())
        rows.append(dict(family=family, instance=name, vertices=len(M.nodes), before=before, after=he.total_cost,
                         exact=exact, flips=he.info["flips"], gap_before_pct=round(100 * (before - exact) / exact, 2),
                         gap_after_pct=round(100 * (he.total_cost - exact) / exact, 2)))
        print(rows[-1], flush=True)

    with open(f"{OUT}/mixed_city.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["exact_optimal"] == "True":
                size, seed = r["instance"].split("-")[1].split("x")[0], r["instance"].rsplit("s", 1)[1]
                add("town", r["instance"], city_grid(int(size), int(size), seed=int(seed)), float(r["exact"]))
    with open(f"{OUT}/mixed_benchmarks.csv", newline="", encoding="utf-8") as f:
        pub = {r["instance"]: r for r in csv.DictReader(f)}
    for path in sorted(glob.glob("data/carp/*.dat")):
        inst = read_carp(path)
        if inst.name in pub:
            add("benchmark", inst.name, from_graph(inst.graph, oneway_frac=0.4, seed=1), float(pub[inst.name]["exact"]))
    save("local_search", rows)


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


def record_environment():
    """Write results/environment.json: the machine and versions behind the timings."""
    import json
    import platform
    import networkx
    import numpy
    import scipy
    cpu, ram = platform.processor(), None
    if os.path.exists("/proc/cpuinfo"):                # Linux; elsewhere the fields stay generic
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            cpu = next((line.split(":", 1)[1].strip() for line in f if line.startswith("model name")), cpu)
        ram = round(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024 ** 3, 1)
    with open(f"{OUT}/environment.json", "w", encoding="utf-8") as f:
        json.dump(dict(cpu=cpu, cores=os.cpu_count(), ram_gb=ram,
                       system=platform.platform(), python=platform.python_version(),
                       numpy=numpy.__version__, scipy=scipy.__version__,
                       networkx=networkx.__version__, date=time.strftime("%Y-%m-%d")), f, indent=2)


def mixed_towns(limit=300.0, seeds=5):
    """Five towns per size. Resumes from results/mixed_city.csv if a run was interrupted."""
    from chinese_postman.mixed import city_grid
    record_environment()
    rows = []
    if os.path.exists(f"{OUT}/mixed_city.csv"):
        with open(f"{OUT}/mixed_city.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    done = {r["instance"] for r in rows}
    for size in (8, 12, 16, 20, 30, 40, 60, 80):
        for seed in range(seeds):
            name = f"city-{size}x{size}-s{seed}"
            if name not in done:
                rows.append(_mixed_row("mixed-city", name, city_grid(size, size, seed=seed), limit))
                save("mixed_city", rows)


def mcpp(limit=120.0, step=4):
    """Published mixed instances of Corberan et al. (run tools/fetch_mcpp.sh first): every
    `step`-th file, balanced across the sets, smallest networks first so that an interrupted run
    still covers both sets evenly. Resumes from results/mixed_published.csv."""
    from chinese_postman.mixed import read_mcpp
    record_environment()
    rows = []
    if os.path.exists(f"{OUT}/mixed_published.csv"):
        with open(f"{OUT}/mixed_published.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    done = {r["instance"] for r in rows}
    for path in sorted(sorted(glob.glob("data/mcpp/M*"))[::step], key=lambda p: os.path.basename(p)[2:4]):
        name = os.path.basename(path)
        if name not in done:
            rows.append(_mixed_row("mcpp-" + name[:2], name, read_mcpp(path), limit))
            save("mixed_published", rows)


def mixed(limit=300.0):
    from chinese_postman.mixed import from_graph
    mixed_towns(limit)
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


def _rural_row(family, name, G, limit, depot=1):
    from chinese_postman import rural
    t = time.perf_counter()
    sol = rural.solve_rural(G, depot=depot, time_limit=limit)
    i = sol.info
    req = sum(1 for *_, d in G.edges(data=True) if d.get("required", True))
    r = dict(family=family, instance=name, vertices=G.number_of_nodes(), edges=G.number_of_edges(),
             required=req, pieces=i.get("pieces", 1), service=sol.service_cost,
             frederickson=i.get("frederickson", sol.total_cost),
             heuristic=i.get("heuristic_cost", sol.total_cost), lp_bound=i.get("lp_bound", ""),
             best=sol.total_cost, lower_bound=sol.lower_bound, optimal=sol.optimal,
             method=sol.method, seconds=round(time.perf_counter() - t, 3),
             bound_gap_pct=round(sol.gap_pct, 2),
             frederickson_gap_pct=round(100 * (i.get("frederickson", sol.total_cost) - sol.total_cost)
                                        / sol.total_cost, 2),
             heuristic_gap_pct=round(100 * (i.get("heuristic_cost", sol.total_cost) - sol.total_cost)
                                     / sol.total_cost, 2))
    print(f"{family:10} {name:14} req={req:4}/{G.number_of_edges():4} pieces={r['pieces']:3} "
          f"fred={r['frederickson']:8} heur={r['heuristic']:8} best={sol.total_cost:8} "
          f"opt={sol.optimal} {r['seconds']}s", flush=True)
    return r


def rural(limit=120.0):
    """Rural postman: benchmark networks whose files mark only some streets as required,
    and synthetic towns where a random share of the streets needs service."""
    import random
    rows, seen = [], set()
    for fam, prefix in FAMILIES.items():
        for path in sorted(glob.glob(f"data/carp/{prefix}*.dat")):
            inst = read_carp(path)
            G = inst.graph
            if inst.required == G.number_of_edges():
                continue
            for u, v, k, d in G.edges(keys=True, data=True):
                d["required"] = d["demand"] > 0
            sig = tuple(sorted((min(u, v), max(u, v), w, d["required"]) for u, v, w, d in
                               ((u, v, d["weight"], d) for u, v, d in G.edges(data=True))))
            if sig in seen:
                continue
            seen.add(sig)
            rows.append(_rural_row("rpp-" + fam, inst.name, G, limit))
            save("rural_benchmarks", rows)
    rows = []
    for size in (10, 20, 30):
        for share in (0.2, 0.5):
            for seed in range(3):
                G = I.manhattan(size, size, seed=seed)
                rng = random.Random(seed)
                for u, v, k, d in G.edges(keys=True, data=True):
                    d["required"] = rng.random() < share
                depot = min(G.nodes)
                rows.append(_rural_row("rpp-town", f"town-{size}x{size}-{int(share*100)}%-s{seed}",
                                       G, limit, depot=depot))
                save("rural_towns", rows)


def fleet_small(seconds=1.0, seeds=8):
    """k postmen on small random networks: tour split and local search against the exact optimum."""
    import random
    import networkx as nx
    from chinese_postman import fleet, rural
    from chinese_postman.sequence import orient, route_cost, from_circuit
    rows = []
    for n, m in ((6, 9), (7, 11)):
        for seed in range(seeds):
            rng = random.Random(1000 * n + seed)
            while True:
                g = nx.gnm_random_graph(n, m, seed=rng.randrange(10 ** 9))
                if nx.is_connected(g):
                    break
            for share in (1.0, 0.6):
                G = nx.MultiGraph()
                for u, v in g.edges():
                    G.add_edge(u, v, weight=rng.randint(1, 20), required=rng.random() < share)
                if not any(d["required"] for *_, d in G.edges(data=True)):
                    continue
                for k in (2, 3):
                    t = time.perf_counter()
                    sol = fleet.solve_k_postmen(G, k, depot=0, local_seconds=seconds)
                    th = time.perf_counter() - t
                    t = time.perf_counter()
                    val, opt, _ = fleet.solve_k_exact(G, k, depot=0, time_limit=60)
                    te = time.perf_counter() - t
                    if val is None or not opt:
                        continue
                    val = round(val, 6)
                    rows.append(dict(n=n, m=m, seed=seed, required_share=share, k=k,
                                     single=sol.info["single_tour"], split=sol.info["split_max"],
                                     heuristic=sol.max_cost, optimum=val, lower_bound=sol.lower_bound,
                                     split_gap_pct=round(100 * (sol.info["split_max"] - val) / val, 2),
                                     heuristic_gap_pct=round(100 * (sol.max_cost - val) / val, 2),
                                     split_ratio=round(sol.info["split_max"] / val, 4),
                                     guarantee=round(2 - 1 / k, 4), heuristic_s=round(th, 3),
                                     exact_s=round(te, 3)))
            print(n, m, seed, flush=True)
        save("fleet_small", rows)


def fleet_benchmarks(seconds=5.0):
    """k postmen on the benchmark networks (k = the vehicles of the file), against the bound."""
    from chinese_postman import fleet
    rows, seen = [], set()
    for fam, prefix in FAMILIES.items():
        for path in sorted(glob.glob(f"data/carp/{prefix}*.dat")):
            inst = read_carp(path)
            if fam.startswith("beullens") and not inst.name[1:].isdigit():
                continue
            G = inst.graph
            for u, v, k, d in G.edges(keys=True, data=True):
                d["required"] = d["demand"] > 0
            sig = (fam, G.number_of_nodes(), G.number_of_edges(), inst.required)
            if sig in seen:
                continue
            seen.add(sig)
            for k in sorted({2, 4, inst.vehicles}):
                t = time.perf_counter()
                sol = fleet.solve_k_postmen(G, k, depot=1, time_limit=seconds * 3, local_seconds=seconds)
                rows.append(dict(family=fam, instance=inst.name, vertices=G.number_of_nodes(),
                                 edges=G.number_of_edges(), required=inst.required, k=k,
                                 single=sol.info["single_tour"], split=sol.info["split_max"],
                                 longest=sol.max_cost, total=sol.total_cost, lower_bound=sol.lower_bound,
                                 far_bound=sol.info["far_bound"], gap_pct=round(sol.gap_pct, 2),
                                 split_gap_pct=round(100 * (sol.info["split_max"] - sol.lower_bound)
                                                     / sol.lower_bound, 2),
                                 seconds=round(time.perf_counter() - t, 2)))
                print(f"{fam:10} {inst.name:10} k={k:2} split={sol.info['split_max']:8.0f} "
                      f"longest={sol.max_cost:8.0f} lb={sol.lower_bound:8.0f} gap={sol.gap_pct:5.2f}%",
                      flush=True)
            save("fleet_benchmarks", rows)


def carp(seconds=5.0):
    """Capacitated fleets: route first, cluster second, against the best known solutions."""
    from chinese_postman import fleet
    rows = []
    for fam, prefix in FAMILIES.items():
        for path in sorted(glob.glob(f"data/carp/{prefix}*.dat")):
            inst = read_carp(path)
            t = time.perf_counter()
            sol = fleet.solve_carp(inst.graph, inst.capacity, depot=1, local_seconds=seconds)
            ub, lb = inst.upper_bound, inst.lower_bound
            rows.append(dict(family=fam, instance=inst.name, vertices=inst.graph.number_of_nodes(),
                             edges=inst.graph.number_of_edges(), required=inst.required,
                             capacity=inst.capacity, best_known=ub, best_lower_bound=lb,
                             split=sol.info["split_total"], improved=sol.total_cost,
                             vehicles_used=len(sol.routes),
                             split_gap_pct=round(100 * (sol.info["split_total"] - ub) / ub, 2),
                             gap_to_best_known_pct=round(100 * (sol.total_cost - ub) / ub, 2),
                             seconds=round(time.perf_counter() - t, 2)))
            print(f"{fam:10} {inst.name:10} split={sol.info['split_total']:7.0f} "
                  f"improved={sol.total_cost:7.0f} best={ub:6} gap={rows[-1]['gap_to_best_known_pct']:5.2f}%",
                  flush=True)
        save("carp", rows)


if __name__ == "__main__":
    todo = sys.argv[1:] or ["classic", "benchmarks", "cpp_bound", "bnb", "directed", "scaling"]
    for name in todo:
        globals()[name]()
