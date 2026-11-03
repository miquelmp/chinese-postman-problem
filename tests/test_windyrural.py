"""The rural postman on windy, mixed and directed networks."""
import csv
import random
from collections import Counter
from pathlib import Path

import networkx as nx
import numpy as np
import pytest

from chinese_postman import instances as I
from chinese_postman import rural
from chinese_postman.windy import WindyGraph
from chinese_postman.windy import solve_exact as windy_exact
from chinese_postman.windyrural import (RuralProblem, lower_bound, read_directed, read_directed_general,
                                        read_instance, solve,
                                        solve_exact, solve_heuristic)


def walked(P, sol):
    """Walk the route; check it is closed and legal and serves every required link. Return its cost."""
    c = sol.circuit
    assert c[0] == c[-1]
    best = {}
    for u, v, a, b, _ in P.links:
        if a is not None:
            best[u, v] = min(a, best.get((u, v), a))
        if b is not None:
            best[v, u] = min(b, best.get((v, u), b))
    steps = Counter(zip(c, c[1:]))
    assert all(s in best for s in steps)
    seen = {frozenset(s) for s in steps}
    assert all(frozenset(l[:2]) in seen for l in P.links if l[4])
    return sum(best[s] * n for s, n in steps.items())


def small(seed, kind):
    rnd = random.Random(seed)
    while True:
        G = nx.gnm_random_graph(9, 16, seed=rnd.randrange(10 ** 6))
        if not nx.is_connected(G):
            continue
        links = []
        for u, v in G.edges:
            a, b, r = rnd.randint(1, 30), rnd.randint(1, 30), rnd.random() < 0.5
            if kind == "mixed" and rnd.random() < 0.4:
                b = None
            if kind == "directed":
                links.append((u, v, a, None, r))
                links.append((v, u, b, None, False))
            else:
                links.append((u, v, a, b, r))
        P = RuralProblem(links)
        if any(l[4] for l in links) and P.is_feasible():
            return P


def enumerate_optimum(P, most=2):
    """Try every number of passes up to `most` in each direction of a small network."""
    W = P.windy
    cols = [(k, a, b, c) for k in range(len(P.links)) for a, b, c in W.directions(k)]
    grid = np.indices((most + 1,) * len(cols), dtype=np.int8).reshape(len(cols), -1)
    ok = np.ones(grid.shape[1], bool)
    for v in W.nodes:
        out = sum(grid[j] for j, c in enumerate(cols) if c[1] == v)
        ins = sum(grid[j] for j, c in enumerate(cols) if c[2] == v)
        ok &= out == ins
    for k, l in enumerate(P.links):
        if l[4]:
            ok &= sum(grid[j] for j, c in enumerate(cols) if c[0] == k) >= 1
    best = None
    needed = {x for l in P.links if l[4] for x in l[:2]}
    idx = np.flatnonzero(ok)
    cost = sum(grid[j][idx].astype(np.int64) * c[3] for j, c in enumerate(cols))
    for i in np.argsort(cost):
        G = nx.Graph()
        G.add_edges_from((c[1], c[2]) for j, c in enumerate(cols) if grid[j][idx[i]])
        if needed <= set(G) and any(needed <= c for c in nx.connected_components(G)):
            return int(cost[i])
    return best


@pytest.mark.parametrize("seed", range(8))
def test_exact_equals_enumeration(seed):
    rnd = random.Random(seed)
    links = [(0, 1, rnd.randint(1, 9), rnd.randint(1, 9), True), (1, 2, rnd.randint(1, 9), rnd.randint(1, 9), False),
             (2, 0, rnd.randint(1, 9), rnd.randint(1, 9), False), (2, 3, rnd.randint(1, 9), rnd.randint(1, 9), True),
             (3, 4, rnd.randint(1, 9), rnd.randint(1, 9), False), (4, 2, rnd.randint(1, 9), rnd.randint(1, 9), True)]
    P = RuralProblem(links)
    sol = solve_exact(P)
    assert sol.optimal and sol.total_cost == enumerate_optimum(P)


@pytest.mark.parametrize("kind", ["windy", "mixed", "directed"])
@pytest.mark.parametrize("seed", range(6))
def test_bounds_and_routes(kind, seed):
    P = small(seed, kind)
    lp = lower_bound(P)
    opt = solve_exact(P)
    heur = solve_heuristic(P, local_seconds=2)
    assert lp[0] <= opt.total_cost + 1e-6 and opt.total_cost <= heur.total_cost
    assert walked(P, opt) <= opt.total_cost and walked(P, heur) <= heur.total_cost
    combined = solve(P, time_limit=30)
    assert combined.optimal and combined.total_cost == opt.total_cost


@pytest.mark.parametrize("seed", range(5))
def test_every_street_required_gives_the_windy_postman(seed):
    rnd = random.Random(seed)
    G = I.delaunay_town(40, seed=seed)
    links = [(u, v, rnd.randint(1, 50), rnd.randint(1, 50)) for u, v in G.edges()]
    assert solve_exact(RuralProblem([l + (True,) for l in links])).total_cost == windy_exact(WindyGraph(links)).total_cost


@pytest.mark.parametrize("seed", range(5))
def test_equal_costs_give_the_undirected_rural_postman(seed):
    rnd = random.Random(seed)
    G = nx.MultiGraph()
    for u, v, w in I.delaunay_town(40, seed=seed).edges(data="weight"):
        G.add_edge(u, v, weight=w, required=rnd.random() < 0.4)
    P = RuralProblem([(u, v, d["weight"], d["weight"], d["required"]) for u, v, d in G.edges(data=True)])
    assert solve_exact(P).total_cost == rural.solve_rural(G).total_cost


def test_depot_outside_the_required_streets_is_visited():
    P = RuralProblem([(1, 2, 3, 3, True), (2, 3, 4, 4, False), (3, 1, 5, 5, False)], depot=3)
    sol = solve_exact(P)
    assert 3 in sol.circuit and sol.total_cost == 12


def test_readers(tmp_path):
    p = tmp_path / "w"
    p.write_text("LISTA_ARISTAS_REQ :\n(1, 2) coste 3 5\nLISTA_ARISTAS_NOREQ :\n(2, 3) coste 99999999 7\n", encoding="latin-1")
    assert read_instance(p).links == [(1, 2, 3, 5, True), (2, 3, None, 7, False)]
    q = tmp_path / "d"
    q.write_text("3\n1\n2\n1\n2\n1, 2, 37 ,1\n2, 1, 8 ,0\n", encoding="latin-1")
    assert read_directed(q).links == [(1, 2, 37, None, True), (2, 1, 8, None, False)]


def _csv(name):
    path = Path(__file__).resolve().parent.parent / "results" / name
    if not path.exists():
        pytest.skip(f"{name} has not been produced")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_measured_runs_agree_with_their_bounds_and_with_published_values():
    published = {r["instance"].lower(): r for r in _csv("wrpp_published_values.csv")}
    rows = _csv("rural_general.csv")
    assert rows
    for r in rows:
        best, bound = float(r["best"]), float(r["bound"])
        assert bound <= best + 1e-6 and best <= float(r["heuristic"]) + 1e-6
        if r["optimal"] == "True":
            assert abs(best - bound) <= 1e-6 * max(1.0, best) + 0.51
        p = published.get(r["instance"].lower())
        if r["family"] == "windy" and p:
            assert best >= float(p["lower_bound"]) - 1e-6
            if r["optimal"] == "True" and p["status"] == "optimal":
                assert abs(best - float(p["upper_bound"])) < 1e-6


@pytest.mark.parametrize("name", ["rural_general.csv", "rural_mixed_long.csv"])
def test_mixed_results_agree_with_the_published_optima(name):
    published = {r["instance"]: float(r["upper_bound"]) for r in _csv("mrpp_published_values.csv")}
    rows = [r for r in _csv(name) if r["instance"] in published and r.get("family", "mixed") == "mixed"]
    assert rows
    for r in rows:
        optimum = published[r["instance"]]
        assert float(r["bound"]) <= optimum + 1e-6 <= float(r["best"]) + 2e-6
        if r["optimal"] == "True":
            assert float(r["best"]) == optimum


DIRECTED = """NOMBRE: test
VERTICES: 4
ARCOS_REQ: 1
ARCOS_NOREQ: 4
VERTICES_REQ: 1
LIST OF ARCS:
(1,2) coste 5
ARCOS_NOREQ:
(2,1) coste 1 -1
(2,3) coste 2 -1
(3,1) coste 2 -1
(2,4) coste 7 -1
(4,1) coste 7 -1
VERT_REQ:
3
"""


def test_directed_general_reader_and_required_vertices(tmp_path):
    path = tmp_path / "x.dat"
    path.write_text(DIRECTED, encoding="latin-1")
    P = read_directed_general(str(path))
    assert P.vertices == (3,) and len(P.links) == 6 and sum(l[4] for l in P.links) == 1
    assert solve_exact(P).total_cost == 9                 # 1, 2, 3, 1, not the shorter 1, 2, 1
    sol = solve(P)
    assert sol.optimal and sol.total_cost == 9 and 3 in sol.circuit
    free = RuralProblem(P.links)
    assert solve(free).total_cost == 6


def test_files_without_a_list_of_vertices_require_all_of_them(tmp_path):
    path = tmp_path / "x.dat"
    path.write_text(DIRECTED.replace("VERTICES_REQ: 1\n", "").replace("VERT_REQ:\n3\n", ""), encoding="latin-1")
    assert read_directed_general(str(path)).vertices == (1, 2, 3, 4)


def test_directed_results_agree_with_the_published_values():
    rows = _csv("directed_published.csv") + _csv("dgrp_lap.csv")
    assert rows
    for r in rows:
        published = float(r["published"])
        if r["bound"]:
            assert float(r["bound"]) <= published + 1e-6
        if r["best"]:
            assert float(r["best"]) >= published - 1e-6
            if r["optimal"] == "True":
                assert float(r["best"]) == published
