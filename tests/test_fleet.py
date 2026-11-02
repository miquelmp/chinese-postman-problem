"""Several postmen and capacitated fleets: valid routes, bounds, and the exact optimum."""
import random
from pathlib import Path

import networkx as nx
import pytest

from chinese_postman import fleet, read_carp, rural

ROOT = Path(__file__).resolve().parents[1]


def random_net(seed, n=7, m=11, share=0.7):
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


def check_routes(G, routes, costs, depot):
    need = {}
    for u, v, d in G.edges(data=True):
        if d.get("required", True) and d.get("demand", 1) > 0:
            need[frozenset((u, v))] = need.get(frozenset((u, v)), 0) + 1
    seen = {}
    for r, c in zip(routes, costs):
        assert r[0] == depot and r[-1] == depot
        cost = 0.0
        for a, b in zip(r, r[1:]):
            assert G.has_edge(a, b)
            cost += min(d["weight"] for d in G[a][b].values())
            seen[frozenset((a, b))] = seen.get(frozenset((a, b)), 0) + 1
        assert cost <= c + 1e-6
    for key, n in need.items():
        assert seen.get(key, 0) >= n


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("k", [2, 3])
def test_heuristic_against_exact(seed, k):
    G = random_net(seed)
    sol = fleet.solve_k_postmen(G, k, depot=0, local_seconds=1.5)
    check_routes(G, sol.routes, sol.route_costs, 0)
    val, optimal, _ = fleet.solve_k_exact(G, k, depot=0, time_limit=90)
    if not optimal:
        pytest.skip("exact optimum not reached within the time limit")
    assert sol.lower_bound <= val + 1e-6 <= sol.max_cost + 2e-6


def test_one_postman_is_the_rural_postman():
    G = random_net(3, share=0.5)
    one = fleet.solve_k_postmen(G, 1, depot=0, local_seconds=1)
    single = rural.solve_rural(G, depot=0)
    assert one.max_cost == pytest.approx(single.total_cost)


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("k", [2, 3])
def test_split_of_optimal_tour_within_guarantee(seed, k):
    """Frederickson, Hecht & Kim: splitting an optimal single tour costs at most (2 - 1/k)
    times the optimum. With every street required the single tour is optimal (a CPP)."""
    G = random_net(50 + seed, share=1.0)
    sol = fleet.solve_k_postmen(G, k, depot=0, local_seconds=0.5)
    assert sol.info["single_optimal"]
    val, optimal, _ = fleet.solve_k_exact(G, k, depot=0, time_limit=90)
    if not optimal:
        pytest.skip("exact optimum not reached within the time limit")
    assert sol.info["split_max"] <= (2 - 1 / k) * val + 1e-6


def test_split_dp_is_optimal_over_cut_points():
    import itertools
    from chinese_postman.sequence import from_circuit, orient, route_cost
    G = read_carp(str(ROOT / "data" / "carp" / "gdb2.dat")).graph
    P = rural.Problem(G, 1)
    seq = orient(P, from_circuit(P, rural.solve_rural(G, depot=1).circuit))[:9]
    best = min(max(route_cost(P, seq[a:b]) for a, b in zip((0,) + cut, cut + (len(seq),)))
               for cut in itertools.combinations(range(1, len(seq)), 2))
    got = max(route_cost(P, r) for r in fleet.split_minmax(P, seq, 3))
    assert got == pytest.approx(best)


def test_carp_capacity_and_coverage():
    inst = read_carp(str(ROOT / "data" / "carp" / "gdb1.dat"))
    sol = fleet.solve_carp(inst.graph, inst.capacity, depot=1, local_seconds=1)
    check_routes(inst.graph, sol.routes, sol.route_costs, 1)
    assert sol.total_cost >= inst.lower_bound
    assert max(sol.info["loads"]) <= inst.capacity
    assert sum(sol.info["loads"]) == sum(d for *_, d in inst.graph.edges(data="demand"))
