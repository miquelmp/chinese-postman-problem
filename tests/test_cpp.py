import glob
import itertools
import random
from collections import Counter
from pathlib import Path

import networkx as nx
import pytest

from chinese_postman import read_carp, read_gra, solve_directed, solve_undirected
from chinese_postman import instances as I

ROOT = Path(__file__).parent.parent


def check_tour(G, sol):
    """Closed walk, every original edge covered, length = edges + duplicates."""
    c = sol.circuit
    assert c[0] == c[-1]
    key = (lambda a, b: (a, b)) if G.is_directed() else (lambda a, b: frozenset((a, b)))
    used = Counter(key(a, b) for a, b in zip(c, c[1:]))
    need = Counter(key(a, b) for a, b in G.edges())
    assert all(used[k] >= n for k, n in need.items())
    assert len(c) - 1 == G.number_of_edges() + len(sol.duplicated)


def brute_force_added(G):
    """Cheapest pairing of odd vertices by enumeration (only for tiny cases)."""
    odd = [v for v in G if G.degree(v) % 2]
    d = dict(nx.all_pairs_dijkstra_path_length(nx.Graph(G)))

    def best(rest):
        if not rest:
            return 0
        a = rest[0]
        return min(d[a][b] + best([x for x in rest[1:] if x != b]) for b in rest[1:])
    return best(odd)


def test_1997_example():
    G = read_gra(ROOT / "examples" / "example_1997.gra")
    sol = solve_undirected(G, start=1)
    assert (sol.original_cost, sol.added_cost, sol.total_cost) == (54, 9, 63)
    assert {frozenset(p) for p in sol.pairs} == {frozenset({1, 4}), frozenset({3, 6})}
    check_tour(G, sol)


@pytest.mark.parametrize("build, odd, added", [
    (I.konigsberg, 4, 2),       # cross 2 bridges twice: 9 crossings in total
    (I.petersen, 10, 5),        # Petersen has a perfect matching of 5 edges
    (I.dodecahedron, 20, 10),
])
def test_classic_graphs(build, odd, added):
    G = build()
    sol = solve_undirected(G)
    assert sol.odd_vertices == odd
    assert sol.added_cost == added
    check_tour(G, sol)


@pytest.mark.parametrize("seed", range(30))
def test_against_brute_force(seed):
    rnd = random.Random(seed)
    while True:
        H = nx.gnm_random_graph(9, 14, seed=rnd.randint(0, 10**6))
        if nx.is_connected(H) and sum(H.degree(v) % 2 for v in H) <= 8:
            break
    G = nx.MultiGraph()
    for u, v in H.edges:
        G.add_edge(u, v, weight=rnd.randint(1, 30))
    sol = solve_undirected(G)
    assert sol.added_cost == brute_force_added(G)
    check_tour(G, sol)


def test_parallel_edges():
    G = nx.MultiGraph()
    G.add_edge(1, 2, weight=3)
    G.add_edge(1, 2, weight=5)
    G.add_edge(2, 3, weight=1)
    sol = solve_undirected(G)
    assert sol.added_cost == 1
    check_tour(G, sol)


def test_generators_produce_valid_tours():
    for G in (I.manhattan(6, 8, drop=0.15, seed=1), I.delaunay_town(120, seed=2)):
        check_tour(G, solve_undirected(G))


def test_directed():
    G = nx.MultiDiGraph()
    for u, v, w in [(1, 2, 1), (2, 3, 1), (3, 1, 1), (1, 3, 5), (3, 4, 2), (4, 1, 2), (1, 4, 3)]:
        G.add_edge(u, v, weight=w)
    sol = solve_directed(G, start=1)
    assert sol.added_cost == 2      # repeat 4 -> 1
    check_tour(G, sol)


def test_one_way_grid():
    G = I.one_way_grid(6, 7)
    assert nx.is_strongly_connected(G)
    check_tour(G, solve_directed(G))


@pytest.mark.parametrize("path", sorted(glob.glob(str(ROOT / "data" / "carp" / "gdb*.dat"))))
def test_gdb_cpp_below_carp_bound(path):
    """In gdb every edge is required, so any CARP solution is a postman tour:
    the CPP optimum can never exceed the published CARP lower bound."""
    inst = read_carp(path)
    assert inst.required == inst.graph.number_of_edges()
    sol = solve_undirected(inst.graph, start=1)
    check_tour(inst.graph, sol)
    assert sol.total_cost <= inst.lower_bound


# ---------------------------------------------------------------- LEMON backend
from chinese_postman import fast

needs_lemon = pytest.mark.skipif(not fast.available(), reason="native/liblemon_match.so not built")


@needs_lemon
@pytest.mark.parametrize("path", sorted(glob.glob(str(ROOT / "data" / "carp" / "*.dat")))[::5])
def test_lemon_matches_networkx_on_benchmarks(path):
    G = read_carp(path).graph
    a = solve_undirected(G, start=1)
    b = solve_undirected(G, start=1, backend="lemon")
    assert a.total_cost == b.total_cost
    check_tour(G, b)


@needs_lemon
@pytest.mark.parametrize("seed", range(4))
def test_lemon_pricing_with_tiny_candidate_set(seed):
    """k=1 forces many pricing rounds; the result must still be optimal."""
    G = I.delaunay_town(300, seed=seed)
    sol = fast.solve_undirected_fast(G, k=1)
    assert sol.matching_stats["rounds"] >= 2
    assert sol.total_cost == solve_undirected(G).total_cost
    check_tour(G, sol)


@needs_lemon
@pytest.mark.parametrize("seed", range(4))
def test_lemon_duals_certify_the_matching(seed):
    """The certificate must hold and give the same cost as an independent complete-graph solve."""
    G = I.delaunay_town(200, seed=seed)
    sol = fast.solve_undirected_fast(G)
    assert sol.matching_stats["certified_cost"] == sol.added_cost
    assert sol.total_cost == solve_undirected(G).total_cost
