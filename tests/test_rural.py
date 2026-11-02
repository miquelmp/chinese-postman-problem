"""Rural postman and two-cost streets: exact against brute force, bounds, valid tours."""
import itertools
import random
from pathlib import Path

import networkx as nx
import pytest

from chinese_postman import read_carp, rural, solve_undirected

ROOT = Path(__file__).resolve().parents[1]


def random_rural(seed, n=7, m=10, share=0.4):
    rng = random.Random(seed)
    while True:
        g = nx.gnm_random_graph(n, m, seed=rng.randrange(10 ** 9))
        if nx.is_connected(g):
            break
    G = nx.MultiGraph()
    for u, v in g.edges():
        G.add_edge(u, v, weight=rng.randint(1, 9), required=rng.random() < share)
    if not any(d["required"] for *_, d in G.edges(data=True)):
        u, v, k = next(iter(G.edges(keys=True)))
        G[u][v][k]["required"] = True
    return G


def brute_force_original(G, depot):
    """Enumerate 0..2 extra passes over every street of the original graph."""
    E = list(G.edges(data=True))
    best = float("inf")
    for xs in itertools.product((0, 1, 2), repeat=len(E)):
        deg = dict.fromkeys(G, 0)
        H = nx.Graph()
        H.add_node(depot)
        cost = 0
        for (u, v, d), x in zip(E, xs):
            k = x + (1 if d["required"] else 0)
            if k:
                deg[u] += k; deg[v] += k
                H.add_edge(u, v)
            cost += x * d["weight"] + (d.get("service", d["weight"]) if d["required"] else 0)
        if cost < best and not any(x % 2 for x in deg.values()) and nx.is_connected(H):
            best = cost
    return best


def check_tour(G, sol, depot):
    c = sol.circuit
    assert c[0] == depot and c[-1] == depot
    need = {}
    for u, v, d in G.edges(data=True):
        if d.get("required", True):
            need[frozenset((u, v))] = need.get(frozenset((u, v)), 0) + 1
    seen, cost = {}, 0.0
    for a, b in zip(c, c[1:]):
        assert G.has_edge(a, b), f"no street {a}-{b}"
        key = frozenset((a, b))
        seen[key] = seen.get(key, 0) + 1
        cost += min(d["weight"] for d in G[a][b].values())
    for key, n in need.items():
        assert seen.get(key, 0) >= n, f"street {set(key)} not served"
    assert cost <= sol.total_cost + 1e-6       # service = weight in these tests


@pytest.mark.parametrize("seed", range(12))
def test_exact_matches_brute_force(seed):
    G = random_rural(seed)
    depot = next((u for u, v, d in G.edges(data=True) if d["required"]))
    sol = rural.solve_rural(G, depot=depot, time_limit=30)
    assert sol.optimal
    assert sol.total_cost == pytest.approx(brute_force_original(G, depot))
    assert sol.lower_bound <= sol.total_cost + 1e-6
    check_tour(G, sol, depot)


@pytest.mark.parametrize("seed", range(20))
def test_frederickson_within_three_halves(seed):
    G = random_rural(100 + seed, n=9, m=15, share=0.35)
    sol = rural.solve_rural(G, time_limit=30)
    assert sol.optimal
    assert sol.info.get("frederickson", sol.total_cost) <= 1.5 * sol.total_cost + 1e-6


def test_all_required_equals_cpp():
    G = read_carp(str(ROOT / "data" / "carp" / "gdb1.dat")).graph
    sol = rural.solve_rural(G, depot=1)
    assert sol.method.startswith("matching") and sol.optimal
    assert sol.total_cost == solve_undirected(G).total_cost == 294


def test_two_costs_is_service_plus_cpp_on_travel_costs():
    G = read_carp(str(ROOT / "data" / "carp" / "gdb1.dat")).graph
    H = nx.MultiGraph()
    for u, v, d in G.edges(data=True):
        H.add_edge(u, v, weight=d["weight"], service=3 * d["weight"])
    sol = rural.solve_two_costs(H, start=1)
    cpp = solve_undirected(G)
    assert sol.total_cost == pytest.approx(3 * cpp.original_cost + cpp.added_cost)
    D = nx.MultiDiGraph()
    D.add_edge(1, 2, weight=2, service=5); D.add_edge(2, 3, weight=2, service=5)
    D.add_edge(3, 1, weight=2, service=5); D.add_edge(1, 3, weight=4, service=9)
    total, _ = rural.solve_two_costs(D, start=1)
    assert total == 5 + 5 + 5 + 9 + 2      # the extra pass 3->1 costs only its travel time


def test_eglese_rural_benchmark():
    inst = read_carp(str(ROOT / "data" / "carp" / "egl-s1-A.dat"))
    G = inst.graph
    for *_, d in G.edges(data=True):
        d["required"] = d["demand"] > 0
    sol = rural.solve_rural(G, depot=1, time_limit=60)
    assert sol.optimal and sol.total_cost == 2538
    check_tour(G, sol, 1)


def test_disconnected_required_reported():
    G = nx.MultiGraph()
    G.add_edge(1, 2, weight=1, required=True)
    G.add_edge(3, 4, weight=1, required=True)
    with pytest.raises(ValueError):
        rural.solve_rural(G, depot=1)
