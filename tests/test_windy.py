"""The windy postman: agreement with enumeration and with its special cases."""
import csv
import itertools
import random
from collections import Counter
from pathlib import Path

import networkx as nx
import numpy as np
import pytest

from chinese_postman import instances as I
from chinese_postman import solve_undirected
from chinese_postman.mixed import MixedGraph, solve_exact as mixed_exact
from chinese_postman.mixed import from_graph as mixed_from_graph
from chinese_postman.windy import (WindyGraph, bounds, from_graph, from_mixed, read_wpp, solve_exact,
                                   solve_heuristic, solve_win, solve_windy)


def cost_of(W, sol):
    """Walk the tour; check it is closed, legal and covers every link. Return its cheapest cost."""
    c = sol.circuit
    assert c[0] == c[-1]
    steps = Counter(zip(c, c[1:]))
    best, covered = {}, Counter()
    for k in range(len(W.links)):
        for a, b, w in W.directions(k):
            best[a, b] = min(w, best.get((a, b), w))
    assert all(s in best for s in steps)
    pairs = Counter(frozenset(s) for s in steps.elements())
    for u, v, *_ in W.links:
        covered[frozenset((u, v))] += 1
    assert all(pairs[p] >= n for p, n in covered.items())
    return sum(best[s] * n for s, n in steps.items())


def enumerate_optimum(W, most=3):
    """Try every number of passes up to `most` in each direction of each link."""
    cols = [(k, a, b, c) for k in range(len(W.links)) for a, b, c in W.directions(k)]
    grid = np.indices((most + 1,) * len(cols), dtype=np.int16).reshape(len(cols), -1)
    idx = {v: i for i, v in enumerate(W.nodes)}
    ok = np.ones(grid.shape[1], bool)
    for v in idx:
        out = sum(grid[j] for j, (_, a, _, _) in enumerate(cols) if a == v)
        ins = sum(grid[j] for j, (_, _, b, _) in enumerate(cols) if b == v)
        ok &= out == ins
    for k in range(len(W.links)):
        ok &= sum(grid[j] for j, c in enumerate(cols) if c[0] == k) >= 1
    cost = sum(grid[j].astype(np.int64) * c[3] for j, c in enumerate(cols))
    return int(cost[ok].min())


def small(seed):
    rnd = random.Random(seed)
    while True:
        G = nx.gnm_random_graph(4, 5, seed=rnd.randrange(10 ** 6))
        if nx.is_connected(G):
            return WindyGraph([(u, v, rnd.randint(1, 20), rnd.randint(1, 20)) for u, v in G.edges])


@pytest.mark.parametrize("seed", range(12))
def test_exact_equals_enumeration(seed):
    W = small(seed)
    sol = solve_exact(W)
    assert sol.optimal and sol.total_cost == enumerate_optimum(W)
    assert cost_of(W, sol) <= sol.total_cost


@pytest.mark.parametrize("seed", range(12))
def test_order_of_bounds_and_tours(seed):
    W = from_graph(I.delaunay_town(60, seed=seed), 0.3, seed)
    lb, lp, und, _ = bounds(W)
    opt = solve_exact(W)
    heur = solve_heuristic(W)
    win = solve_win(W)
    assert lb <= opt.total_cost + 1e-6 and opt.total_cost <= heur.total_cost <= win.total_cost
    assert win.total_cost <= 2 * opt.total_cost
    assert cost_of(W, heur) <= heur.total_cost
    assert cost_of(W, win) <= win.total_cost


@pytest.mark.parametrize("seed", range(6))
def test_equal_costs_give_the_undirected_postman(seed):
    G = I.delaunay_town(80, seed=seed)
    W = WindyGraph([(u, v, c, c) for u, v, c in G.edges(data="weight")])
    assert solve_exact(W).total_cost == solve_undirected(G).total_cost


@pytest.mark.parametrize("seed", range(6))
def test_forbidden_directions_give_the_mixed_postman(seed):
    M = mixed_from_graph(I.delaunay_town(80, seed=seed), 0.4, seed)
    W = from_mixed(M)
    assert solve_exact(W).total_cost == mixed_exact(M).total_cost
    assert solve_heuristic(W).total_cost >= mixed_exact(M).total_cost


@pytest.mark.parametrize("seed", range(6))
def test_win_is_optimal_on_eulerian_networks(seed):
    rnd = random.Random(seed)
    G = nx.circulant_graph(12, [1, 3])
    W = WindyGraph([(u, v, rnd.randint(1, 30), rnd.randint(1, 30)) for u, v in G.edges])
    assert solve_win(W).total_cost == solve_exact(W).total_cost
    assert bounds(W)[1] == pytest.approx(solve_exact(W).total_cost)


@pytest.mark.parametrize("seed", range(6))
def test_combined_method_proves_the_optimum(seed):
    W = from_graph(I.delaunay_town(60, seed=seed), 0.3, seed)
    sol = solve_windy(W)
    assert sol.optimal and sol.total_cost == solve_exact(W).total_cost
    assert cost_of(W, sol) <= sol.total_cost


def test_win_needs_both_directions():
    with pytest.raises(ValueError):
        solve_win(WindyGraph([(1, 2, 3, None), (2, 1, 4, None)]))


def test_read_wpp(tmp_path):
    p = tmp_path / "w"
    p.write_text("NOMBRE : t\nLISTA_ARISTAS_REQ :\n(   1,   2)   coste  3  5\n(2, 3) coste 99999999 7\n"
                 "(3, 1) coste 2 2\n", encoding="latin-1")
    assert read_wpp(p).links == [(1, 2, 3, 5), (2, 3, None, 7), (3, 1, 2, 2)]


def test_measured_windy_results_agree_with_published_values():
    root = Path(__file__).parent.parent / "results"
    published = {r["instance"]: r for r in csv.DictReader(open(root / "wpp_published_values.csv"))}
    assert len(published) == 120
    for r in csv.DictReader(open(root / "windy_published.csv")):
        p = published[r["instance"]]
        assert float(r["best"]) >= float(p["lower_bound"]) - 1e-3
        if p["status"] == "optimal":
            assert float(r["bound"]) <= float(p["upper_bound"]) + 1e-3
            if r["optimal"] == "True":
                assert float(r["best"]) == float(p["upper_bound"])
