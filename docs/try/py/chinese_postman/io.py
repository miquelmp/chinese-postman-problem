"""Graph file formats.

.GRA (1997 project):            CARP .dat (CARPData.jl, Martinelli):
    n_vertices                       n_vertices
    n_edges                          n_edges
    u v cost                         u v cost demand      (0-based vertices)
    ...                              ...
                                     vehicles capacity lower_bound upper_bound
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


def read_gra(path: str, directed: bool = False):
    """Read a .GRA file into a NetworkX multigraph (a directed one if `directed`)."""
    tok = open(path, encoding="utf-8").read().split()
    nv, ne = int(tok[0]), int(tok[1])
    G = nx.MultiDiGraph() if directed else nx.MultiGraph()
    G.add_nodes_from(range(1, nv + 1))
    for k in range(ne):
        a, b, c = tok[2 + 3 * k: 5 + 3 * k]
        G.add_edge(int(a), int(b), weight=float(c) if "." in c else int(c))
    return G


def write_gra(G, path: str) -> None:
    """Write a multigraph in the .GRA format."""
    edges = list(G.edges(data="weight"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{G.number_of_nodes()}\n{len(edges)}\n")
        for a, b, w in edges:
            f.write(f"{a} {b} {w}\n")


@dataclass
class CARPInstance:
    """A CARP benchmark: its road graph, vehicles, capacity and published bounds."""
    name: str
    graph: nx.MultiGraph       # every edge, vertices renumbered from 1
    required: int              # edges with demand > 0
    vehicles: int
    capacity: int
    lower_bound: int
    upper_bound: int


def read_carp(path: str) -> CARPInstance:
    """Read a CARP .dat file, keeping each street's demand as an edge attribute."""
    import os
    v = [int(x) for x in open(path, encoding="utf-8").read().split()]
    n, m = v[0], v[1]
    G = nx.MultiGraph()
    G.add_nodes_from(range(1, n + 1))
    req, i = 0, 2
    for _ in range(m):
        a, b, c, d = v[i:i + 4]
        G.add_edge(a + 1, b + 1, weight=c, demand=d)
        req += d > 0
        i += 4
    name = os.path.splitext(os.path.basename(path))[0]
    return CARPInstance(name, G, req, v[i], v[i + 1], v[i + 2], v[i + 3])
