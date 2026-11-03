"""Several postmen on windy, mixed and directed networks, with the longest route as short as possible.

The method is that of `fleet.solve_k_postmen`, with directed distances. One route serves every
required link; a dynamic programme cuts it into at most k pieces, each driven from the depot and
back; a local search then moves links out of the longest route. The min-max problem is NP-hard. The
lower bound is the larger of the longest single job and a k-th of the bound for one route.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .windyrural import RuralProblem, _Paths, lower_bound, solve_heuristic


@dataclass
class KSolution:
    """Routes from the depot, each a vertex sequence, with their costs and a lower bound."""
    routes: list
    costs: list
    lower_bound: float
    single_route: float
    seconds: float
    info: dict = field(default_factory=dict)

    @property
    def longest(self):
        """Cost of the longest route."""
        return max(self.costs)

    @property
    def gap_pct(self):
        """Percentage by which the longest route exceeds the lower bound."""
        return 100 * (self.longest - self.lower_bound) / self.lower_bound if self.lower_bound else 0.0


def _tasks_of(P, circuit):
    """The required links in the order the route first serves them, as (tail, head, cost, link)."""
    open_links = {}
    for k, l in enumerate(P.links):
        if l[4]:
            open_links.setdefault(frozenset(l[:2]), []).append(k)
    tasks = []
    for a, b in zip(circuit, circuit[1:]):
        q = open_links.get(frozenset((a, b)))
        if q:
            for i, k in enumerate(q):
                u, v, c_uv, c_vu, _ = P.links[k]
                c = c_uv if (a, b) == (u, v) else c_vu
                if c is not None:
                    q.pop(i)
                    tasks.append((a, b, c, k))
                    break
    return tasks


def _route_cost(paths, depot, route):
    """Cost of serving `route`, a list of tasks in order, from the depot and back."""
    i = paths.idx
    d = paths.dist
    at, cost = i[depot], 0.0
    for a, b, c, _ in route:
        cost += d[at, i[a]] + c
        at = i[b]
    return cost + d[at, i[depot]]


def _split(paths, depot, tasks, k):
    """Cut `tasks` into at most k consecutive routes, minimising the longest (exact for this order)."""
    n = len(tasks)
    k = min(k, n)
    idx = paths.idx
    tail = np.array([idx[t[0]] for t in tasks])
    head = np.array([idx[t[1]] for t in tasks])
    c = np.array([t[2] for t in tasks], float)
    D, dep = paths.dist, idx[depot]
    between = np.concatenate(([0.0], D[head[:-1], tail[1:]]))    # from task i - 1 to task i
    run = np.cumsum(c + between)                                 # run[j] - run[i] - serves i + 1..j
    start, finish = D[dep, tail], D[head, dep]
    C = np.full((n, n), np.inf)
    for i in range(n):
        C[i, i:] = start[i] + c[i] + (run[i:] - run[i]) + finish[i:]
    f = C[0].copy()
    cuts = []
    for _ in range(1, k):
        g, st = f.copy(), np.full(n, -1)
        for j in range(1, n):
            cand = np.maximum(f[:j], C[1:j + 1, j])
            q = int(np.argmin(cand))
            if cand[q] < g[j] - 1e-12:
                g[j], st[j] = cand[q], q + 1
        f = g
        cuts.append(st)
    routes, j = [], n - 1
    for r in range(k - 2, -1, -1):
        s = cuts[r][j]
        if s >= 0:
            routes.append(tasks[s:j + 1])
            j = s - 1
    routes.append(tasks[:j + 1])
    return routes[::-1]


def _improve(P, paths, depot, routes, seconds):
    """Move a task out of the longest route to its best place in another, in either direction, while
    that lowers the longest route, or keeps it and lowers the total."""
    W = P.windy
    t0 = time.perf_counter()
    costs = [_route_cost(paths, depot, r) for r in routes]
    moves = 0
    improved = True
    while improved and time.perf_counter() - t0 < seconds:
        improved = False
        worst = int(np.argmax(costs))
        best = None
        for p, task in enumerate(routes[worst]):
            shorter = routes[worst][:p] + routes[worst][p + 1:]
            c0 = _route_cost(paths, depot, shorter) if shorter else 0.0
            for r, route in enumerate(routes):
                if r == worst:
                    continue
                for a, b, c in W.directions(task[3]):
                    for q in range(len(route) + 1):
                        new = route[:q] + [(a, b, c, task[3])] + route[q:]
                        c1 = _route_cost(paths, depot, new)
                        key = (max(c0, c1), c0 + c1)
                        if best is None or key < best[0]:
                            best = (key, p, r, new, shorter, c0, c1)
            if time.perf_counter() - t0 > seconds:
                break
        if best and best[0][0] < costs[worst] - 1e-9:
            _, _, r, new, shorter, c0, c1 = best
            routes[r], routes[worst] = new, shorter
            costs[r], costs[worst] = c1, c0
            moves += 1
            improved = True
    return routes, costs, moves


def _vertices(paths, depot, route):
    seq, at = [depot], depot
    for a, b, _, _ in route:
        for _, y, _ in paths.path(at, a):
            seq.append(y)
        seq.append(b)
        at = b
    for _, y, _ in paths.path(at, depot):
        seq.append(y)
    return seq


def solve_k_postmen(P: RuralProblem, k: int, local_seconds: float = 5.0) -> KSolution:
    """At most k routes from the depot that together serve every required link."""
    if P.depot is None:
        P = RuralProblem(P.links, next(l[0] for l in P.links if l[4]))
    t0 = time.perf_counter()
    pre = lower_bound(P)
    single = solve_heuristic(P, pre=pre, local_seconds=min(local_seconds, 5.0))
    paths = _Paths(P)
    tasks = _tasks_of(P, single.circuit)
    routes = _split(paths, P.depot, tasks, k)
    split_longest = max(_route_cost(paths, P.depot, r) for r in routes)
    routes, costs, moves = _improve(P, paths, P.depot, routes, local_seconds)
    routes_used = [(r, c) for r, c in zip(routes, costs) if r]
    W = P.windy
    i, D = paths.idx, paths.dist
    far = max(min(D[i[P.depot], i[a]] + c + D[i[b], i[P.depot]] for a, b, c in W.directions(n))
              for n, l in enumerate(P.links) if l[4])
    bound = max(far, pre[0] / k)
    return KSolution([_vertices(paths, P.depot, r) for r, _ in routes_used], [c for _, c in routes_used],
                     float(bound), single.total_cost, time.perf_counter() - t0,
                     {"split_longest": split_longest, "moves": moves})
