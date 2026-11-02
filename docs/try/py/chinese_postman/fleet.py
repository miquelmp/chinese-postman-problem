"""Several postmen: dividing the streets among k routes from one depot.

This follows the third observation of the 1997 conclusions: a routine service is limited by a
working shift, so a large district is shared among several crews.

* `solve_k_postmen`: min-max k-postmen (k-CPP / k-RPP). Every required street is served by one
  of k routes from the depot; the longest route is made as short as possible. NP-hard
  (Frederickson, Hecht & Kim 1978). Heuristic: one tour (exact for the CPP, chapter 3; for the
  RPP, rural.solve_rural), split into k consecutive pieces at least cost (an exact dynamic
  programme over the tour order), then a local search that moves streets out of the longest
  route and re-plans each route. Splitting an optimal single tour is never worse than
  (2 - 1/k) times the optimum (Frederickson, Hecht & Kim 1978); the local search only improves.
  `lower_bound` gives max( farthest street there and back, single-tour bound / k ).
* `solve_k_exact`: integer program for tiny networks, to measure the heuristic.
* `solve_carp`: capacitated fleets (CARP), every street with a demand and every vehicle with a
  capacity; the tour is split by Ulusoy's (1985) dynamic programme, then improved locally.

Routes are sequences of served streets (i, j, service, demand) on the required vertices of a
`rural.Problem`; consecutive streets are joined by shortest paths.
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse.csgraph import minimum_spanning_tree
from scipy.sparse import csr_matrix

from . import rural
from .cpp import min_weight_pairing
from .sequence import route_cost, orient, insertion as _best_insertion, from_circuit as tour_sequence
from .sequence import expand as _expand


@dataclass
class FleetSolution:
    method: str
    routes: list                 # one vertex sequence per route, depot to depot
    route_costs: list
    max_cost: float              # the longest route
    total_cost: float            # all routes together
    lower_bound: float           # on the objective (longest route, or total for the CARP)
    optimal: bool
    seconds: float
    info: dict = field(default_factory=dict)

    @property
    def gap_pct(self) -> float:
        obj = self.info.get("objective_value", self.max_cost)
        lb = self.lower_bound
        return 100.0 * max(obj - lb, 0.0) / lb if lb else 0.0


# ---------------------------------------------------------------------------- splitting

def _segment_costs(P, seq):
    """cost(i, j) of serving seq[i..j] in one route, as a vectorised helper."""
    d, D = P.vi[P.depot], P.D
    n = len(seq)
    a = np.array([e[0] for e in seq]); b = np.array([e[1] for e in seq])
    s = np.array([e[2] for e in seq], float)
    link = np.append(D[b[:-1], a[1:]], 0.0)
    pre = np.concatenate([[0.0], np.cumsum(s + link)])
    to = D[d, a]; back = D[b, d]

    def cost(i, j):                            # j may be an array
        return to[i] + pre[np.asarray(j) + 1] - pre[i] - link[np.asarray(j)] + back[np.asarray(j)]
    return cost, n


def split_minmax(P, seq, k):
    """Split a sequence into at most k consecutive routes, minimising the longest (exact DP)."""
    cost, n = _segment_costs(P, seq)
    if n == 0:
        return []
    k = min(k, n)
    C = np.full((n, n), np.inf)                # C[i, j]: one route serving i..j
    for i in range(n):
        C[i, i:] = cost(i, np.arange(i, n))
    f = C[0].copy()                            # f[j]: best longest route for 0..j
    start = []
    for r in range(1, k):
        g = f.copy()
        st = np.full(n, -1)
        for j in range(1, n):
            cand = np.maximum(f[:j], C[1:j + 1, j])       # last route starts at i + 1
            i = int(np.argmin(cand))
            if cand[i] < g[j] - 1e-12:
                g[j], st[j] = cand[i], i + 1
        f = g
        start.append(st)
    routes, j = [], n - 1
    for r in range(k - 1, 0, -1):
        s = start[r - 1][j]
        if s >= 0:
            routes.append(seq[s:j + 1])
            j = s - 1
    routes.append(seq[:j + 1])
    return [rt for rt in reversed(routes) if rt]


def split_capacity(P, seq, Q):
    """Ulusoy's split: consecutive routes with load <= Q, least total cost (exact DP)."""
    cost, n = _segment_costs(P, seq)
    q = np.array([e[3] for e in seq], float)
    if (q > Q).any():
        raise ValueError("A street's demand exceeds the vehicle capacity")
    f = np.full(n + 1, np.inf); f[0] = 0.0
    pred = np.zeros(n + 1, int)
    for i in range(n):
        load, j = 0.0, i
        while j < n and load + q[j] <= Q:
            load += q[j]
            c = f[i] + cost(i, j)
            if c < f[j + 1]:
                f[j + 1], pred[j + 1] = c, i
            j += 1
    routes, j = [], n
    while j > 0:
        routes.append(seq[pred[j]:j]); j = pred[j]
    return list(reversed(routes))


# ---------------------------------------------------------------------------- route re-planning

def replan(P, seq):
    """Re-plan one route as a small rural postman problem (Frederickson on the reduced graph)."""
    if len(seq) < 2:
        return orient(P, seq)
    dep = P.vi[P.depot]
    idx = sorted({dep} | {e[0] for e in seq} | {e[1] for e in seq})
    pos = {v: t for t, v in enumerate(idx)}
    uf = list(range(len(idx)))

    def find(x):
        while uf[x] != x:
            uf[x] = uf[uf[x]]; x = uf[x]
        return x
    for a, b, *_ in seq:
        uf[find(pos[a])] = find(pos[b])
    comps = {}
    for v in idx:
        comps.setdefault(find(pos[v]), []).append(v)
    pieces = list(comps.values())
    links = []
    if len(pieces) > 1:
        m = len(pieces)
        W = np.zeros((m, m)); arg = {}
        for x in range(m):
            for y in range(x + 1, m):
                sub = P.D[np.ix_(pieces[x], pieces[y])]
                r, c = np.unravel_index(np.argmin(sub), sub.shape)
                W[x, y] = W[y, x] = sub[r, c] + 1e-9
                arg[x, y] = arg[y, x] = (pieces[x][r], pieces[y][c])
        T = minimum_spanning_tree(csr_matrix(W)).tocoo()
        links = [arg[int(x), int(y)] for x, y in zip(T.row, T.col)]
    deg = {v: 0 for v in idx}
    for a, b, *_ in seq:
        deg[a] += 1; deg[b] += 1
    for a, b in links:
        deg[a] += 1; deg[b] += 1
    odd = [v for v in idx if deg[v] % 2]
    if odd:
        links += min_weight_pairing(odd, P.D)
    E = nx.MultiGraph()
    E.add_node(dep)
    for t, (a, b, *_ ) in enumerate(seq):
        E.add_edge(a, b, key=("r", t))
    for t, (a, b) in enumerate(links):
        E.add_edge(a, b, key=("d", t))
    new = []
    for u, v, key in nx.eulerian_circuit(E, source=dep, keys=True):
        if key[0] == "r":
            a, b, s, q = seq[key[1]]
            new.append((u, v, s, q))
    new = orient(P, new)
    return new if route_cost(P, new) < route_cost(P, seq) - 1e-9 else orient(P, seq)


# ---------------------------------------------------------------------------- local search

def _key(costs):
    return (round(max(costs), 9), round(sum(costs), 9))


def _descent(P, routes, deadline):
    """Relocations and swaps that shorten the longest route (or, at equal longest route, the
    total), until none is left; then every route is re-planned and the search repeats."""
    routes = [orient(P, r) for r in routes]
    costs = [route_cost(P, r) for r in routes]
    while time.perf_counter() < deadline:
        L = int(np.argmax(costs))
        best = None                                   # (key, routes A, B, index A, index B)
        for t, e in enumerate(routes[L]):
            rest = orient(P, routes[L][:t] + routes[L][t + 1:])
            c_rest = route_cost(P, rest)
            for r in range(len(routes)):
                if r == L:
                    continue
                delta, ins = _best_insertion(P, routes[r], e)
                trial = costs.copy(); trial[L] = c_rest; trial[r] = costs[r] + delta
                if _key(trial) < _key(costs) and (best is None or _key(trial) < best[0]):
                    best = (_key(trial), rest, ins, L, r)
                for u, f in enumerate(routes[r]):     # swap e and f
                    if time.perf_counter() > deadline:
                        break
                    d1, a_new = _best_insertion(P, rest, f)
                    other = routes[r][:u] + routes[r][u + 1:]
                    d2, b_new = _best_insertion(P, other, e)
                    trial = costs.copy()
                    trial[L] = c_rest + d1
                    trial[r] = route_cost(P, other) + d2
                    if _key(trial) < _key(costs) and (best is None or _key(trial) < best[0]):
                        best = (_key(trial), a_new, b_new, L, r)
        if best is None:
            new = [replan(P, r) for r in routes]
            nc = [route_cost(P, r) for r in new]
            if _key(nc) < _key(costs):
                routes, costs = new, nc
                continue
            break
        _, A, B, a, b = best
        routes[a], routes[b] = orient(P, A), orient(P, B)
        costs[a], costs[b] = route_cost(P, routes[a]), route_cost(P, routes[b])
    return routes, costs


def improve_minmax(P, routes, seconds=5.0, seed=0):
    """Descent, then iterated perturbation (a few streets moved at random) while time is left."""
    import random
    rng = random.Random(seed)
    deadline = time.perf_counter() + seconds
    best, bc = _descent(P, routes, deadline)
    cur, cc = best, bc
    stall = 0
    while time.perf_counter() < deadline and stall < 400:
        trial = [list(r) for r in cur]
        for _ in range(rng.randint(1, 3)):
            nonempty = [i for i, r in enumerate(trial) if r]
            a = rng.choice(nonempty)
            e = trial[a].pop(rng.randrange(len(trial[a])))
            b = rng.randrange(len(trial))
            _, trial[b] = _best_insertion(P, trial[b], e)
        trial, tc = _descent(P, trial, deadline)
        if _key(tc) < _key(cc) or rng.random() < 0.05:
            cur, cc = trial, tc
        if _key(tc) < _key(bc):
            best, bc, stall = trial, tc, 0
        else:
            stall += 1
    return best


def tour_variants(P, circuit, count, seed=0):
    """The same closed walk written out from different Euler circuits (different street orders)."""
    import random
    rng = random.Random(seed)
    edges = list(zip(circuit, circuit[1:]))
    out = [circuit, circuit[::-1]]
    for _ in range(max(0, count - 2)):
        rng.shuffle(edges)
        E = nx.MultiGraph()
        E.add_edges_from(edges)
        out.append([u for u, _ in nx.eulerian_circuit(E, source=P.depot)] + [P.depot])
    return out


def improve_capacity(P, routes, Q, seconds=5.0):
    """Relocate single streets between routes when the total cost falls and loads stay <= Q."""
    t0 = time.perf_counter()
    routes = [replan(P, r) for r in routes]
    load = [sum(e[3] for e in r) for r in routes]
    improved = True
    while improved and time.perf_counter() - t0 < seconds:
        improved = False
        for A in range(len(routes)):
            for t in range(len(routes[A])):
                e = routes[A][t]
                rest = orient(P, routes[A][:t] + routes[A][t + 1:])
                gain = route_cost(P, routes[A]) - route_cost(P, rest)
                for B in range(len(routes)):
                    if B == A or load[B] + e[3] > Q:
                        continue
                    delta, new = _best_insertion(P, routes[B], e)
                    if delta < gain - 1e-9:
                        routes[A], routes[B] = rest, orient(P, new)
                        load[A] -= e[3]; load[B] += e[3]
                        improved = True
                        break
                if improved or time.perf_counter() - t0 > seconds:
                    break
            if improved:
                break
    routes = [replan(P, r) for r in routes if r]
    return routes


# ---------------------------------------------------------------------------- bounds

def lower_bound(P, k, single_bound):
    d = P.vi[P.depot]
    far = max(P.D[d, P.vi[u]] + s + P.D[P.vi[v], d] for u, v, s in P.R)
    return max(far, single_bound / k), far


# ---------------------------------------------------------------------------- solvers

def solve_k_postmen(G: nx.MultiGraph, k: int, depot=None, time_limit: float = 30.0,
                    local_seconds: float = 10.0) -> FleetSolution:
    """Min-max k postmen on the required streets (all streets if none is marked)."""
    t0 = time.perf_counter()
    single = rural.solve_rural(G, depot=depot, time_limit=max(1.0, time_limit / 2),
                               local_seconds=min(local_seconds, 5.0))
    P = rural.Problem(G, depot)
    starts = []
    variants = 8 if len(P.R) <= 300 else 2
    for circ in tour_variants(P, single.circuit, variants):
        seq = orient(P, tour_sequence(P, circ))
        rts = split_minmax(P, seq, k)
        starts.append((max(route_cost(P, r) for r in rts), rts))
    starts.sort(key=lambda x: x[0])
    split_max, routes = starts[0]
    left = max(0.5, min(local_seconds, time_limit - (time.perf_counter() - t0)))
    routes = improve_minmax(P, routes, left)
    costs = [route_cost(P, r) for r in routes]
    lb, far = lower_bound(P, k, single.lower_bound)
    integral = np.allclose(P.D, np.round(P.D)) and all(float(s).is_integer() for *_, s in P.R)
    if integral:
        lb = float(np.ceil(lb - 1e-6))
    info = {"single_tour": single.total_cost, "single_optimal": single.optimal,
            "split_max": split_max, "far_bound": far, "objective_value": max(costs)}
    return FleetSolution("tour split + local search", [_expand(P, r) for r in routes], costs,
                         max(costs), sum(costs), lb, max(costs) <= lb + 1e-9,
                         time.perf_counter() - t0, info)


def solve_k_exact(G: nx.MultiGraph, k: int, depot=None, time_limit: float = 120.0):
    """Exact min-max k postmen by branch-and-cut (tiny networks). Returns (value, optimal, bound)."""
    P = rural.Problem(G, depot)
    E = P.deadhead_edges()
    R = [(P.vi[u], P.vi[v], s) for u, v, s in P.R]
    nV, nE, nR = len(P.V), len(E), len(R)
    dep = P.vi[P.depot]
    per = nR + nE + nV                        # y, x, z for each route
    nv = k * per + 1                           # + L
    Lc = nv - 1
    Y = lambda e, r: r * per + e
    X = lambda a, r: r * per + nR + a
    Z = lambda v, r: r * per + nR + nE + v
    rows, lo, hi = [], [], []

    def add(coefs, l, h):
        row = np.zeros(nv)
        for j, c in coefs:
            row[j] += c
        rows.append(row); lo.append(l); hi.append(h)
    for e in range(nR):
        add([(Y(e, r), 1) for r in range(k)], 1, 1)
    for r in range(k):
        for v in range(nV):
            co = [(Y(e, r), 1) for e, (a, b, _) in enumerate(R) if a == v and b != v]
            co += [(Y(e, r), 1) for e, (a, b, _) in enumerate(R) if b == v and a != v]
            co += [(X(t, r), 1) for t, (a, b, _) in enumerate(E) if v in (a, b)]
            co.append((Z(v, r), -2))
            add(co, 0, 0)
        co = [(Y(e, r), s) for e, (_, _, s) in enumerate(R)] + [(X(t, r), d) for t, (_, _, d) in enumerate(E)]
        add(co + [(Lc, -1)], -np.inf, 0)
        if r + 1 < k:                           # symmetry: routes sorted by cost
            co2 = [(Y(e, r + 1), -s) for e, (_, _, s) in enumerate(R)] + \
                  [(X(t, r + 1), -d) for t, (_, _, d) in enumerate(E)]
            add(co + co2, 0, np.inf)
    cost = np.zeros(nv); cost[Lc] = 1.0
    lb_ = np.zeros(nv); ub = np.full(nv, np.inf)
    for r in range(k):
        for e in range(nR):
            ub[Y(e, r)] = 1
        for t in range(nE):
            ub[X(t, r)] = 2
    integ = np.ones(nv); integ[Lc] = 0
    t0 = time.perf_counter()
    while True:
        left = time_limit - (time.perf_counter() - t0)
        if left <= 0.5:
            return None, False, None
        res = milp(cost, constraints=[LinearConstraint(np.array(rows), lo, hi)], integrality=integ,
                   bounds=Bounds(lb_, ub), options={"time_limit": left, "disp": False})
        if res.x is None:
            return None, False, None
        x = res.x
        added = False
        for r in range(k):
            uf = list(range(nV))

            def find(a):
                while uf[a] != a:
                    uf[a] = uf[uf[a]]; a = uf[a]
                return a
            for e, (a, b, _) in enumerate(R):
                if x[Y(e, r)] > 0.5:
                    uf[find(a)] = find(b)
            for t, (a, b, _) in enumerate(E):
                if x[X(t, r)] > 0.5:
                    uf[find(a)] = find(b)
            for comp_root in {find(a) for e, (a, b, _) in enumerate(R) if x[Y(e, r)] > 0.5}:
                if comp_root == find(dep):
                    continue
                S = {v for v in range(nV) if find(v) == comp_root}
                for f, (a, b, _) in enumerate(R):
                    if x[Y(f, r)] > 0.5 and a in S:
                        co = [(Y(e, r), 1) for e, (p, q, _) in enumerate(R) if (p in S) != (q in S)]
                        co += [(X(t, r), 1) for t, (p, q, _) in enumerate(E) if (p in S) != (q in S)]
                        co.append((Y(f, r), -2))
                        add(co, 0, np.inf)
                        added = True
                        break
        if not added:
            val = float(x[Lc])
            return val, res.status == 0, float(getattr(res, "mip_dual_bound", val))


def solve_carp(G: nx.MultiGraph, capacity: float, depot=None, local_seconds: float = 10.0):
    """Capacitated fleet: route-first (one rural postman tour), cluster-second (Ulusoy split),
    then relocations between routes. Edge attribute 'demand' (> 0 means required)."""
    t0 = time.perf_counter()
    H = nx.MultiGraph()
    for u, v, d in G.edges(data=True):
        H.add_edge(u, v, **{**d, "required": d.get("demand", 0) > 0})
    single = rural.solve_rural(H, depot=depot, time_limit=10, local_seconds=2)
    P = rural.Problem(H, depot)
    dem = [d.get("demand", 0) for u, v, d in H.edges(data=True) if d["required"]]
    starts = []
    for circ in tour_variants(P, single.circuit, 8):
        seq = orient(P, tour_sequence(P, circ, dem))
        rts = split_capacity(P, seq, capacity)
        starts.append((sum(route_cost(P, r) for r in rts), rts))
    starts.sort(key=lambda x: x[0])
    split_total, routes = starts[0]
    routes = improve_capacity(P, routes, capacity, local_seconds)
    costs = [route_cost(P, r) for r in routes]
    info = {"split_total": split_total, "single_tour": single.total_cost,
            "objective_value": sum(costs), "vehicles": len(routes),
            "loads": [sum(e[3] for e in r) for r in routes]}
    return FleetSolution("route first, cluster second + relocation", [_expand(P, r) for r in routes],
                         costs, max(costs), sum(costs), single.lower_bound, False,
                         time.perf_counter() - t0, info)
