"""Chinese Postman Problem: undirected (Edmonds' method) and directed (min-cost flow).

    sol = solve_undirected(G)   # G: nx.MultiGraph with 'weight' on every edge
    sol = solve_directed(G)     # G: nx.MultiDiGraph, strongly connected
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field

import networkx as nx

from .euler import eulerian_circuit


@dataclass
class CPPSolution:
    """A postman tour with its cost breakdown, duplicated edges and time per phase."""
    original_cost: float
    added_cost: float
    total_cost: float
    duplicated: list            # (u, v, cost) edges traversed a second time
    circuit: list               # vertex sequence, first == last
    odd_vertices: int = 0
    pairs: list = field(default_factory=list)
    seconds: dict = field(default_factory=dict)   # time per phase

    def summary(self) -> str:
        """Return a readable report of the solution."""
        t = ", ".join(f"{k} {v:.3f} s" for k, v in self.seconds.items())
        return "\n".join([
            f"Original cost:   {self.original_cost}",
            f"Added cost:      {self.added_cost}",
            f"Total cost:      {self.total_cost}",
            f"Odd vertices:    {self.odd_vertices}",
            f"Duplicated edges:{len(self.duplicated)}",
            f"Time:            {t}",
            "Circuit: " + " - ".join(map(str, self.circuit)),
        ])


def _simple(G):
    """Simple graph keeping the cheapest of any parallel edges."""
    H = nx.DiGraph() if G.is_directed() else nx.Graph()
    H.add_nodes_from(G)
    for u, v, w in G.edges(data="weight"):
        if u != v and (not H.has_edge(u, v) or H[u][v]["weight"] > w):
            H.add_edge(u, v, weight=w)
    return H


def min_weight_pairing(odd, D):
    """Minimum-weight perfect matching on the complete graph over `odd` (Edmonds' blossom)."""
    K = nx.Graph()
    for u, v in itertools.combinations(odd, 2):
        K.add_edge(u, v, weight=D[u, v])
    return [tuple(p) for p in nx.min_weight_matching(K)]


def solve_undirected(G: nx.MultiGraph, start=None, backend: str = "networkx") -> CPPSolution:
    """backend: "networkx" (pure Python, any costs), "lemon" (needs native/liblemon_match.so,
    integer costs) or "auto" (lemon when built and costs are integers, else networkx)."""
    if backend in ("auto", "lemon"):
        from . import fast
        ints = all(float(w).is_integer() for *_, w in G.edges(data="weight"))
        if backend == "lemon" or (fast.available() and ints):
            return fast.solve_undirected_fast(G, start=start)
    if G.number_of_edges() == 0:
        raise ValueError("Graph has no edges")
    core = G.subgraph([v for v in G if G.degree(v) > 0])
    if not nx.is_connected(core):
        raise ValueError("Graph must be connected")
    secs = {}
    H = _simple(G)
    odd = [v for v in G if G.degree(v) % 2]
    original = sum(w for _, _, w in G.edges(data="weight"))

    t = time.perf_counter()
    D, path = {}, {}
    for u in odd:
        dist, paths = nx.single_source_dijkstra(H, u, weight="weight")
        for v in odd:
            D[u, v], path[u, v] = dist[v], paths[v]
    secs["shortest paths"] = time.perf_counter() - t

    t = time.perf_counter()
    pairs = min_weight_pairing(odd, D) if odd else []
    secs["matching"] = time.perf_counter() - t

    t = time.perf_counter()
    E = nx.MultiGraph(G)
    dup = []
    for u, v in pairs:
        p = path[u, v]
        for a, b in zip(p, p[1:]):
            w = H[a][b]["weight"]
            E.add_edge(a, b, weight=w)
            dup.append((a, b, w))
    circ = eulerian_circuit(E, start if start is not None else next(iter(core)))
    secs["euler"] = time.perf_counter() - t

    added = sum(w for *_, w in dup)
    return CPPSolution(original, added, original + added, dup, circ, len(odd), pairs, secs)


def solve_directed(G: nx.MultiDiGraph, start=None) -> CPPSolution:
    """Directed CPP via minimum-cost flow on the imbalance of each vertex."""
    if not nx.is_strongly_connected(G):
        raise ValueError("Directed graph must be strongly connected")
    H = _simple(G)
    t = time.perf_counter()
    F = nx.DiGraph()
    for v in G:
        F.add_node(v, demand=G.out_degree(v) - G.in_degree(v))
    for u, v, d in H.edges(data=True):
        F.add_edge(u, v, weight=d["weight"])           # unbounded capacity
    flow = nx.min_cost_flow(F)
    secs = {"min-cost flow": time.perf_counter() - t}

    t = time.perf_counter()
    E = nx.MultiDiGraph(G)
    dup = []
    for u, out in flow.items():
        for v, f in out.items():
            for _ in range(f):
                w = H[u][v]["weight"]
                E.add_edge(u, v, weight=w)
                dup.append((u, v, w))
    circ = eulerian_circuit(E, start if start is not None else next(iter(G)))
    secs["euler"] = time.perf_counter() - t
    original = sum(w for *_, w in G.edges(data="weight"))
    added = sum(w for *_, w in dup)
    unbalanced = sum(1 for v in G if G.out_degree(v) != G.in_degree(v))
    return CPPSolution(original, added, original + added, dup, circ, unbalanced, [], secs)
