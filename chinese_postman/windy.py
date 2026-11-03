"""Windy Postman Problem: every street can be driven both ways, at a different cost each way.

A link is (u, v, cost_uv, cost_vu), where None forbids that direction, so the mixed and undirected
problems are special cases. Every link must be traversed at least once. With x(u->v) the number of
traversals of a link in that direction:

    min  sum cost * x
    s.t. at every vertex: traversals out = traversals in
         every link: x(u->v) + x(v->u) >= 1
         x integer >= 0

It is NP-hard in general (Brucker 1981; Guan 1984). Three methods share the model.

* `bounds`          — the linear relaxation, and the undirected CPP on the cheaper direction.
* `solve_exact`     — the integer program, solved by HiGHS branch-and-cut.
* `solve_win`       — Win (1989): an undirected CPP on average costs, then the windy postman on the
                      resulting Eulerian graph, which is polynomial.
* `solve_heuristic` — the starting orientations of `solve_win` and of the relaxation, completed by
                      an exact min-cost rebalance and improved by dual-guided flips.
"""
from __future__ import annotations

import collections
import re
import time
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import coo_matrix

from .cpp import solve_undirected
from .euler import eulerian_circuit
from .mixed import MixedGraph


@dataclass
class WindyGraph:
    """A street network with one cost for each direction of each link."""
    links: list                      # (u, v, cost_uv, cost_vu), None forbids a direction

    @property
    def nodes(self):
        """All vertices, sorted."""
        return sorted({x for u, v, *_ in self.links for x in (u, v)}, key=str)

    def directions(self, k):
        """The allowed directions of link k, as (tail, head, cost)."""
        u, v, a, b = self.links[k]
        return [d for d in ((u, v, a), (v, u, b)) if d[2] is not None]

    def digraph(self):
        """Every allowed direction of travel, keeping the cheapest parallel link."""
        D = nx.DiGraph()
        D.add_nodes_from(self.nodes)
        for k in range(len(self.links)):
            for a, b, c in self.directions(k):
                if not D.has_edge(a, b) or D[a][b]["weight"] > c:
                    D.add_edge(a, b, weight=c)
        return D

    def is_feasible(self):
        """Return True if a tour exists: the network is strongly connected."""
        D = self.digraph()
        return D.number_of_nodes() > 0 and nx.is_strongly_connected(D)


@dataclass
class WindySolution:
    """A windy tour with its cost, lower bound and whether it is proven optimal."""
    method: str
    total_cost: float
    lower_bound: float | None
    optimal: bool
    circuit: list
    seconds: float
    info: dict = field(default_factory=dict)

    @property
    def gap_to_bound_pct(self):
        """Percentage by which the tour exceeds the lower bound, or None without a bound."""
        if self.lower_bound in (None, 0):
            return None
        return 100 * (self.total_cost - self.lower_bound) / self.lower_bound


def from_mixed(M: MixedGraph) -> WindyGraph:
    """The windy form of a mixed network: a one-way link forbids its reverse direction."""
    return WindyGraph([(u, v, c, None if one else c) for u, v, c, one in M.links])


def from_graph(G: nx.MultiGraph, asymmetry: float, seed: int = 0) -> WindyGraph:
    """Give each edge costs c(1 + r) and c(1 - r), with r uniform in [-asymmetry, asymmetry],
    rounded to integers of at least 1, so that a round trip costs about the same as before."""
    import random
    rnd = random.Random(seed)
    links = []
    for u, v, c in G.edges(data="weight"):
        r = rnd.uniform(-asymmetry, asymmetry)
        links.append((u, v, max(1, round(c * (1 + r))), max(1, round(c * (1 - r)))))
    return WindyGraph(links)


def read_wpp(path: str, forbidden: int = 99999999) -> WindyGraph:
    """Read an instance in the format of Corberan et al.: `(i, j) coste c_ij c_ji`. Costs of at
    least `forbidden` forbid that direction."""
    with open(path, encoding="latin-1") as f:
        text = f.read()
    links = []
    for i, j, a, b in re.findall(r"\(\s*(\d+),\s*(\d+)\)\s+coste\s+(\d+)\s+(\d+)", text):
        a, b = int(a), int(b)
        links.append((int(i), int(j), None if a >= forbidden else a, None if b >= forbidden else b))
    if not links:
        raise ValueError(f"{path}: no streets found")
    return WindyGraph(links)


# ------------------------------------------------------------------ the model
def _model(W: WindyGraph):
    nodes = W.nodes
    idx = {v: i for i, v in enumerate(nodes)}
    cols = [(k, a, b, c) for k in range(len(W.links)) for a, b, c in W.directions(k)]
    r, cc, val = [], [], []
    for j, (_, a, b, _) in enumerate(cols):
        r += [idx[a], idx[b]]; cc += [j, j]; val += [1.0, -1.0]
    A_bal = coo_matrix((val, (r, cc)), shape=(len(nodes), len(cols))).tocsr()
    k_col = [k for k, *_ in cols]
    A_cov = coo_matrix((np.ones(len(cols)), (k_col, range(len(cols)))),
                       shape=(len(W.links), len(cols))).tocsr()
    cost = np.array([c for *_, c in cols], float)
    return cols, cost, [LinearConstraint(A_bal, 0, 0), LinearConstraint(A_cov, 1, np.inf)]


def _circuit(arcs, start):
    G = nx.MultiDiGraph()
    for a, b, c, n in arcs:
        for _ in range(n):
            G.add_edge(a, b, weight=c)
    return eulerian_circuit(G, start)


def bounds(W: WindyGraph):
    """Two valid lower bounds: the linear relaxation (ignores parity) and the undirected CPP with
    each street at its cheaper direction (any tour pays at least that for each pass).
    Returns (best, lp, undirected, (columns, solution))."""
    cols, cost, cons = _model(W)
    res = milp(cost, constraints=cons, integrality=np.zeros(len(cost)), bounds=Bounds(0, np.inf))
    if res.status != 0:
        raise ValueError(f"LP failed: {res.message}")
    G = nx.MultiGraph()
    for u, v, a, b in W.links:
        G.add_edge(u, v, weight=min(c for c in (a, b) if c is not None))
    und = solve_undirected(G, backend="auto").total_cost
    return max(float(res.fun), und), float(res.fun), und, (cols, res.x)


def solve_exact(W: WindyGraph, time_limit: float = 300.0, start=None) -> WindySolution:
    """Solve the integer program with HiGHS, with zero relative gap, within `time_limit`."""
    if not W.is_feasible():
        raise ValueError("The network must be strongly connected")
    t0 = time.perf_counter()
    cols, cost, cons = _model(W)
    res = milp(cost, constraints=cons, integrality=np.ones(len(cost)), bounds=Bounds(0, np.inf),
               options={"time_limit": time_limit, "mip_rel_gap": 0.0, "disp": False})
    if res.x is None:
        raise RuntimeError(f"No integer solution within {time_limit} s: {res.message}")
    arcs = [(a, b, c, int(round(t))) for (_, a, b, c), t in zip(cols, res.x)]
    return WindySolution("exact", float(round(res.fun, 6)), float(getattr(res, "mip_dual_bound", np.nan)),
                         res.status == 0, _circuit(arcs, start), time.perf_counter() - t0)


def _on_eulerian(W: WindyGraph, multiplicity):
    """Solve the windy postman on the Eulerian multigraph with `multiplicity[k]` copies of link k.
    Win (1989) shows this is polynomial, because the relaxation has an integral optimum there."""
    cols, cost, (bal, _) = _model(W)
    k_col = [k for k, *_ in cols]
    A_cov = coo_matrix((np.ones(len(cols)), (k_col, range(len(cols)))),
                       shape=(len(W.links), len(cols))).tocsr()
    low = np.array([multiplicity[k] for k in range(len(W.links))], float)
    res = milp(cost, constraints=[bal, LinearConstraint(A_cov, low, np.inf)],
               integrality=np.ones(len(cols)), bounds=Bounds(0, np.inf), options={"mip_rel_gap": 0.0})
    if res.x is None:
        raise RuntimeError(res.message)
    return [(a, b, c, int(round(t))) for (_, a, b, c), t in zip(cols, res.x)]


def _copies(W: WindyGraph):
    """How many times an undirected CPP on average costs passes along each link, with costs
    doubled to stay integers."""
    G = nx.MultiGraph()
    best = {}
    for k, (u, v, a, b) in enumerate(W.links):
        G.add_edge(u, v, weight=a + b)
        key = frozenset((u, v))
        if key not in best or a + b < sum(W.links[best[key]][2:]):
            best[key] = k
    copies = {k: 1 for k in range(len(W.links))}
    for u, v, _ in solve_undirected(G, backend="auto").duplicated:
        copies[best[frozenset((u, v))]] += 1
    return copies


def solve_win(W: WindyGraph, start=None) -> WindySolution:
    """Win (1989), for networks where every link can be driven both ways. At most twice the
    optimum, and optimal when the network is already Eulerian."""
    if any(None in l[2:] for l in W.links):
        raise ValueError("Win's method needs both directions of every link")
    t0 = time.perf_counter()
    arcs = _on_eulerian(W, _copies(W))
    total = sum(c * n for _, _, c, n in arcs)
    return WindySolution("win", float(total), None, False, _circuit(arcs, start), time.perf_counter() - t0)


class _Balancer:
    """Min-cost rebalancing for a fixed orientation, with the vertex duals of the LP."""

    def __init__(self, W: WindyGraph):
        D = W.digraph()
        self.idx = {v: i for i, v in enumerate(D.nodes)}
        self.arcs = list(D.edges(data="weight"))
        r, c, val = [], [], []
        for j, (a, b, _) in enumerate(self.arcs):
            r += [self.idx[b], self.idx[a]]; c += [j, j]; val += [1.0, -1.0]
        self.A = coo_matrix((val, (r, c)), shape=(len(self.idx), len(self.arcs))).tocsr()
        self.cost = np.array([w for *_, w in self.arcs], float)

    def solve(self, oriented):
        """Return (extra cost, flow per arc, duals) for `oriented`, a (tail, head, cost) per link."""
        dem = np.zeros(len(self.idx))
        for a, b, _ in oriented:
            dem[self.idx[a]] += 1
            dem[self.idx[b]] -= 1
        res = linprog(self.cost, A_eq=self.A, b_eq=dem, bounds=(0, None), method="highs")
        if res.status != 0:
            raise RuntimeError(res.message)
        flow = [(a, b, w, int(round(f))) for (a, b, w), f in zip(self.arcs, res.x) if round(f)]
        return float(res.fun), flow, res.eqlin.marginals


def _improve(W, oriented, bal, max_seconds, tries=25):
    """Reverse links whose first-order change, c(b, a) - c(a, b) + 2 (m_b - m_a) for a link driven
    a -> b, is negative. Each reversal is checked by an exact re-solve and kept only if it pays."""
    t0 = time.perf_counter()
    oriented = list(oriented)
    extra, flow, m = bal.solve(oriented)
    total = extra + sum(c for *_, c in oriented)
    flips = 0
    two = [k for k in range(len(W.links)) if None not in W.links[k][2:]]

    def other(k):
        a, b, _ = oriented[k]
        return next(d for d in W.directions(k) if d[:2] == (b, a))

    while time.perf_counter() - t0 < max_seconds:
        est = sorted((other(k)[2] - oriented[k][2] + 2 * (m[bal.idx[oriented[k][1]]] - m[bal.idx[oriented[k][0]]]), k)
                     for k in two)
        improved = False
        for e, k in est[:tries]:
            if e >= -1e-9:
                break
            old, oriented[k] = oriented[k], other(k)
            x2, f2, m2 = bal.solve(oriented)
            t2 = x2 + sum(c for *_, c in oriented)
            if t2 < total - 1e-9:
                total, flow, m = t2, f2, m2
                flips += 1
                improved = True
                break
            oriented[k] = old
        if not improved:
            break
    return total, flow, oriented, flips


def solve_heuristic(W: WindyGraph, start=None, pre=None, local_seconds: float = 60.0) -> WindySolution:
    """Orient every link from the relaxation (two tie rules) or at its cheaper direction, complete
    each by an exact rebalance, improve the two best by reversals, and return the best tour found,
    Win's among them when it applies."""
    if not W.is_feasible():
        raise ValueError("The network must be strongly connected")
    t0 = time.perf_counter()
    lb, lp_val, und_val, (cols, x) = pre if pre is not None else bounds(W)
    amount = collections.defaultdict(dict)
    for (k, a, b, c), t in zip(cols, x):
        amount[k][a, b] = (t, c)
    starts = {}
    for tie in (0, 1):
        oriented = []
        for k in range(len(W.links)):
            opts = W.directions(k)
            pick = max(opts, key=lambda d: (round(amount[k][d[:2]][0], 9), -d[2] if tie == 0 else d[2]))
            oriented.append(pick)
        starts[f"lp-{tie}"] = oriented
    starts["cheaper"] = [min(W.directions(k), key=lambda d: d[2]) for k in range(len(W.links))]
    bal = _Balancer(W)
    scored = {n: bal.solve(o)[0] + sum(c for *_, c in o) for n, o in starts.items()}
    best, flips = None, 0
    for name in sorted(scored, key=scored.get)[:2]:
        total, flow, oriented, f = _improve(W, starts[name], bal, local_seconds / 2)
        flips += f
        if best is None or total < best[0]:
            best = (total, flow, oriented, name)
    total, flow, oriented, name = best
    arcs = [(a, b, c, 1) for a, b, c in oriented] + flow
    win = None
    if all(None not in l[2:] for l in W.links):
        win = solve_win(W)
        if win.total_cost < total:
            total, name, arcs = win.total_cost, "win", None
    circuit = win.circuit if arcs is None else _circuit(arcs, start)
    return WindySolution("heuristic", float(total), lb, False, circuit, time.perf_counter() - t0,
                         {"winner": name, "flips": flips, "lp_bound": lp_val, "undirected_bound": und_val,
                          "win": win.total_cost if win else None})


def solve_windy(W: WindyGraph, time_limit: float = 300.0, start=None) -> WindySolution:
    """Heuristic and bounds first, then branch-and-cut told to find a tour cheaper than the
    heuristic's. If it proves there is none, the heuristic's tour is optimal."""
    t0 = time.perf_counter()
    pre = bounds(W)
    he = solve_heuristic(W, start=start, pre=pre)
    lb = pre[0]
    integral = all(float(c).is_integer() for l in W.links for c in l[2:] if c is not None)
    if integral:
        lb = float(np.ceil(lb - 1e-6))
    if he.total_cost <= lb + 1e-9:
        return WindySolution("heuristic", he.total_cost, lb, True, he.circuit, time.perf_counter() - t0, he.info)
    cols, cost, cons = _model(W)
    cutoff = he.total_cost - 1 if integral else he.total_cost * (1 - 1e-9)
    left = max(1.0, time_limit - (time.perf_counter() - t0))
    res = milp(cost, constraints=cons + [LinearConstraint(cost.reshape(1, -1), -np.inf, cutoff)],
               integrality=np.ones(len(cost)), bounds=Bounds(0, np.inf),
               options={"time_limit": left, "mip_rel_gap": 0.0, "disp": False})
    info = dict(he.info, heuristic=he.total_cost)
    seconds = time.perf_counter() - t0
    if res.status == 2:                # infeasible: nothing beats the heuristic's tour
        return WindySolution("heuristic, proved", he.total_cost, he.total_cost, True, he.circuit, seconds, info)
    dual = float(getattr(res, "mip_dual_bound", np.nan))
    bound = max(lb, float(np.ceil(dual - 1e-6)) if integral else dual) if not np.isnan(dual) else lb
    if res.x is not None and res.fun < he.total_cost - 1e-9:
        arcs = [(a, b, c, int(round(t))) for (_, a, b, c), t in zip(cols, res.x)]
        return WindySolution("branch-and-cut", float(round(res.fun, 6)), bound, res.status == 0,
                             _circuit(arcs, start), seconds, info)
    return WindySolution("heuristic", he.total_cost, min(bound, he.total_cost), False, he.circuit, seconds, info)
