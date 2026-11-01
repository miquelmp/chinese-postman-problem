"""Write tests/js/cases.json: networks with the optimum computed by the Python package.

    python3 tests/js/make_cases.py      # then: node tests/js/test_cpp.mjs
"""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cartero import web                                   # noqa: E402
from cartero.mixed import MixedGraph, from_graph, solve_exact  # noqa: E402
from cartero import read_carp                             # noqa: E402


def strip(inst):
    return {"name": inst["name"], "nodes": [{"id": n["id"]} for n in inst["nodes"]], "links": inst["links"]}


def main():
    cases, seen = [], set()
    ex = [("pfc1997", {}), ("konigsberg", {}), ("petersen", {})]
    ex += [("grid", {"size": s, "seed": k}) for s in (4, 8, 15, 25) for k in range(2)]
    ex += [("delaunay", {"size": s, "seed": k}) for s in (30, 150, 400) for k in range(2)]
    ex += [("oneway-grid", {"size": s, "seed": k}) for s in (4, 8, 20) for k in range(2)]
    ex += [("mixed-town", {"size": s, "seed": k, "oneway": f}) for s in (5, 8, 12) for k in range(3) for f in (0.3, 0.6)]
    for name, kw in ex:
        inst = web.example(name, **kw)
        r = web.solve(inst, time_limit=120)
        assert r["optimal"], (name, kw)
        cases.append({"inst": strip(inst), "kind": r["kind"], "opt": r["total"]})
    for path in sorted(glob.glob(str(ROOT / "data" / "carp" / "*.dat"))):
        inst = read_carp(path)
        G = inst.graph
        sig = (G.number_of_nodes(), tuple(sorted((min(u, v), max(u, v), w) for u, v, w in G.edges(data="weight"))))
        if sig in seen or not G.number_of_edges():
            continue
        seen.add(sig)
        links = [{"u": u, "v": v, "w": w, "oneway": False} for u, v, w in G.edges(data="weight")]
        nodes = [{"id": v} for v in G]
        und = web.solve({"name": inst.name, "nodes": [{"id": v, "x": 0, "y": 0, "label": str(v)} for v in G],
                         "links": links})
        cases.append({"inst": {"name": inst.name, "nodes": nodes, "links": links}, "kind": "undirected",
                      "opt": und["total"]})
        M = from_graph(G, oneway_frac=0.4, seed=1)
        ex_ = solve_exact(M, time_limit=120)
        assert ex_.optimal
        cases.append({"inst": {"name": inst.name + " (40% one-way)", "nodes": nodes,
                               "links": [{"u": u, "v": v, "w": w, "oneway": o} for u, v, w, o in M.links]},
                      "kind": "mixed", "opt": ex_.total_cost})
    out = Path(__file__).with_name("cases.json")
    out.write_text(json.dumps(cases))
    print(f"{len(cases)} cases -> {out}")


if __name__ == "__main__":
    main()
