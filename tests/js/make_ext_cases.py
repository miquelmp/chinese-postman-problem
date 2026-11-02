"""Write tests/js/ext_cases.json: rural postman and k-postmen cases with optima from Python.

    python3 tests/js/make_ext_cases.py      # then: node tests/js/test_extensions.mjs
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import networkx as nx                                             # noqa: E402
from chinese_postman import fleet, read_carp, rural               # noqa: E402
from chinese_postman import instances as I                        # noqa: E402


def as_inst(name, G):
    return {"name": name, "nodes": [{"id": v} for v in G],
            "links": [{"u": u, "v": v, "w": d["weight"], "req": bool(d.get("required", True))}
                      for u, v, d in G.edges(data=True)]}


def random_net(seed, n, m, share):
    rng = random.Random(seed)
    while True:
        g = nx.gnm_random_graph(n, m, seed=rng.randrange(10 ** 9))
        if nx.is_connected(g):
            break
    G = nx.MultiGraph()
    for u, v in g.edges():
        G.add_edge(u, v, weight=rng.randint(1, 20), required=rng.random() < share)
    if not any(d["required"] for *_, d in G.edges(data=True)):
        u, v, k = next(iter(G.edges(keys=True)))
        G[u][v][k]["required"] = True
    return G


def main():
    rural_cases, k_cases = [], []
    for seed in range(40):
        G = random_net(seed, 9, 15, 0.4)
        dep = next(u for u, v, d in G.edges(data=True) if d["required"])
        s = rural.solve_rural(G, depot=dep, time_limit=60)
        assert s.optimal
        rural_cases.append({"inst": as_inst(f"random-{seed}", G), "depot": dep, "opt": s.total_cost})
    for size, share in ((8, 0.2), (8, 0.5), (12, 0.3)):
        for seed in range(3):
            G = I.manhattan(size, size, seed=seed)
            rng = random.Random(seed)
            for *_, d in G.edges(data=True):
                d["required"] = rng.random() < share
            dep = min(G.nodes)
            s = rural.solve_rural(G, depot=dep, time_limit=120)
            if s.optimal:
                rural_cases.append({"inst": as_inst(f"town-{size}-{share}-{seed}", G), "depot": dep,
                                    "opt": s.total_cost})
    for name in ("egl-e1-A", "egl-s1-A", "egl-s2-A"):
        inst = read_carp(str(ROOT / "data" / "carp" / f"{name}.dat"))
        G = inst.graph
        for *_, d in G.edges(data=True):
            d["required"] = d["demand"] > 0
        s = rural.solve_rural(G, depot=1, time_limit=120)
        assert s.optimal
        rural_cases.append({"inst": as_inst(name, G), "depot": 1, "opt": s.total_cost})
    for seed in range(20):
        G = random_net(500 + seed, 7, 11, 0.8)
        for k in (2, 3):
            val, opt, _ = fleet.solve_k_exact(G, k, depot=0, time_limit=120)
            if opt:
                k_cases.append({"inst": as_inst(f"small-{seed}", G), "depot": 0, "k": k, "opt": round(val, 6)})
    out = Path(__file__).with_name("ext_cases.json")
    out.write_text(json.dumps({"rural": rural_cases, "postmen": k_cases}))
    print(f"{len(rural_cases)} rural and {len(k_cases)} k-postmen cases -> {out}")


if __name__ == "__main__":
    main()
