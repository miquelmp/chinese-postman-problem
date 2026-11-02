"""Fast undirected CPP: SciPy (C) shortest paths + LEMON with dual pricing.

Instead of the complete graph on the odd vertices (n²/2 edges), LEMON's blossom code is solved on
a sparse candidate graph: each odd vertex's k nearest odd vertices plus a greedy pairing that
guarantees a perfect matching exists. Then, using the optimal duals, every missing pair with
negative slack is added and the problem re-solved, until no such pair remains.

`check` then proves the result from the numbers alone. With w = C - d, u and z >= 0 such that

    u[i] + u[j] + sum(z[B] for blossoms B containing i and j) >= w[i, j]   for ALL pairs i, j,

every perfect matching M has w(M) <= sum(u) + sum(z[B] * floor(|B| / 2)) (weak duality). If the
matching found reaches that value, it is optimal on the complete graph.

Requires native/liblemon_match.so, built by native/build_lemon.sh.
"""
from __future__ import annotations

import ctypes
import os
import time
from collections import defaultdict

import numpy as np
import networkx as nx
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from .cpp import CPPSolution, _simple
from .euler import eulerian_circuit

_LIB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "native", "liblemon_match.so")
_lib = None


def available() -> bool:
    """Return True if the LEMON library has been built."""
    return _load() is not None


def _load():
    global _lib
    if _lib is None and os.path.exists(_LIB_PATH):
        L = ctypes.CDLL(_LIB_PATH)
        P, I, Q = ctypes.c_void_p, ctypes.c_int, ctypes.c_int64
        IP = np.ctypeslib.ndpointer(np.int32, flags="C_CONTIGUOUS")
        QP = np.ctypeslib.ndpointer(np.int64, flags="C_CONTIGUOUS")
        L.lm_solve.restype, L.lm_solve.argtypes = P, [I, Q, IP, IP, QP]
        L.lm_free.restype, L.lm_free.argtypes = None, [P]
        L.lm_scale.restype, L.lm_scale.argtypes = I, []
        L.lm_blossoms.restype, L.lm_blossoms.argtypes = I, [P]
        L.lm_members.restype, L.lm_members.argtypes = Q, [P]
        L.lm_read.restype, L.lm_read.argtypes = None, [P, IP, QP, QP, IP, IP]
        _lib = L
    return _lib


def violations(D, C, twice_u, blossoms, chunk=1024):
    """All pairs i < j whose dual constraint fails, counting the blossoms that contain both."""
    inside = defaultdict(list)
    for k, b in enumerate(blossoms):
        for v in b["members"]:
            inside[v].append(k)
    found = []
    for r0 in range(0, len(D), chunk):
        block = twice_u[r0:r0 + chunk, None] + twice_u[None, :] - 2.0 * (C - D[r0:r0 + chunk].astype(np.float64))
        rows, cols = np.nonzero(block < 0)
        for i, j, s in zip(rows + r0, cols, block[rows, cols]):
            if i < j:
                common = set(inside.get(i, ())) & set(inside.get(j, ()))
                if s + 2.0 * sum(blossoms[k]["z"] for k in common) < 0:
                    found.append((int(i), int(j)))
    return found


def check(D, mate, twice_u, blossoms):
    """Return the certified optimal cost, or raise. Uses only D and the numbers given."""
    t = len(D)
    C = float(D.max()) + 1.0
    mate = np.asarray(mate)
    if (mate < 0).any() or (mate[mate] != np.arange(t)).any():
        raise ValueError("Not a perfect matching")
    if any(b["z"] < 0 for b in blossoms):
        raise ValueError("Negative blossom dual")
    if violations(D, C, twice_u, blossoms):
        raise ValueError("Dual constraint violated")
    pairs = [(i, int(mate[i])) for i in range(t) if i < mate[i]]
    cost = float(sum(float(D[p]) for p in pairs))
    weight = C * len(pairs) - cost
    dual = twice_u.sum() / 2.0 + sum(b["z"] * (len(b["members"]) // 2) for b in blossoms)
    if abs(weight - dual) > 1e-6:
        raise ValueError(f"Duality gap: matching {weight}, dual {dual}")
    return cost


def candidates(D, k=10, chunk=1024):
    """Each vertex's k nearest, plus a greedy pairing so that a perfect matching exists.
    Works row by row, which keeps memory near the size of D."""
    t = len(D)
    pairs = set()
    for r0 in range(0, t, chunk):
        block = D[r0:r0 + chunk].astype(np.int64)
        block[np.arange(len(block)), np.arange(r0, r0 + len(block))] = np.iinfo(np.int64).max
        near = np.argpartition(block, min(k, t - 1) - 1, axis=1)[:, :k]
        pairs.update((min(i, int(j)), max(i, int(j))) for i, row in enumerate(near, r0) for j in row)
    free = np.ones(t, bool)
    for i, j in sorted(pairs, key=lambda p: D[p]):
        if free[i] and free[j]:
            free[i] = free[j] = False
    left = np.flatnonzero(free).tolist()
    pairs.update(zip(left[0::2], left[1::2]))
    return pairs


def _lemon(L, D, pairs, C):
    """One LEMON run on the candidate pairs. Returns mate, doubled vertex duals and blossoms."""
    t = len(D)
    a = np.array(sorted(pairs), dtype=np.int32)
    i, j = np.ascontiguousarray(a[:, 0]), np.ascontiguousarray(a[:, 1])
    w = np.ascontiguousarray(C - D[i, j].astype(np.int64), dtype=np.int64)
    h = L.lm_solve(t, len(a), i, j, w)
    if not h:
        raise RuntimeError("Candidate graph has no perfect matching")
    try:
        count = L.lm_blossoms(h)
        mate, node = np.empty(t, np.int32), np.empty(t, np.int64)
        z, size = np.empty(count, np.int64), np.empty(count, np.int32)
        members = np.empty(L.lm_members(h), np.int32)
        L.lm_read(h, mate, node, z, size, members)
    finally:
        L.lm_free(h)
    scale = L.lm_scale()
    twice_u = node.astype(np.float64) * 2.0 / scale
    ends = np.cumsum(size)
    blossoms = [{"z": float(q) / scale, "members": m.tolist()}
                for q, m in zip(z, np.split(members, ends[:-1]))] if count else []
    return mate, twice_u, blossoms


def match_pricing(D: np.ndarray, k: int = 10):
    """Certified minimum-weight perfect matching on the complete graph with integer costs D (t×t)."""
    L = _load()
    if L is None:
        raise RuntimeError("LEMON library not built: run native/build_lemon.sh")
    C = int(D.max()) + 1
    pairs = candidates(D, k)
    stats = {"initial_edges": len(pairs), "rounds": 0, "added_edges": 0}
    while True:
        stats["rounds"] += 1
        mate, twice_u, blossoms = _lemon(L, D, pairs, C)
        new = violations(D, float(C), twice_u, blossoms)
        if not new:
            break
        pairs.update(new)
        stats["added_edges"] += len(new)
    stats["certified_cost"] = check(D, mate, twice_u, blossoms)
    stats["blossoms"] = len(blossoms)
    return mate, stats


def solve_undirected_fast(G: nx.MultiGraph, start=None, k: int = 10) -> CPPSolution:
    """Solve an undirected CPP with integer costs through LEMON, dual pricing and a certificate."""
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
