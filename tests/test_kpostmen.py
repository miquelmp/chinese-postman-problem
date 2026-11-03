"""Several postmen on windy, mixed and directed networks."""
import csv
import random
from collections import Counter
from pathlib import Path

import networkx as nx
import pytest

from chinese_postman import web
from chinese_postman.kpostmen import solve_k_postmen
from chinese_postman.windyrural import RuralProblem


def network(seed, kind):
    rnd = random.Random(seed)
    while True:
        G = nx.gnm_random_graph(14, 26, seed=rnd.randrange(10 ** 6))
        if not nx.is_connected(G):
            continue
        links = []
        for u, v in G.edges:
            a, b = rnd.randint(1, 30), rnd.randint(1, 30)
            if kind == "mixed" and rnd.random() < 0.4:
                b = None
            if kind == "directed":
                links += [(u, v, a, None, rnd.random() < 0.6), (v, u, b, None, rnd.random() < 0.6)]
            else:
                links.append((u, v, a, b, rnd.random() < 0.6))
        P = RuralProblem(links, 0)
        if P.is_feasible():
            return P


def check(P, sol):
    best = {}
    for u, v, a, b, _ in P.links:
        if a is not None:
            best[u, v] = min(a, best.get((u, v), a))
        if b is not None:
            best[v, u] = min(b, best.get((v, u), b))
    served = set()
    for route, cost in zip(sol.routes, sol.costs):
        assert route[0] == P.depot == route[-1]
        steps = Counter(zip(route, route[1:]))
        assert all(s in best for s in steps)
        served |= {frozenset(s) for s in steps}
        assert sum(best[s] * n for s, n in steps.items()) <= cost + 1e-9
    assert all(frozenset(l[:2]) in served for l in P.links if l[4])


@pytest.mark.parametrize("kind", ["windy", "mixed", "directed"])
@pytest.mark.parametrize("k", [1, 2, 4])
@pytest.mark.parametrize("seed", range(3))
def test_routes_serve_everything_within_the_bound(kind, k, seed):
    P = network(seed, kind)
    sol = solve_k_postmen(P, k, local_seconds=1)
    check(P, sol)
    assert len(sol.routes) <= k
    assert sol.lower_bound <= sol.longest + 1e-9


@pytest.mark.parametrize("seed", range(3))
def test_more_postmen_never_lengthen_the_longest_split(seed):
    P = network(seed, "windy")
    a = solve_k_postmen(P, 2, local_seconds=0).info["split_longest"]
    b = solve_k_postmen(P, 4, local_seconds=0).info["split_longest"]
    assert b <= a + 1e-9


def test_web_solves_partial_service_on_one_way_streets():
    links = [dict(u=u, v=v, w=w, oneway=True, req=r) for u, v, w, r in
             [(0, 1, 3, True), (1, 2, 4, False), (2, 0, 5, False), (0, 2, 7, True), (2, 1, 2, False), (1, 0, 2, False)]]
    r = web.solve(dict(name="t", nodes=[dict(id=i) for i in range(3)], links=links))
    assert r["optimal"] and r["kind"] == "rural" and r["total"] == 3 + 2 + 7 + 2 + 2


def _csv(name):
    path = Path(__file__).resolve().parent.parent / "results" / name
    if not path.exists():
        pytest.skip(f"{name} has not been produced")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_published_min_max_runs_never_beat_the_published_bounds():
    published = {(r["k"], r["instance"]): r for r in _csv("mmwrpp_published_values.csv")}
    rows = _csv("k_published.csv")
    assert rows
    for r in rows:
        p = published[(r["k"], r["instance"])]
        longest = float(r["longest"])
        assert float(r["bound"]) <= longest + 1e-6
        if p["lower_bound"]:
            assert longest >= float(p["lower_bound"]) - 1e-6, (r["k"], r["instance"])
