"""Eulerian circuit in a multigraph (Hierholzer's algorithm, O(m)).

Same idea as section 5.2.2 of the 1997 project (splice sub-cycles into the
circuit under construction), with one pointer per vertex into its adjacency
list so that every edge is examined once.
"""
from __future__ import annotations

import networkx as nx


def eulerian_circuit(G: nx.MultiGraph | nx.MultiDiGraph, start=None) -> list:
    """Return the vertex sequence of an Eulerian circuit (first == last)."""
    directed = G.is_directed()
    adj = {v: [] for v in G}
    for eid, (u, v) in enumerate(G.edges()):
        adj[u].append((v, eid))
        if not directed:
            adj[v].append((u, eid))
    m = G.number_of_edges()
    if m == 0:
        return [start] if start is not None else []
    used = [False] * m
    ptr = {v: 0 for v in G}
    if start is None or not adj[start]:
        start = next(v for v in G if adj[v])
    stack, circuit = [start], []
    while stack:
        v = stack[-1]
        lst = adj[v]
        while ptr[v] < len(lst) and used[lst[ptr[v]][1]]:
            ptr[v] += 1
        if ptr[v] == len(lst):
            circuit.append(stack.pop())
        else:
            w, eid = lst[ptr[v]]
            used[eid] = True
            stack.append(w)
    if len(circuit) != m + 1:
        raise ValueError("Graph is not Eulerian or not connected")
    circuit.reverse()
    return circuit
