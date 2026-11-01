import random
from collections import Counter
from pathlib import Path

import networkx as nx
import pytest

from chinese_postman import read_gra, solve_directed, solve_undirected
from chinese_postman import instances as I
from chinese_postman.mixed import (MixedGraph, bounds, city_grid, from_graph, solve_brute_force,
                           solve_exact, solve_heuristic)

ROOT = Path(__file__).parent.parent


def check_mixed_tour(M, sol):
    """Closed walk; one-way links only forwards; every link covered; cost adds up."""
    c = sol.circuit
    assert c[0] == c[-1]
    steps = Counter(zip(c, c[1:]))
    allowed = {}
    for u, v, w, one in M.links:
        for a, b in ((u, v),) if one else ((u, v), (v, u)):
            allowed[a, b] = min(w, allowed.get((a, b), w))
    assert all(s in allowed for s in steps)
    left = Counter()
    for u, v, w, one in M.links:            # each link needs one traversal of its own
        left[(u, v, one)] += 1
    for (a, b), n in steps.items():
        for _ in range(n):
            if left[(a, b, True)] > 0:
                left[(a, b, True)] -= 1
            elif left[(a, b, False)] > 0:
                left[(a, b, False)] -= 1
            elif left[(b, a, False)] > 0:
                left[(b, a, False)] -= 1
    assert sum(left.values()) == 0
    assert len(c) - 1 == sum(n for *_, n in sol.traversals)


def small_mixed(seed):
    rnd = random.Random(seed)
    while True:
        H = nx.gnm_random_graph(7, 12, seed=rnd.randint(0, 10**6))
        if nx.is_connected(H):
            break
    G = nx.MultiGraph()
    for u, v in H.edges:
        G.add_edge(u, v, weight=rnd.randint(1, 20))
    return from_graph(G, oneway_frac=0.5, seed=seed)


@pytest.mark.parametrize("seed", range(25))
def test_exact_and_heuristic_against_brute_force(seed):
    M = small_mixed(seed)
    opt = solve_brute_force(M)
    ex = solve_exact(M)
    he = solve_heuristic(M)
    lb = bounds(M)[0]
    assert ex.optimal and ex.total_cost == opt
    assert lb <= opt + 1e-9
    assert he.total_cost >= opt - 1e-9
    check_mixed_tour(M, ex)
    check_mixed_tour(M, he)


def test_all_two_way_equals_undirected_cpp():
    G = read_gra(ROOT / "examples" / "example_1997.gra")
    M = MixedGraph([(u, v, w, False) for u, v, w in G.edges(data="weight")])
    assert solve_exact(M).total_cost == solve_heuristic(M).total_cost == 63


def test_all_one_way_equals_directed_cpp():
    D = I.one_way_grid(6, 7)
    M = MixedGraph([(u, v, w, True) for u, v, w in D.edges(data="weight")])
    expected = solve_directed(D).total_cost
    assert solve_exact(M).total_cost == expected
    assert solve_heuristic(M).total_cost == expected


@pytest.mark.parametrize("seed", range(3))
def test_city_grid_is_feasible_and_bounded(seed):
    M = city_grid(6, 7, seed=seed)
    assert M.is_feasible()
    ex, he = solve_exact(M), solve_heuristic(M)
    assert he.lower_bound <= ex.total_cost <= he.total_cost
    check_mixed_tour(M, he)


# ---------------------------------------------------------------- combined strategy
from chinese_postman.mixed import solve_mixed


@pytest.mark.parametrize("seed", range(8))
def test_combined_matches_exact(seed):
    M = small_mixed(100 + seed)
    r = solve_mixed(M, time_limit=60)
    assert r.optimal and r.total_cost == solve_brute_force(M)
    check_mixed_tour(M, r)


def test_combined_proves_heuristic_optimal_by_cutoff():
    """Here the heuristic is already optimal but the cheap bounds cannot show it: branch-and-cut
    must find the 'cheaper than heuristic' model infeasible."""
    M = city_grid(8, 8, seed=0)
    r = solve_mixed(M, time_limit=120)
    assert r.optimal and r.total_cost == solve_exact(M).total_cost
    assert r.info["phase_bound"] == "cutoff infeasible"
    check_mixed_tour(M, r)


def test_combined_respects_tolerance():
    M = city_grid(12, 12, seed=0)
    r = solve_mixed(M, time_limit=120, gap_tol=0.005)
    assert r.lower_bound <= r.total_cost <= r.lower_bound * 1.005 + 1
    check_mixed_tour(M, r)


def test_combined_all_two_way_proven_by_bound():
    G = read_gra(ROOT / "examples" / "example_1997.gra")
    M = MixedGraph([(u, v, w, False) for u, v, w in G.edges(data="weight")])
    r = solve_mixed(M)
    assert r.optimal and r.total_cost == 63 and not r.info["exact_ran"]
