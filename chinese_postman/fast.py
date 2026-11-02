"""Fast undirected CPP: SciPy (C) shortest paths + Blossom V with dual pricing.

Instead of the complete graph on the odd vertices (n²/2 edges), Blossom V is solved on a
sparse candidate graph: each odd vertex's k nearest odd vertices plus a greedy pairing that
guarantees a perfect matching exists. Then, using the optimal duals, every missing pair (u, v)
with 2·d(u, v) < 2y(u) + 2y(v) (negative reduced cost) is added and the problem re-solved,
until no such pair remains. At that point the matching is optimal for the complete graph too.

Requires native/libblossom5.so (built by native/build_blossom5.sh). Blossom V's licence
allows evaluation and non-commercial research only.
"""
from __future__ import annotations

import ctypes
import os
import time

import numpy as np
import networkx as nx
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from .cpp import CPPSolution, _simple
from .euler import eulerian_circuit

_LIB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "native", "libblossom5.so")
_lib = None


def available() -> bool:
    """Return True if the Blossom V library has been built."""
    return _load() is not None


def _load():
    global _lib
    if _lib is None and os.path.exists(_LIB_PATH):
        L = ctypes.CDLL(_LIB_PATH)
        P, I = ctypes.c_void_p, ctypes.c_int
        IP = np.ctypeslib.ndpointer(np.int32, flags="C_CONTIGUOUS")
        L.pm_new.restype, L.pm_new.argtypes = P, [I, I]
        L.pm_free.argtypes = [P]
        L.pm_add_edges.argtypes = [P, I, IP, IP, IP]
        L.pm_solve.argtypes = [P]
        L.pm_start_update.argtypes = [P, I, IP]
        L.pm_add_new_edges.restype, L.pm_add_new_edges.argtypes = I, [P, I, IP, IP, IP]
        L.pm_finish_update.argtypes = [P]
        L.pm_get_match.argtypes = [P, I, IP]
        _lib = L
    return _lib


def _initial_edges(D, k):
    """k nearest neighbours of every vertex + a greedy perfect pairing (feasibility)."""
    t = D.shape[0]
    k = min(k, t - 1)
    Dm = D.astype(np.int64)
    np.fill_diagonal(Dm, np.iinfo(np.int64).max)
    nn = np.argpartition(Dm, k - 1, axis=1)[:, :k] if k > 0 else np.zeros((t, 0), int)
    i = np.repeat(np.arange(t), nn.shape[1])
    j = nn.ravel()
    a, b = np.minimum(i, j), np.maximum(i, j)
    pairs = np.unique(a * t + b)
    a, b = pairs // t, pairs % t
    # greedy pairing on candidate edges, leftovers paired in index order
    order = np.argsort(D[a, b], kind="stable")
    free = np.ones(t, bool)
    extra = []
    for e in order:
        u, v = a[e], b[e]
        if free[u] and free[v]:
            free[u] = free[v] = False
    left = np.flatnonzero(free)
    extra = list(zip(left[0::2], left[1::2]))
    if extra:
        ea, eb = np.array(extra).T
        a, b = np.concatenate([a, ea]), np.concatenate([b, eb])
    return a.astype(np.int32), b.astype(np.int32)


def match_pricing(D: np.ndarray, k: int = 10, chunk: int = 2048):
    """Minimum-weight perfect matching on the complete graph with integer costs D (t×t)."""
    L = _load()
    if L is None:
        raise RuntimeError("Blossom V library not built: run native/build_blossom5.sh")
    t = D.shape[0]
    a, b = _initial_edges(D, k)
    w = np.ascontiguousarray(D[a, b], dtype=np.int32)
    pm = L.pm_new(t, int(len(a) * 4) + 8 * t + 64)
    stats = {"initial_edges": int(len(a)), "rounds": 0, "added_edges": 0}
    try:
        L.pm_add_edges(pm, len(a), a, b, w)
        L.pm_solve(pm)
        ts = np.empty(t, np.int32)
        while True:
            L.pm_start_update(pm, t, ts)
            added = 0
            for r0 in range(0, t, chunk):
                r1 = min(t, r0 + chunk)
                block = 2 * D[r0:r1].astype(np.int64)
                viol = block < ts[r0:r1, None].astype(np.int64) + ts[None, :].astype(np.int64)
                rr, cc = np.nonzero(viol)
                rr = rr + r0
                keep = rr < cc
                rr, cc = rr[keep].astype(np.int32), cc[keep].astype(np.int32)
                if len(rr):
                    ww = np.ascontiguousarray(D[rr, cc], dtype=np.int32)
                    added += L.pm_add_new_edges(pm, len(rr), rr, cc, ww)
            L.pm_finish_update(pm)
            L.pm_solve(pm)          # re-solve (also restores the primal after an update round)
            stats["rounds"] += 1
            stats["added_edges"] += added
            if added == 0:
                break
        mate = np.empty(t, np.int32)
        L.pm_get_match(pm, t, mate)
    finally:
        L.pm_free(pm)
    return mate, stats


def solve_undirected_fast(G: nx.MultiGraph, start=None, k: int = 10) -> CPPSolution:
    """Solve an undirected CPP with integer costs through Blossom V and dual pricing."""
    if G.number_of_edges() == 0:
        raise ValueError("Graph has no edges")
    core = G.subgraph([v for v in G if G.degree(v) > 0])
    if not nx.is_connected(core):
        raise ValueError("Graph must be connected")
    secs = {}
    H = _simple(G)
    nodes = list(H.nodes)
    idx = {v: i for i, v in enumerate(nodes)}
    ws = [w for *_, w in H.edges(data="weight")]
    if any(int(w) != w for w in ws):
        raise ValueError("Fast backend needs integer costs (scale them, e.g. metres or seconds)")
    original = sum(w for *_, w in G.edges(data="weight"))
    odd = np.array([idx[v] for v in G if G.degree(v) % 2], dtype=np.int64)

    t0 = time.perf_counter()
    r = np.array([idx[u] for u, v in H.edges]); c = np.array([idx[v] for u, v in H.edges])
    A = csr_matrix((np.array(ws, float), (r, c)), shape=(len(nodes), len(nodes)))
    T = len(odd)
    D = np.empty((T, T), np.int32)
    for s0 in range(0, T, 1024):
        rows = dijkstra(A, directed=False, indices=odd[s0:s0 + 1024])
        D[s0:s0 + 1024] = np.rint(rows[:, odd]).astype(np.int32)
    secs["shortest paths"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    stats = {"initial_edges": 0, "rounds": 0, "added_edges": 0}
    pairs_i = []
    if T:
        mate, stats = match_pricing(D, k=k)
        pairs_i = [(i, int(mate[i])) for i in range(T) if i < mate[i]]
    secs["matching"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    E = nx.MultiGraph(G)
    dup = []
    if pairs_i:
        src = np.array([odd[i] for i, _ in pairs_i])
        for s0 in range(0, len(src), 1024):
            _, pred = dijkstra(A, directed=False, indices=src[s0:s0 + 1024], return_predecessors=True)
            for row, (i, j) in enumerate(pairs_i[s0:s0 + 1024]):
                x = odd[j]
                while x != odd[i]:
                    y = pred[row, x]
                    u, v = nodes[y], nodes[x]
                    wgt = H[u][v]["weight"]
                    E.add_edge(u, v, weight=wgt)
                    dup.append((u, v, wgt))
                    x = y
    circ = eulerian_circuit(E, start if start is not None else next(iter(core)))
    secs["euler"] = time.perf_counter() - t0

    added = sum(w for *_, w in dup)
    pairs = [(nodes[odd[i]], nodes[odd[j]]) for i, j in pairs_i]
    sol = CPPSolution(original, added, original + added, dup, circ, T, pairs, secs)
    sol.matching_stats = stats
    return sol
