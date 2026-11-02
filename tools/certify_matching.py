"""Repeat every large matching with a second solver: the JavaScript blossom code, through
tools/match_sparse.mjs, instead of LEMON. The same sparse pricing and the same dual certificate
(chinese_postman.fast) apply, so a defect in either code would show as a different optimum.

    python3 tools/certify_matching.py                  # every case, writes results/certificates.csv
    python3 tools/certify_matching.py manhattan 70     # or: delaunay 2025
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chinese_postman.fast import candidates, check, violations  # noqa: E402


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
    """Every network of results/scaling_lemon.csv. Writes results/certificates.csv."""
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
