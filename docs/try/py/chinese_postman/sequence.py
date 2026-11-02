"""Routes as sequences of served streets, joined by shortest paths.

A route from the depot is a list of streets (i, j, service, demand) in the order and direction
they are served; i and j index the required vertices of a `rural.Problem`. Its cost is the
service of every street plus the shortest paths from the depot to the first street, between
consecutive streets and from the last street back. Any closed walk that serves the streets
costs at least this much, so working on sequences loses nothing.
"""
from __future__ import annotations

import time

import numpy as np


def route_cost(P, seq):
    if not seq:
        return 0.0
    d, D = P.vi[P.depot], P.D
    a = np.fromiter((e[0] for e in seq), int, len(seq))
    b = np.fromiter((e[1] for e in seq), int, len(seq))
    s = sum(e[2] for e in seq)
    return float(D[d, a[0]] + s + D[b[:-1], a[1:]].sum() + D[b[-1], d])


def orient(P, seq):
    """Best direction for every street, keeping the order (dynamic programme, linear time)."""
    if not seq:
        return seq
    d, D = P.vi[P.depot], P.D
    n = len(seq)
    A = np.array([[e[0], e[1]] for e in seq])        # start vertex if direction 0 / 1 ...
    start = np.stack([A[:, 0], A[:, 1]], 1)            # start[t, o]
    end = np.stack([A[:, 1], A[:, 0]], 1)              # end[t, o]
    cost = D[d, start[0]].astype(float)
    back = np.zeros((n, 2), int)
    for t in range(1, n):
        trans = cost[:, None] + D[end[t - 1][:, None], start[t][None, :]]   # [prev o, new o]
        back[t] = trans.argmin(0)
        cost = trans.min(0)
    cost = cost + D[end[-1], d]
    o = int(cost.argmin())
    out = [None] * n
    for t in range(n - 1, -1, -1):
        out[t] = (int(start[t, o]), int(end[t, o]), seq[t][2], seq[t][3])
        o = back[t, o]
    return out


def insertion(P, seq, e):
    """Cheapest place and direction to add street e; returns (extra cost, new sequence)."""
    d, D = P.vi[P.depot], P.D
    n = len(seq)
    prev = np.array([d] + [x[1] for x in seq])
    nxt = np.array([x[0] for x in seq] + [d])
    a, b, s = e[0], e[1], e[2]
    base = D[prev, nxt]
    f = D[prev, a] + s + D[b, nxt] - base
    r = D[prev, b] + s + D[a, nxt] - base
    t1, t2 = int(f.argmin()), int(r.argmin())
    if f[t1] <= r[t2]:
        return float(f[t1]), seq[:t1] + [(a, b, s, e[3])] + seq[t1:]
    return float(r[t2]), seq[:t2] + [(b, a, s, e[3])] + seq[t2:]


def improve(P, seq, seconds=5.0):
    """Local search on one route: move a street elsewhere (drop and re-add), and reverse a
    stretch of the route (2-opt), while the route gets shorter."""
    deadline = time.perf_counter() + seconds
    seq = orient(P, seq)
    d, D = P.vi[P.depot], P.D
    cost = route_cost(P, seq)
    improved = True
    while improved and time.perf_counter() < deadline:
        improved = False
        # 2-opt: reversing seq[i..j] changes only its two outer links (distances are symmetric)
        n = len(seq)
        if n >= 2:
            st = np.array([x[0] for x in seq]); en = np.array([x[1] for x in seq])
            prev = np.concatenate([[d], en[:-1]])           # vertex before position i
            nxt = np.concatenate([st[1:], [d]])             # vertex after position j
            for i in range(n - 1):
                j = np.arange(i + 1, n)
                delta = D[prev[i], en[j]] + D[st[i], nxt[j]] - D[prev[i], st[i]] - D[en[j], nxt[j]]
                k = int(delta.argmin())
                if delta[k] < -1e-9:
                    j = i + 1 + k
                    seq = seq[:i] + [(x[1], x[0], x[2], x[3]) for x in reversed(seq[i:j + 1])] + seq[j + 1:]
                    cost += float(delta[k])
                    improved = True
                    break
            if improved:
                continue
        # drop and re-add each street
        for t in range(len(seq)):
            if time.perf_counter() > deadline:
                break
            e = seq[t]
            p = d if t == 0 else seq[t - 1][1]
            q = d if t == len(seq) - 1 else seq[t + 1][0]
            gain = D[p, e[0]] + e[2] + D[e[1], q] - D[p, q]
            rest = seq[:t] + seq[t + 1:]
            extra, new = insertion(P, rest, e)
            if extra < gain - 1e-9:
                seq, cost, improved = new, cost - gain + extra, True
        seq = orient(P, seq)
        cost = route_cost(P, seq)
    return seq, cost


def from_circuit(P, circuit, demand=None):
    """Order in which a closed walk serves the required streets (the first pass serves)."""
    left = {}
    for k, (u, v, s) in enumerate(P.R):
        key = frozenset((P.vi[u], P.vi[v]))
        left.setdefault(key, []).append((s, demand[k] if demand is not None else 0.0))
    seq = []
    for x, y in zip(circuit, circuit[1:]):
        if x in P.vi and y in P.vi:
            key = frozenset((P.vi[x], P.vi[y]))
            if left.get(key):
                s, q = left[key].pop()
                seq.append((P.vi[x], P.vi[y], s, q))
    for key, rest in left.items():            # parallel streets: serve the remaining copies too
        for s, q in rest:
            a, b = (tuple(key) * 2)[:2]
            seq.append((a, b, s, q))
    return seq


def expand(P, seq):
    """Vertex sequence of a route through the original network, depot to depot."""
    dep = P.vi[P.depot]
    cur, out = dep, [P.depot]
    for a, b, *_ in seq:
        if cur != a:
            out += P.path(cur, a)[1:]
        out.append(P.V[b])
        cur = b
    if cur != dep:
        out += P.path(cur, dep)[1:]
    return out
