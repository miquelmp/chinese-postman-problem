"""Certify a minimum-weight perfect matching on the complete graph of odd vertices, without
Blossom V, by the sparse pricing of section 4.4 and a dual certificate.

    python3 tools/certify_matching.py                  # every case, writes results/certificates.csv
    python3 tools/certify_matching.py manhattan 70     # or: delaunay 2025

A matching solver (the JavaScript blossom code, through tools/match_sparse.mjs) runs on a sparse
candidate graph; pairs with negative slack are added until none is left. `check` then needs
nothing from that solver but its numbers. With w = C - d, u and z >= 0 such that

    u[i] + u[j] + sum(z[B] for blossoms B containing i and j) >= w[i, j]   for ALL pairs i, j,

every perfect matching M has w(M) <= sum(u) + sum(z[B] * floor(|B| / 2)) (weak duality). If the
matching found reaches that value, it is optimal on the complete graph.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


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


def solve(D, k=10):
    C = float(D.max()) + 1.0
    pairs = candidates(D, k)
    rounds = 0
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.json", Path(tmp) / "out.json"
        while True:
            rounds += 1
            src.write_text(json.dumps({"edges": [[i, j, C - float(D[i, j])] for i, j in pairs]}))
            subprocess.run(["node", "--max-old-space-size=4096", str(ROOT / "tools" / "match_sparse.mjs"),
                            str(src), str(dst)], check=True)
            out = json.loads(dst.read_text())
            twice_u = np.array(out["vertex"], dtype=np.float64)
            new = violations(D, C, twice_u, out["blossoms"])
            if not new:
                return out["mate"], twice_u, out["blossoms"], rounds, len(pairs)
            pairs.update(new)


def distances(G):
    """Odd-vertex distance table, as in chinese_postman.fast."""
    import networkx  # noqa: F401
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    from chinese_postman.cpp import _simple
    H = _simple(G)
    nodes = list(H.nodes)
    idx = {v: i for i, v in enumerate(nodes)}
    w = [c for *_, c in H.edges(data="weight")]
    r = [idx[u] for u, _ in H.edges]
    c = [idx[v] for _, v in H.edges]
    A = csr_matrix((np.array(w, float), (r, c)), shape=(len(nodes), len(nodes)))
    odd = np.array([idx[v] for v in G if G.degree(v) % 2], dtype=np.int64)
    D = np.empty((len(odd), len(odd)), np.int32)
    for s in range(0, len(odd), 1024):
        D[s:s + 1024] = np.rint(dijkstra(A, directed=False, indices=odd[s:s + 1024])[:, odd]).astype(np.int32)
    return D


def certify(kind, size):
    from chinese_postman import instances as I
    t0 = time.perf_counter()
    if kind == "manhattan":
        G, name = I.manhattan(size, size, drop=0.1, seed=size), f"manhattan-{size}x{size}"
    else:
        G, name = I.delaunay_town(size, seed=size), f"delaunay-{size}"
    t1 = time.perf_counter()
    D = distances(G)
    t2 = time.perf_counter()
    mate, twice_u, blossoms, rounds, edges = solve(D)
    t3 = time.perf_counter()
    added = check(D, mate, twice_u, blossoms)
    t4 = time.perf_counter()
    original = sum(w for *_, w in G.edges(data="weight"))
    return dict(instance=name, odd=len(D), original=original, added=int(added), total=int(original + added),
                rounds=rounds, candidate_edges=edges, blossoms=len(blossoms),
                build_s=round(t1 - t0, 1), distances_s=round(t2 - t1, 1), match_s=round(t3 - t2, 1),
                check_s=round(t4 - t3, 1))


def main():
    """Every network of results/scaling_blossom5.csv, then the town that exceeded the memory
    limit of the fast backend. Writes results/certificates.csv."""
    import csv
    import resource
    plan = [("manhattan", s) for s in (45, 70, 100, 140, 200)] + [("delaunay", s) for s in (2025, 5000, 10000, 20000, 40000)]
    rows = []
    for kind, size in plan:
        r = certify(kind, size)
        r["peak_rss_gb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 2, 2)
        rows.append(r)
        print(r, flush=True)
        with open(ROOT / "results" / "certificates.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    if len(sys.argv) == 3:
        print(json.dumps(certify(sys.argv[1], int(sys.argv[2]))), flush=True)
    else:
        main()
