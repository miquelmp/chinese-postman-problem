"""Branch-and-bound for the pairing step: the 1997 method, the tightened bound of section 8.3
of the 2026 report, and an improved variant. The CPP itself uses Edmonds' blossom algorithm
(cpp.py); this module exists to measure the search that the 2026 version replaced.

The search follows chapter 9 and the Turbo C listings of the 1997 report:

* A node fixes pairs as taken or rejected. It separates on the first usable pair of the list
  sorted by cost: one child takes the pair, the other rejects it.
* Bound = cost of the taken pairs + ceil(sum of row minima / divisor). The divisor is imp/2 in
  the 1997 bound and 2 in the tightened one. They coincide for imp = 4.
* Under 100 open nodes, the node with the lowest bound is explored next; from 100 on, the one
  with most pairs taken. Remaining ties follow the insertion rule of ARBOL.C (newest first).

Options of the improved variant: `branch="constrained"` separates on the cheapest pair of the
vertex with fewest usable pairs, `start=True` begins from a greedy pairing improved by pair
swaps, and both prune a node as soon as a free vertex has no usable pair. Costs must be
positive integers, as in 1997.
"""
from __future__ import annotations

import heapq
import itertools
import time
from dataclasses import dataclass

import numpy as np

SWITCH = 100                     # open nodes at which exploration changes criterion (1997)


@dataclass
class BnBResult:
    """Outcome of a branch-and-bound run; costs and pairs refer to the matrix given."""
    cost: float | None           # best pairing found (None if none was found)
    pairs: list
    proven: bool                 # False if the node limit stopped the search
    explored: int                # nodes taken from the tree and separated
    generated: int               # children created, whether or not they were kept
    seconds: float


def bound_of(D, avail, taken_cost, divisor):
    """The 1997 bound; returns None for a node whose free vertices cannot all be paired by the
    parity test of the 1997 routine `cota` (an odd number of empty rows)."""
    big = np.iinfo(np.int64).max
    mins = np.where(avail, D, big).min(axis=1)
    mins[mins == big] = 0
    if int((mins == 0).sum()) % 2:
        return None
    return taken_cost + -(-int(mins.sum()) // divisor)


def greedy_pairing(D):
    """Cheapest pair first, then swaps between two pairs until none improves."""
    t = D.shape[0]
    edges = sorted((int(D[i, j]), i, j) for i, j in itertools.combinations(range(t), 2))
    free = set(range(t))
    pairs = []
    for _, i, j in edges:
        if i in free and j in free:
            free -= {i, j}
            pairs.append((i, j))
    improved = True
    while improved:
        improved = False
        for x, y in itertools.combinations(range(len(pairs)), 2):
            a, b = pairs[x]
            c, d = pairs[y]
            now = D[a, b] + D[c, d]
            for p, q in (((a, c), (b, d)), ((a, d), (b, c))):
                if D[p] + D[q] < now:
                    pairs[x], pairs[y] = p, q
                    improved = True
                    break
            if improved:
                break
    return pairs


def branch_and_bound(D, bound: str = "1997", branch: str = "list", start: bool = False,
                     max_nodes: int | None = None) -> BnBResult:
    """Minimum-cost perfect pairing of the t×t symmetric integer matrix D."""
    t0 = time.perf_counter()
    D = np.asarray(D, dtype=np.int64)
    t = D.shape[0]
    divisor = t // 2 if bound == "1997" else 2
    improved = branch == "constrained" or start
    order = sorted((int(D[i, j]), i, j) for i, j in itertools.combinations(range(t), 2))
    root = ~np.eye(t, dtype=bool)
    best, best_pairs = None, []
    if start:
        best_pairs = greedy_pairing(D)
        best = int(sum(D[p] for p in best_pairs))
    seq = itertools.count()
    nodes = {}                   # id -> (bound, taken cost, pairs, avail, free, list position)
    by_bound, by_depth = [], []

    def push(node):
        k = next(seq)
        nodes[k] = node
        heapq.heappush(by_bound, (node[0], -len(node[2]), -k))
        heapq.heappush(by_depth, (-len(node[2]), node[0], -k))

    def pop():
        heap = by_bound if len(nodes) < SWITCH else by_depth
        while True:
            k = -heapq.heappop(heap)[2]
            if k in nodes:
                return nodes.pop(k)

    def choose(node):
        _, _, _, avail, free, pos = node
        if branch == "list":
            for k in range(pos, len(order)):
                _, i, j = order[k]
                if avail[i, j]:
                    return i, j, k
            return None
        counts = avail.sum(axis=1)
        counts[~free] = t
        i = int(counts.argmin())
        if counts[i] in (0, t):
            return None
        return i, int(np.where(avail[i], D[i], np.iinfo(np.int64).max).argmin()), 0

    push((bound_of(D, root, 0, divisor), 0, (), root, np.ones(t, bool), 0))
    explored = generated = 0
    proven = True
    while nodes:
        if max_nodes is not None and explored >= max_nodes:
            proven = False
            break
        node = pop()
        parent_bound, cost, pairs, avail, free, _ = node
        explored += 1
        chosen = choose(node)
        if chosen is None:
            continue
        i, j, pos = chosen
        for take in (True, False):
            generated += 1
            a, f = avail.copy(), free
            if take:
                a[[i, j], :] = False
                a[:, [i, j]] = False
                f = free.copy()
                f[[i, j]] = False
                c, p = cost + int(D[i, j]), pairs + ((i, j),)
            else:
                a[i, j] = a[j, i] = False
                c, p = cost, pairs
            b = bound_of(D, a, c, divisor)
            if b is None or b < parent_bound or (best is not None and b >= best):
                continue
            if len(p) == t // 2:
                best, best_pairs = b, list(p)
                for k in [k for k, n in nodes.items() if n[0] >= best]:   # `matar`
                    del nodes[k]
                by_bound[:] = [e for e in by_bound if -e[2] in nodes]
                by_depth[:] = [e for e in by_depth if -e[2] in nodes]
                heapq.heapify(by_bound)
                heapq.heapify(by_depth)
            elif not (improved and bool((f & ~a.any(axis=1)).any())):
                push((b, c, p, a, f, pos))
    return BnBResult(best, best_pairs, proven, explored, generated, time.perf_counter() - t0)
