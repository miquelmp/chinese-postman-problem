"""Write tests/js/matchings.json: optima of 3,000 random matchings, computed with NetworkX.

    python3 tests/js/make_matchings.py      # then: node tests/js/test_matching.mjs

The cost matrices are not stored: both languages rebuild them from the same generator.
"""
import json
from pathlib import Path

import networkx as nx

CASES = 3000


def matrix(k):
    """Case k: 2 to 24 vertices; odd cases have small costs, and therefore many ties."""
    x = k + 1
    t, top = 2 * (1 + k % 12), 20 if k % 2 else 1000
    D = {}
    for i in range(t):
        for j in range(i + 1, t):
            x = x * 16807 % 2147483647
            x = x * 16807 % 2147483647
            D[i, j] = 1 + x % top
    return t, D


def main():
    out = []
    for k in range(CASES):
        t, D = matrix(k)
        G = nx.Graph()
        for (i, j), w in D.items():
            G.add_edge(i, j, weight=w)
        out.append(sum(D[min(p), max(p)] for p in nx.min_weight_matching(G)))
    Path(__file__).with_name("matchings.json").write_text(json.dumps(out))
    print(f"{len(out)} matchings")


if __name__ == "__main__":
    main()
