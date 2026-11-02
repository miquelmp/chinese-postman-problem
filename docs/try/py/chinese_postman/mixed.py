"""Mixed Chinese Postman Problem: two-way streets (edges) and one-way streets (arcs).

A link is (u, v, cost, oneway). A one-way link may only be traversed u -> v; a two-way link
in either direction. Every link must be traversed at least once; extra traversals cost again.

Three methods share one model. With x(u->v) = number of traversals of a link in that direction:

    min  sum cost * x
    s.t. at every vertex: traversals out = traversals in
         one-way link:  x(u->v) >= 1
         two-way link:  x(u->v) + x(v->u) >= 1
         x integer >= 0

* `lower_bound`  — the linear relaxation (HiGHS LP). Its optimum is half-integral.
* `solve_exact`  — the integer program, solved by HiGHS branch-and-cut (scipy.optimize.milp).
* `solve_heuristic` — orient each two-way link as the LP suggests, then add the cheapest
  extra traversals that balance every vertex (min-cost flow, exact for that orientation).
  Polynomial; the LP value certifies how far it can be from the optimum.

Mixed CPP is NP-hard (Papadimitriou 1976); the heuristic follows the orient-then-balance idea
of Frederickson (1979).
"""
from __future__ import annotations

import collections
import itertools
import time
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from .euler import eulerian_circuit


@dataclass
class MixedGraph:
    links: list                      # (u, v, cost, oneway)

    @property
    def nodes(self):
        return sorted({x for u, v, *_ in self.links for x in (u, v)}, key=str)

    def counts(self):
        one = sum(1 for *_, o in self.links if o)
        return len(self.nodes), len(self.links) - one, one

    def digraph(self):
        """Every allowed direction of travel, keeping the cheapest parallel link."""
        D = nx.DiGraph()
        D.add_nodes_from(self.nodes)
        for u, v, c, one in self.links:
            for a, b in ((u, v),) if one else ((u, v), (v, u)):
                if not D.has_edge(a, b) or D[a][b]["weight"] > c:
                    D.add_edge(a, b, weight=c)
        return D

    def is_feasible(self):
        D = self.digraph()
        return D.number_of_nodes() > 0 and nx.is_strongly_connected(D)


@dataclass
class MixedSolution:
    method: str
    total_cost: float
    original_cost: float
    lower_bound: float | None
    optimal: bool
    circuit: list
    traversals: list                 # (u, v, times) per direction actually used
    seconds: float
    info: dict = field(default_factory=dict)

    @property
    def gap_to_bound_pct(self):
        if self.lower_bound in (None, 0):
            return None
        return 100 * (self.total_cost - self.lower_bound) / self.lower_bound


# ------------------------------------------------------------------ the model
def _model(M: MixedGraph):
    nodes = M.nodes
    idx = {v: i for i, v in enumerate(nodes)}
    cols = []                        # (link index, tail, head, cost)
    for k, (u, v, c, one) in enumerate(M.links):
        cols.append((k, u, v, c))
        if not one:
            cols.append((k, v, u, c))
    n, nv = len(nodes), len(cols)
    r, cc, val = [], [], []
    for j, (_, a, b, _) in enumerate(cols):
        r += [idx[a], idx[b]]; cc += [j, j]; val += [1.0, -1.0]
    A_bal = coo_matrix((val, (r, cc)), shape=(n, nv)).tocsr()
    rows = {k: [] for k in range(len(M.links))}
    for j, (k, *_) in enumerate(cols):
        rows[k].append(j)
    r = [k for k in rows for _ in rows[k]]
    cc = [j for k in rows for j in rows[k]]
    A_cov = coo_matrix((np.ones(len(r)), (r, cc)), shape=(len(M.links), nv)).tocsr()
    cost = np.array([c for *_, c in cols], float)
    cons = [LinearConstraint(A_bal, 0, 0), LinearConstraint(A_cov, 1, np.inf)]
    return cols, cost, cons


def _tour(M, cols, x, start):
    G = nx.MultiDiGraph()
    trav = []
    for (k, a, b, c), t in zip(cols, x):
        t = int(round(t))
        if t:
            trav.append((a, b, t))
            for _ in range(t):
                G.add_edge(a, b, weight=c)
    return eulerian_circuit(G, start), trav


def lower_bound(M: MixedGraph):
    cols, cost, cons = _model(M)
    res = milp(cost, constraints=cons, integrality=np.zeros(len(cost)), bounds=Bounds(0, np.inf))
    if res.status != 0:
        raise ValueError(f"LP failed: {res.message}")
    return float(res.fun), cols, res.x


def solve_exact(M: MixedGraph, time_limit: float = 300.0, start=None) -> MixedSolution:
    if not M.is_feasible():
        raise ValueError("Mixed graph must be strongly connected")
    t0 = time.perf_counter()
    cols, cost, cons = _model(M)
    res = milp(cost, constraints=cons, integrality=np.ones(len(cost)), bounds=Bounds(0, np.inf),
               options={"time_limit": time_limit, "mip_rel_gap": 0.0, "disp": False})
    secs = time.perf_counter() - t0
    if res.x is None:
        raise RuntimeError(f"No integer solution within {time_limit} s: {res.message}")
    optimal = res.status == 0
    circ, trav = _tour(M, cols, res.x, start)
    bound = float(getattr(res, "mip_dual_bound", np.nan))
    return MixedSolution("exact", float(round(res.fun, 6)), sum(c for _, _, c, _ in M.links),
                         bound, optimal, circ, trav, secs,
                         {"status": res.message, "mip_gap": float(getattr(res, "mip_gap", np.nan))})


def _balance(M: MixedGraph, oriented):
    """Cheapest extra traversals that balance a fixed orientation (min-cost flow).
    `oriented` = list of (tail, head) for each link's compulsory traversal."""
    D = M.digraph()
    for v in D:
        D.nodes[v]["demand"] = 0
    for a, b in oriented:
        D.nodes[a]["demand"] += 1        # a has one more traversal out: it must receive flow
        D.nodes[b]["demand"] -= 1
    cost, flow = nx.network_simplex(D)
    return cost, flow


class _Balancer:
    """Min-cost rebalancing for a fixed orientation, as an LP (HiGHS) so that the vertex duals
    are available. Network matrices give integral optimal vertices, so the flow is integral."""

    def __init__(self, M: MixedGraph):
        from scipy.optimize import linprog  # noqa: F401  (imported here to fail early)
        D = M.digraph()
        self.nodes = list(D.nodes)
        self.idx = {v: i for i, v in enumerate(self.nodes)}
        self.arcs = list(D.edges(data="weight"))
        r, c, val = [], [], []
        for j, (a, b, w) in enumerate(self.arcs):
            r += [self.idx[b], self.idx[a]]; c += [j, j]; val += [1.0, -1.0]   # inflow - outflow
        self.A = coo_matrix((val, (r, c)), shape=(len(self.nodes), len(self.arcs))).tocsr()
        self.cost = np.array([w for *_, w in self.arcs], float)

    def solve(self, oriented):
        from scipy.optimize import linprog
        dem = np.zeros(len(self.nodes))
        for a, b in oriented:
            dem[self.idx[a]] += 1      # a has one more traversal out: needs one more in
            dem[self.idx[b]] -= 1
        res = linprog(self.cost, A_eq=self.A, b_eq=dem, bounds=(0, None), method="highs")
        if res.status != 0:
            raise RuntimeError(res.message)
        flow = {}
        for (a, b, w), f in zip(self.arcs, res.x):
            f = int(round(f))
            if f:
                flow.setdefault(a, {})[b] = f
        return float(res.fun), flow, res.eqlin.marginals


def _local_search(M, oriented, bal, max_seconds=60.0, tries=25):
    """Flip two-way links whose first-order cost change, 2·(m_b − m_a) for a link oriented
    a -> b (m = vertex duals of the rebalancing LP), is negative. Each flip is verified by an
    exact re-solve and kept only if it lowers the cost; stop when no tried flip improves."""
    t0 = time.perf_counter()
    oriented = list(oriented)
    cost, flow, m = bal.solve(oriented)
    two = [k for k, l in enumerate(M.links) if not l[3]]
    flips = 0
    while time.perf_counter() - t0 < max_seconds:
        est = []
        for k in two:
            a, b = oriented[k]
            est.append((2 * (m[bal.idx[b]] - m[bal.idx[a]]), k))
        est.sort()
        improved = False
        for e, k in est[:tries]:
            if e >= -1e-9:
                break
            a, b = oriented[k]
            oriented[k] = (b, a)
            c2, f2, m2 = bal.solve(oriented)
            if c2 < cost - 1e-9:
                cost, flow, m = c2, f2, m2
                flips += 1
                improved = True
                break
            oriented[k] = (a, b)
        if not improved:
            break
    return cost, flow, oriented, flips


def _underlying(M: MixedGraph) -> nx.MultiGraph:
    U = nx.MultiGraph()
    for u, v, c, _ in M.links:
        U.add_edge(u, v, weight=c)
    return U


def _euler_orientation(M: MixedGraph, circuit, reverse=False):
    """Direction of each two-way link = the way an Eulerian circuit of the parity-fixed
    underlying graph first crosses it. One-way links keep their direction."""
    pending = collections.defaultdict(list)
    for k, (u, v, c, one) in enumerate(M.links):
        if not one:
            pending[frozenset((u, v))].append(k)
    seq = circuit[::-1] if reverse else circuit
    oriented = [(u, v) for u, v, *_ in M.links]
    for a, b in zip(seq, seq[1:]):
        q = pending.get(frozenset((a, b)))
        if q:
            oriented[q.pop()] = (a, b)
    return oriented


def bounds(M: MixedGraph):
    """Two valid lower bounds: the LP relaxation (ignores parity) and the undirected CPP of the
    underlying graph (ignores directions). Returns (best, lp, undirected, lp_data, cpp_solution)."""
    from .cpp import solve_undirected
    lp = lower_bound(M)
    und = solve_undirected(_underlying(M))
    return max(lp[0], und.total_cost), lp[0], und.total_cost, lp, und


def solve_heuristic(M: MixedGraph, start=None, pre=None, local_seconds: float = 60.0) -> MixedSolution:
    """Four starting orientations — LP rounding (two tie rules) and the Euler-circuit
    orientation of the parity-fixed underlying graph (both directions) — each completed by an
    exact min-cost rebalance; the two best are improved by dual-guided flips (local search)."""
    if not M.is_feasible():
        raise ValueError("Mixed graph must be strongly connected")
    t0 = time.perf_counter()
    lb, lp_val, und_val, (_, cols, x), und = pre if pre is not None else bounds(M)
    fwd = {}
    for (k, a, b, c), t in zip(cols, x):
        u = M.links[k][0]
        fwd.setdefault(k, [0.0, 0.0])[0 if a == u else 1] += t
    candidates = []
    for tie in (0, 1):                 # two roundings for links the LP leaves at 1/2 each way
        oriented = []
        for k, (u, v, c, one) in enumerate(M.links):
            f, b = fwd[k]
            rev = (not one) and (b > f + 1e-9 or (abs(b - f) <= 1e-9 and tie == 1))
            oriented.append((v, u) if rev else (u, v))
        candidates.append((f"lp-round-{tie}", oriented))
    for rev in (False, True):
        candidates.append((f"euler-{'rev' if rev else 'fwd'}", _euler_orientation(M, und.circuit, rev)))
    bal = _Balancer(M)
    tried = {}
    for name, oriented in candidates:
        tried[name] = bal.solve(oriented)[0]
    # local search from the two best starting orientations
    best = None
    flips_total = 0
    for name in sorted(tried, key=tried.get)[:2]:
        oriented = dict(candidates)[name]
        extra, flow, oriented, flips = _local_search(M, oriented, bal, max_seconds=local_seconds / 2)
        flips_total += flips
        if best is None or extra < best[0]:
            best = (extra, oriented, flow, name)
    extra, oriented, flow, tie = best
    G = nx.MultiDiGraph()
    D = M.digraph()
    for (a, b), (u, v, c, one) in zip(oriented, M.links):
        G.add_edge(a, b, weight=c)
    for a, out in flow.items():
        for b, t in out.items():
            for _ in range(t):
                G.add_edge(a, b, weight=D[a][b]["weight"])
    circ = eulerian_circuit(G, start)
    original = sum(c for _, _, c, _ in M.links)
    trav = [(a, b, n) for (a, b), n in collections.Counter(G.edges()).items()]
    ties = sum(1 for k in fwd if abs(fwd[k][0] - fwd[k][1]) <= 1e-9 and not M.links[k][3])
    return MixedSolution("heuristic", original + extra, original, lb, False, circ, trav,
                         time.perf_counter() - t0,
                         {"half_links": ties, "winner": tie, "lp_bound": lp_val, "flips": flips_total,
                          "undirected_bound": und_val,
                          "candidates": {k: original + v for k, v in tried.items()}})


def solve_mixed(M: MixedGraph, time_limit: float = 300.0, gap_tol: float = 0.0,
                start=None) -> MixedSolution:
    """Combined strategy: heuristic first, exact branch-and-cut only while it can still pay off.

    1. Bounds + heuristic (seconds): a good tour and a certified gap.
    2. If that gap is already within `gap_tol`, stop.
    3. Otherwise run branch-and-cut for the remaining time, told to look only for tours cheaper
       than the heuristic (an objective cutoff) and to stop at `gap_tol`. If no cheaper tour
       exists the model is infeasible, which proves the heuristic tour optimal.
    The result always carries the best tour found and the best proven lower bound.

    gap_tol = 0 (default): prove the optimum unless the time limit runs out.
    gap_tol = 0.005: accept any tour certified within 0.5% of the optimum (much faster on
    large networks)."""
    if not M.is_feasible():
        raise ValueError("Mixed graph must be strongly connected")
    t0 = time.perf_counter()
    pre = bounds(M)
    he = solve_heuristic(M, start=start, pre=pre, local_seconds=min(60.0, time_limit / 5))
    lb = pre[0]
    integral = all(float(c).is_integer() for _, _, c, _ in M.links)
    if integral:
        lb = float(np.ceil(lb - 1e-6))
    info = {"heuristic_cost": he.total_cost, "heuristic_s": time.perf_counter() - t0,
            "exact_ran": False, "exact_status": "", "phase_bound": "cheap bounds"}

    def finish(sol, bound, optimal, method):
        gap = (sol.total_cost - bound) / bound if bound else 0.0
        info.update({"gap_pct": round(100 * max(gap, 0.0), 3), "total_s": time.perf_counter() - t0})
        optimal = optimal or gap <= 1e-12
        return MixedSolution(method, sol.total_cost, sol.original_cost, bound, optimal,
                             sol.circuit, sol.traversals, time.perf_counter() - t0, info)

    if he.total_cost <= lb + 1e-9:
        return finish(he, lb, True, "heuristic (proven optimal by bound)")
    if (he.total_cost - lb) / lb <= gap_tol:
        return finish(he, lb, False, "heuristic (within tolerance)")

    remaining = time_limit - (time.perf_counter() - t0)
    if remaining <= 1:
        return finish(he, lb, False, "heuristic (no time left for exact)")
    cols, cost, cons = _model(M)
    cutoff = he.total_cost - 1 if integral else he.total_cost * (1 - 1e-9)
    cons = cons + [LinearConstraint(cost[None, :], -np.inf, cutoff)]
    res = milp(cost, constraints=cons, integrality=np.ones(len(cost)), bounds=Bounds(0, np.inf),
               options={"time_limit": remaining, "mip_rel_gap": gap_tol, "disp": False})
    info.update({"exact_ran": True, "exact_status": res.message, "exact_s": res.get("time", None)})
    dual = getattr(res, "mip_dual_bound", None)
    if res.status == 2:                        # infeasible: nothing beats the heuristic tour
        info["phase_bound"] = "cutoff infeasible"
        return finish(he, he.total_cost, True, "heuristic (proven optimal by branch-and-cut)")
    if dual is not None and np.isfinite(dual):
        lb = max(lb, float(np.ceil(dual - 1e-6)) if integral else float(dual))
        info["phase_bound"] = "branch-and-cut"
    if res.x is not None and res.fun < he.total_cost - 1e-9:
        circ, trav = _tour(M, cols, res.x, start)
        ex = MixedSolution("exact", float(round(res.fun, 6)), he.original_cost, lb, False,
                           circ, trav, 0.0)
        info["exact_cost"] = ex.total_cost
        return finish(ex, lb, False, "branch-and-cut")
    return finish(he, lb, False, "heuristic (branch-and-cut found nothing better in time)")


def solve_brute_force(M: MixedGraph) -> float:
    """Exact optimum by enumerating the direction of every two-way link (tiny cases only)."""
    two = [k for k, l in enumerate(M.links) if not l[3]]
    if len(two) > 16:
        raise ValueError("Too many two-way links for brute force")
    original = sum(c for _, _, c, _ in M.links)
    best = np.inf
    for bits in itertools.product((0, 1), repeat=len(two)):
        rev = dict(zip(two, bits))
        oriented = [(v, u) if rev.get(k) else (u, v) for k, (u, v, c, o) in enumerate(M.links)]
        best = min(best, _balance(M, oriented)[0])
    return original + best


# ------------------------------------------------------------------ instances
def from_graph(G: nx.MultiGraph, oneway_frac: float, seed: int = 0) -> MixedGraph:
    """Make a fraction of the links one-way (random direction), keeping strong connectivity:
    any one-way link that breaks it is turned back into a two-way street."""
    import random
    rnd = random.Random(seed)
    links = []
    for u, v, w in G.edges(data="weight"):
        if rnd.random() < oneway_frac:
            links.append((u, v, w, True) if rnd.random() < 0.5 else (v, u, w, True))
        else:
            links.append((u, v, w, False))
    M = MixedGraph(links)
    order = [k for k, l in enumerate(links) if l[3]]
    rnd.shuffle(order)
    while not M.is_feasible():
        D = M.digraph()
        comp = {v: i for i, c in enumerate(nx.strongly_connected_components(D)) for v in c}
        k = next(k for k in order if M.links[k][3] and comp[M.links[k][0]] != comp[M.links[k][1]])
        u, v, w, _ = M.links[k]
        M.links[k] = (u, v, w, False)
    return M


def city_grid(rows: int, cols: int, oneway_street_frac: float = 0.6, block: int = 80,
              avenue: int = 270, seed: int = 0) -> MixedGraph:
    """Grid town where whole streets are one-way (as in most city centres): each row or column
    street is one-way with the given probability, in a random direction."""
    import random
    rnd = random.Random(seed)
    idx = lambda r, c: r * cols + c + 1
    links = []
    for r in range(rows):
        one = rnd.random() < oneway_street_frac
        d = rnd.random() < 0.5
        for c in range(cols - 1):
            a, b = idx(r, c), idx(r, c + 1)
            links.append(((b, a) if d else (a, b)) + (block + rnd.randint(-8, 8), one))
    for c in range(cols):
        one = rnd.random() < oneway_street_frac
        d = rnd.random() < 0.5
        for r in range(rows - 1):
            a, b = idx(r, c), idx(r + 1, c)
            links.append(((b, a) if d else (a, b)) + (avenue + rnd.randint(-20, 20), one))
    M = MixedGraph(links)
    while not M.is_feasible():        # repair as in from_graph, keeping the street pattern
        if True:
            D = M.digraph()
            comp = {v: i for i, cc in enumerate(nx.strongly_connected_components(D)) for v in cc}
            k = next(k for k, l in enumerate(M.links) if l[3] and comp[l[0]] != comp[l[1]])
            u, v, w, _ = M.links[k]
            M.links[k] = (u, v, w, False)
    return M
