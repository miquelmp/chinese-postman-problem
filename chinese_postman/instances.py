"""Test instances that are not taken from the 1997 Vilanova case studies."""
from __future__ import annotations

import math
import random

import networkx as nx


def konigsberg() -> nx.MultiGraph:
    """Euler's seven bridges (1736): A = Kneiphof island, B/C = river banks, D = east.
    Costs are 1 per bridge, so the answer counts bridge crossings."""
    G = nx.MultiGraph()
    for u, v in [("A", "B"), ("A", "B"), ("A", "C"), ("A", "C"), ("A", "D"), ("B", "D"), ("C", "D")]:
        G.add_edge(u, v, weight=1)
    return G


def unit(G: nx.Graph) -> nx.MultiGraph:
    """Copy a simple graph as a multigraph with every cost equal to 1."""
    M = nx.MultiGraph()
    M.add_edges_from(G.edges, weight=1)
    return M


def petersen() -> nx.MultiGraph:
    """The Petersen graph with unit costs."""
    return unit(nx.petersen_graph())


def dodecahedron() -> nx.MultiGraph:
    """The dodecahedral graph with unit costs."""
    return unit(nx.dodecahedral_graph())


def manhattan(rows: int, cols: int, block: int = 80, avenue: int = 270, drop: float = 0.0,
              seed: int = 0) -> nx.MultiGraph:
    """Grid street plan: short blocks along streets, long ones along avenues (metres).
    `drop` removes a fraction of segments (parks, closed streets), keeping connectivity."""
    rnd = random.Random(seed)
    G = nx.grid_2d_graph(rows, cols)
    for (a, b) in list(G.edges):
        if drop and rnd.random() < drop:
            G.remove_edge(a, b)
            if not nx.is_connected(G):
                G.add_edge(a, b)
    M = nx.MultiGraph()
    idx = {v: i + 1 for i, v in enumerate(sorted(G))}
    for a, b in G.edges:
        M.add_edge(idx[a], idx[b], weight=avenue if a[0] != b[0] else block)
    return M


def delaunay_town(n: int, seed: int = 0, keep: float = 0.75, spacing: float = 100.0) -> nx.MultiGraph:
    """Organic street network: Delaunay triangulation of random points, thinned to `keep` of its
    edges (shortest first kept), Euclidean lengths in metres, at least 1. The square grows with n,
    with a side of spacing * sqrt(n), so the density of junctions stays the same at any size."""
    from scipy.spatial import Delaunay
    rnd = random.Random(seed)
    side = spacing * math.sqrt(n)
    pts = [(rnd.random() * side, rnd.random() * side) for _ in range(n)]
    tri = Delaunay(pts)
    E = set()
    for s in tri.simplices:
        for i in range(3):
            a, b = sorted((int(s[i]), int(s[(i + 1) % 3])))
            E.add((a, b))
    L = {e: math.dist(pts[e[0]], pts[e[1]]) for e in E}
    G = nx.Graph()
    G.add_nodes_from(range(n))
    T = nx.Graph()
    T.add_weighted_edges_from((a, b, L[a, b]) for a, b in E)
    for a, b in nx.minimum_spanning_edges(T, data=False):   # stay connected
        G.add_edge(a, b)
    m = G.number_of_edges()
    for e in sorted(E, key=L.get):
        if m >= keep * len(E):
            break
        if not G.has_edge(*e):
            G.add_edge(*e)
            m += 1
    M = nx.MultiGraph()
    for a, b in G.edges:
        M.add_edge(a + 1, b + 1, weight=max(1, round(L[min(a, b), max(a, b)])))
    for v in M:
        M.nodes[v]["pos"] = pts[v - 1]
    return M


def one_way_grid(rows: int, cols: int, block: int = 80, seed: int = 0) -> nx.MultiDiGraph:
    """Directed grid: inner streets and avenues are one-way with alternating directions
    (like Manhattan); the outer ring and every fourth street are two-way."""
    G = nx.MultiDiGraph()
    idx = lambda r, c: r * cols + c + 1
    rnd = random.Random(seed)

    def add(a, b, w, mode):          # mode: +1 forward, -1 backward, 0 two-way
        if mode >= 0:
            G.add_edge(a, b, weight=w)
        if mode <= 0:
            G.add_edge(b, a, weight=w)

    for r in range(rows):
        for c in range(cols - 1):
            two = r in (0, rows - 1) or r % 4 == 3
            add(idx(r, c), idx(r, c + 1), block + rnd.randint(-10, 10),
                0 if two else (1 if r % 2 == 0 else -1))
    for c in range(cols):
        for r in range(rows - 1):
            two = c in (0, cols - 1)
            add(idx(r, c), idx(r + 1, c), 3 * block + rnd.randint(-20, 20),
                0 if two else (1 if c % 2 == 0 else -1))
    return G
