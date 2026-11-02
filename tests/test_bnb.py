"""The branch-and-bound of section 8.3: faithful to the 1997 trace, and exact."""
import itertools
import random

import networkx as nx
import numpy as np
import pytest

from chinese_postman import read_gra
from chinese_postman.bnb import bound_of, branch_and_bound, greedy_pairing
from chinese_postman.cpp import min_weight_pairing

VARIANTS = [dict(bound="1997"), dict(bound="tight"),
            dict(bound="tight", branch="constrained", start=True)]


def example_matrix():
    G = nx.Graph()
    for u, v, w in read_gra("examples/example_1997.gra").edges(data="weight"):
        G.add_edge(u, v, weight=w)
    odd = [1, 3, 4, 6]
    d = dict(nx.all_pairs_dijkstra_path_length(G))
    return np.array([[d[u][v] for v in odd] for u in odd])


def test_bounds_of_the_1997_worked_example():
    """Nodes 0 to 4 of section 9.2.6 of the 1997 report: bounds 8, 15, 9, 9, 13."""
    D = example_matrix()
    i4, i6, i3, i1 = 2, 3, 1, 0
    a = ~np.eye(4, dtype=bool)
    assert bound_of(D, a, 0, 2) == 8
    take = a.copy()
    take[[i4, i6], :] = False
    take[:, [i4, i6]] = False
    assert bound_of(D, take, 3, 2) == 15
    rej = a.copy()
    rej[i4, i6] = rej[i6, i4] = False
    assert bound_of(D, rej, 0, 2) == 9
    take2 = rej.copy()
    take2[[i3, i6], :] = False
    take2[:, [i3, i6]] = False
    assert bound_of(D, take2, 4, 2) == 9
    rej2 = rej.copy()
    rej2[i3, i6] = rej2[i6, i3] = False
    assert bound_of(D, rej2, 0, 2) == 13


@pytest.mark.parametrize("kw", VARIANTS)
def test_worked_example_optimum(kw):
    r = branch_and_bound(example_matrix(), **kw)
    assert r.proven and r.cost == 9


@pytest.mark.parametrize("kw", VARIANTS)
@pytest.mark.parametrize("seed", range(10))
def test_matches_blossom_on_random_metrics(kw, seed):
    rnd = random.Random(seed)
    t = rnd.choice([4, 6, 8, 10])
    G = nx.gnm_random_graph(t + 6, 3 * t, seed=seed)
    G = nx.compose(G, nx.path_graph(t + 6))
    for u, v in G.edges:
        G[u][v]["weight"] = rnd.randint(1, 30)
    verts = rnd.sample(list(G), t)
    d = dict(nx.all_pairs_dijkstra_path_length(G))
    D = np.array([[d[u][v] for v in verts] for u in verts])
    r = branch_and_bound(D, **kw)
    best = sum(d[u][v] for u, v in min_weight_pairing(verts, {(u, v): d[u][v] for u in verts for v in verts}))
    assert r.proven and r.cost == best
    assert sorted(itertools.chain(*r.pairs)) == list(range(t))
    assert sum(D[p] for p in r.pairs) == r.cost


def test_node_limit_is_strict_and_reported():
    rnd = random.Random(1)
    D = np.zeros((12, 12), dtype=np.int64)
    for i, j in itertools.combinations(range(12), 2):
        D[i, j] = D[j, i] = rnd.randint(1, 50)
    r = branch_and_bound(D, bound="1997", max_nodes=5)
    assert r.explored == 5 and not r.proven


def test_greedy_pairing_is_perfect():
    D = example_matrix()
    assert sorted(itertools.chain(*greedy_pairing(D))) == [0, 1, 2, 3]
