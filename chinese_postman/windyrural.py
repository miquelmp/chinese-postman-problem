"""Rural postman on networks with a cost for each direction of each street.

A link is (u, v, cost_uv, cost_vu, required), where None forbids a direction. So this one model covers
the windy, mixed and directed rural postman problems. Required links must be driven; the others may
be. All these problems are NP-hard. With x(u->v) the number of passes in that direction:

    min  sum cost * x
    s.t. at every vertex: passes out = passes in
         every required link: x(u->v) + x(v->u) >= 1
         every set S that separates required links: x(leaving S) >= 1
         x integer >= 0

The connectivity constraints are added round by round, as in `rural.solve_exact`.

* `lower_bound`     — the linear relaxation with the constraints on the first pieces.
* `solve_heuristic` — the undirected rural postman on summed costs followed by the windy postman on
                      its Eulerian network, or else an orientation of the required links, a
                      min-cost rebalance and shortest paths to join the pieces; then reversals.
* `solve_exact`     — branch-and-cut, with cuts added between integer solutions.
* `solve`           — heuristic first, then branch-and-cut told to beat it.
"""
from __future__ import annotations

import collections
import re
import time
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.csgraph import dijkstra

from . import rural
from .euler import eulerian_circuit
from .windy import WindyGraph, _Balancer


@dataclass
class RuralProblem:
    """Links with a cost each way, some of them required, and an optional depot."""
    links: list                      # (u, v, cost_uv, cost_vu, required)
    depot: object = None

    @property
    def windy(self):
        """The network without the service requirement."""
        return WindyGraph([l[:4] for l in self.links])

    def is_feasible(self):
        """Return True if every required link and the depot lie in one strongly connected part."""
        D = self.windy.digraph()
        needed = {x for u, v, *_, r in self.links if r for x in (u, v)}
        if self.depot is not None:
            needed.add(self.depot)
        return any(needed <= c for c in nx.strongly_connected_components(D))

    def required_pieces(self):
        """Vertex sets of the connected pieces of required links, with the depot."""
        G = nx.Graph()
        if self.depot is not None:
            G.add_node(self.depot)
        G.add_edges_from((u, v) for u, v, *_, r in self.links if r)
        return [set(c) for c in nx.connected_components(G)]


@dataclass
class RuralSolution:
    """A route with its cost, lower bound and whether it is proven optimal."""
    method: str
    total_cost: float
    lower_bound: float | None
    optimal: bool
    circuit: list
    seconds: float
    info: dict = field(default_factory=dict)

    @property
    def gap_to_bound_pct(self):
        """Percentage by which the route exceeds the lower bound, or None without a bound."""
        if self.lower_bound in (None, 0):
            return None
        return 100 * (self.total_cost - self.lower_bound) / self.lower_bound


def read_instance(path: str, forbidden: int = 99999999) -> RuralProblem:
    """Read an instance in the format of Corberan et al.: required links, then the others, each as
    `(i, j) coste c_ij c_ji`. Costs of at least `forbidden` forbid that direction."""
    with open(path, encoding="latin-1") as f:
        text = f.read()
    parts = re.split(r"LISTA_ARISTAS_NOREQ\s*:", text)
    pattern = r"\(\s*(\d+),\s*(\d+)\)\s+coste\s+(\d+)\s+(\d+)"
    links = []
    for required, part in zip((True, False), parts):
        for i, j, a, b in re.findall(pattern, part):
            a, b = int(a), int(b)
            links.append((int(i), int(j), None if a >= forbidden else a, None if b >= forbidden else b, required))
    if not links:
        raise ValueError(f"{path}: no streets found")
    return RuralProblem(links)


def read_directed(path: str) -> RuralProblem:
    """Read a directed instance in the format of Campos et al., as distributed with OAR Lib: counts,
    then one line `tail, head, cost, required` for each arc."""
    with open(path, encoding="latin-1") as f:
        lines = f.read().splitlines()
    links = []
    for line in lines[5:]:
        t = [x.strip() for x in line.split(",")]
        if len(t) == 4:
            links.append((int(t[0]), int(t[1]), int(t[2]), None, t[3] == "1"))
    if not links:
        raise ValueError(f"{path}: no arcs found")
    return RuralProblem(links)


# ------------------------------------------------------------------ the model
def _columns(P):
    W = P.windy
    return [(k, a, b, c) for k in range(len(P.links)) for a, b, c in W.directions(k)]


def _base_model(P):
    nodes = sorted({x for u, v, *_ in P.links for x in (u, v)}, key=str)
    idx = {v: i for i, v in enumerate(nodes)}
    cols = _columns(P)
    r, cc, val = [], [], []
    for j, (_, a, b, _) in enumerate(cols):
        r += [idx[a], idx[b]]; cc += [j, j]; val += [1.0, -1.0]
    bal = coo_matrix((val, (r, cc)), shape=(len(nodes), len(cols))).tocsr()
    req = [k for k, l in enumerate(P.links) if l[4]]
    row = {k: i for i, k in enumerate(req)}
    r = [row[k] for j, (k, *_) in enumerate(cols) if k in row]
    cc = [j for j, (k, *_) in enumerate(cols) if k in row]
    cover = coo_matrix((np.ones(len(r)), (r, cc)), shape=(len(req), len(cols))).tocsr()
    cost = np.array([c for *_, c in cols], float)
    return cols, cost, [LinearConstraint(bal, 0, 0), LinearConstraint(cover, 1, np.inf)]


def _cut(cols, sets):
    """Rows x(leaving S) >= 1 for each vertex set S."""
    r, cc = [], []
    for i, S in enumerate(sets):
        for j, (_, a, b, _) in enumerate(cols):
            if a in S and b not in S:
                r.append(i); cc.append(j)
    A = coo_matrix((np.ones(len(r)), (r, cc)), shape=(len(sets), len(cols))).tocsr()
    return LinearConstraint(A, 1, np.inf)


def _pieces_of(arcs, P):
    """Weak components of the driven arcs that contain required links or the depot."""
    G = nx.Graph()
    if P.depot is not None:
        G.add_node(P.depot)
    G.add_edges_from((a, b) for a, b, *_ in arcs)
    needed = {x for u, v, *_, r in P.links if r for x in (u, v)}
    if P.depot is not None:
        needed.add(P.depot)
    return [set(c) for c in nx.connected_components(G) if c & needed]


def _arcs_of(cols, x):
    return [(a, b, c, int(round(t))) for (_, a, b, c), t in zip(cols, x) if round(t)]


def _circuit(arcs, start):
    G = nx.MultiDiGraph()
    for a, b, c, n in arcs:
        for _ in range(n):
            G.add_edge(a, b, weight=c)
    return eulerian_circuit(G, start)


def lower_bound(P: RuralProblem):
    """The linear relaxation with a cut around each required piece. Returns (value, columns, x)."""
    cols, cost, cons = _base_model(P)
    pieces = P.required_pieces()
    if len(pieces) > 1:
        cons = cons + [_cut(cols, pieces)]
    res = milp(cost, constraints=cons, integrality=np.zeros(len(cost)), bounds=Bounds(0, np.inf))
    if res.status != 0:
        raise ValueError(f"LP failed: {res.message}")
    return float(res.fun), cols, res.x


def _branch_and_cut(P, time_limit, cutoff=None):
    """Integer program with cuts added between solves. Returns (arcs, total, bound, proved, status),
    where arcs is None if no connected solution was found."""
    t0 = time.perf_counter()
    cols, cost, cons = _base_model(P)
    pieces = P.required_pieces()
    sets = list(pieces) if len(pieces) > 1 else []
    if cutoff is not None:
        cons = cons + [LinearConstraint(cost.reshape(1, -1), -np.inf, cutoff)]
    bound, rounds = None, 0
    while True:
        left = time_limit - (time.perf_counter() - t0)
        if left <= 0:
            return None, None, bound, False, "time limit"
        rounds += 1
        all_cons = cons + ([_cut(cols, sets)] if sets else [])
        res = milp(cost, constraints=all_cons, integrality=np.ones(len(cost)), bounds=Bounds(0, np.inf),
                   options={"time_limit": left, "mip_rel_gap": 0.0, "disp": False})
        dual = getattr(res, "mip_dual_bound", None)
        if dual is not None and not np.isnan(dual):
            bound = max(bound or 0.0, float(dual))
        if res.status == 2:
            return None, None, bound, True, "infeasible"
        if res.x is None:
            return None, None, bound, False, "time limit"
        arcs = _arcs_of(cols, res.x)
        found = _pieces_of(arcs, P)
        if len(found) == 1:
            return arcs, float(round(res.fun, 6)), bound, res.status == 0, f"{rounds} rounds"
        new = [s for s in found if s not in sets]
        if not new:
            return None, None, bound, False, "no new cut"
        sets += new


def solve_exact(P: RuralProblem, time_limit: float = 300.0, start=None) -> RuralSolution:
    """Solve the integer program with HiGHS, adding connectivity cuts between integer solutions."""
    if not P.is_feasible():
        raise ValueError("The required streets and the depot must lie in one strongly connected part")
    t0 = time.perf_counter()
    arcs, total, bound, proved, status = _branch_and_cut(P, time_limit)
    if arcs is None:
        raise RuntimeError(f"No connected solution within {time_limit} s")
    return RuralSolution("exact", total, bound, proved, _circuit(arcs, start or P.depot),
                         time.perf_counter() - t0, {"status": status})


# ------------------------------------------------------------------ heuristic
class _Paths:
    """Shortest directed paths on the cheapest arcs."""

    def __init__(self, P):
        self.D = D = P.windy.digraph()
        self.nodes = list(D.nodes)
        self.idx = {v: i for i, v in enumerate(self.nodes)}
        e = list(D.edges(data="weight"))
        w = np.array([max(c, 1e-9) for *_, c in e])
        A = csr_matrix((w, ([self.idx[a] for a, *_ in e], [self.idx[b] for _, b, _ in e])),
                       shape=(len(self.nodes), len(self.nodes)))
        self.dist, self.pred = dijkstra(A, directed=True, return_predecessors=True)

    def path(self, a, b):
        """The arcs of a shortest path from a to b, as (tail, head, cost)."""
        i, j = self.idx[a], self.idx[b]
        out = []
        while j != i:
            k = self.pred[i, j]
            x, y = self.nodes[k], self.nodes[j]
            out.append((x, y, self.D[x][y]["weight"]))
            j = k
        return out[::-1]


def _join(P, arcs, paths):
    """One-way paths that join the pieces of `arcs`, chosen as a minimum spanning tree."""
    pieces = _pieces_of(arcs, P)
    added = []
    while len(pieces) > 1:
        tree, rest = pieces[0], pieces[1:]
        ti = [paths.idx[v] for v in tree]
        best = None
        for q, S in enumerate(rest):
            si = [paths.idx[v] for v in S]
            sub = paths.dist[np.ix_(ti, si)]
            u, v = np.unravel_index(np.argmin(sub), sub.shape)
            if best is None or sub[u, v] < best[0]:
                best = (sub[u, v], ti[u], si[v], q)
        _, a, b, q = best
        added += paths.path(paths.nodes[a], paths.nodes[b])
        pieces = [tree | rest[q]] + [s for i, s in enumerate(rest) if i != q]
    return added


def _complete(P, forced, bal, paths):
    """Rebalance `forced` arcs and join pieces until one Eulerian tour exists."""
    forced = list(forced)
    while True:
        extra, flow, duals = bal.solve(forced)
        arcs = [(a, b, c, 1) for a, b, c in forced] + flow
        joins = _join(P, arcs, paths)
        if not joins:
            return sum(c for *_, c in forced) + extra, arcs, forced, duals
        forced += joins


def _improve(P, W, forced, n_req, bal, paths, max_seconds, tries=25):
    """Reverse required two-way links with a promising dual estimate, keeping real improvements."""
    t0 = time.perf_counter()
    total, arcs, forced, m = _complete(P, forced, bal, paths)
    req = [k for k, l in enumerate(P.links) if l[4]]
    flips = 0
    two = [i for i, k in enumerate(req) if None not in P.links[k][2:4]]

    def other(i):
        a, b, _ = forced[i]
        return next(d for d in W.directions(req[i]) if d[:2] == (b, a))

    while time.perf_counter() - t0 < max_seconds:
        est = sorted((other(i)[2] - forced[i][2] + 2 * (m[bal.idx[forced[i][1]]] - m[bal.idx[forced[i][0]]]), i)
                     for i in two)
        improved = False
        for e, i in est[:tries]:
            if e >= -1e-9:
                break
            trial = list(forced)
            trial[i] = other(i)
            t2, a2, f2, m2 = _complete(P, trial[:n_req], bal, paths)
            if t2 < total - 1e-9:
                total, arcs, forced, m = t2, a2, f2, m2
                flips += 1
                improved = True
                break
        if not improved:
            break
    return total, arcs, flips


def _from_undirected(P: RuralProblem, W: WindyGraph, seconds: float = 20.0, local_seconds: float = 3.0):
    """Benavent et al.'s idea, after Win: solve the undirected rural postman on the sum of both costs,
    then the windy postman on the Eulerian network it gives. Returns driven arcs, or None."""
    G = nx.MultiGraph()
    for u, v, a, b, r in P.links:
        G.add_edge(u, v, weight=(a + b) if None not in (a, b) else 2 * (a if b is None else b), required=r)
    R = rural.Problem(G, P.depot)
    deadhead, _, _ = rural.heuristic(R, local_seconds=local_seconds)
    seq = rural._circuit(R, deadhead)
    passes = collections.Counter(frozenset(e) for e in zip(seq, seq[1:]))
    groups = collections.defaultdict(list)
    for k, l in enumerate(P.links):
        groups[frozenset(l[:2])].append(k)
    copies = {k: 0 for k in range(len(P.links))}
    for key, ks in groups.items():
        req = [k for k in ks if P.links[k][4]]
        for k in req:
            copies[k] = 1
        extra = passes.get(key, 0) - len(req)
        if extra > 0:
            cheap = min(ks, key=lambda k: sum(c for c in P.links[k][2:4] if c is not None))
            copies[cheap] += extra
    cols = _columns(P)
    bal = _base_model(P)[2][0]
    k_col = [k for k, *_ in cols]
    A = coo_matrix((np.ones(len(cols)), (k_col, range(len(cols)))), shape=(len(P.links), len(cols))).tocsr()
    low = np.array([copies[k] for k in range(len(P.links))], float)
    cost = np.array([c for *_, c in cols], float)
    res = milp(cost, constraints=[bal, LinearConstraint(A, low, np.inf)], integrality=np.ones(len(cols)),
               bounds=Bounds(0, np.inf), options={"mip_rel_gap": 0.0, "time_limit": seconds})
    return None if res.x is None else _arcs_of(cols, res.x)


def _orientation_of(P, W, arcs):
    """The direction in which each required link is driven by `arcs`."""
    left = collections.Counter()
    for a, b, _, n in arcs:
        left[a, b] += n
    out = []
    for k, l in enumerate(P.links):
        if l[4]:
            opts = W.directions(k)
            pick = next((d for d in opts if left[d[0], d[1]] > 0), opts[0])
            left[pick[0], pick[1]] -= 1
            out.append(pick)
    return out


def solve_heuristic(P: RuralProblem, start=None, pre=None, local_seconds: float = 30.0) -> RuralSolution:
    """Orient the required links from the relaxation or at their cheaper direction, rebalance, join
    the pieces, and improve the two best starts by reversals."""
    if not P.is_feasible():
        raise ValueError("The required streets and the depot must lie in one strongly connected part")
    t0 = time.perf_counter()
    lp, cols, x = pre if pre is not None else lower_bound(P)
    W = P.windy
    amount = {}
    for (k, a, b, c), t in zip(cols, x):
        amount[k, a, b] = t
    req = [k for k, l in enumerate(P.links) if l[4]]
    starts = {"cheaper": [min(W.directions(k), key=lambda d: d[2]) for k in req]}
    for tie in (0, 1):
        starts[f"lp-{tie}"] = [max(W.directions(k), key=lambda d: (round(amount[k, d[0], d[1]], 9),
                                                                    -d[2] if tie == 0 else d[2])) for k in req]
    bal, paths = _Balancer(W), _Paths(P)
    direct = None
    if any(None not in l[2:4] for l in P.links):
        arcs = _from_undirected(P, W)
        if arcs is not None:
            direct = (float(sum(c * n for _, _, c, n in arcs)), arcs, "undirected")
            starts["undirected"] = _orientation_of(P, W, arcs)
    scored = {n: _complete(P, o, bal, paths)[0] for n, o in starts.items()}
    best, flips = None, 0
    for name in sorted(scored, key=scored.get)[:2]:
        total, arcs, f = _improve(P, W, starts[name], len(req), bal, paths, local_seconds / 2)
        flips += f
        if best is None or total < best[0]:
            best = (total, arcs, name)
    if direct is not None and direct[0] < best[0]:
        best = direct
    total, arcs, name = best
    return RuralSolution("heuristic", float(total), lp, False, _circuit(arcs, start or P.depot),
                         time.perf_counter() - t0, {"start": name, "flips": flips, "lp_bound": lp})


def solve(P: RuralProblem, time_limit: float = 300.0, start=None, local_seconds: float = 6.0) -> RuralSolution:
    """Heuristic first, then branch-and-cut told to find a cheaper route. If it proves that there
    is none, the heuristic route is optimal."""
    t0 = time.perf_counter()
    pre = lower_bound(P)
    he = solve_heuristic(P, start=start, pre=pre, local_seconds=local_seconds)
    integral = all(float(c).is_integer() for l in P.links for c in l[2:4] if c is not None)
    lb = float(np.ceil(pre[0] - 1e-6)) if integral else pre[0]
    info = dict(he.info, heuristic=he.total_cost)
    if he.total_cost <= lb + 1e-9:
        return RuralSolution("heuristic", he.total_cost, lb, True, he.circuit, time.perf_counter() - t0, info)
    cutoff = he.total_cost - 1 if integral else he.total_cost * (1 - 1e-9)
    left = max(1.0, time_limit - (time.perf_counter() - t0))
    arcs, total, bound, proved, status = _branch_and_cut(P, left, cutoff)
    seconds = time.perf_counter() - t0
    info["status"] = status
    if status == "infeasible":
        return RuralSolution("heuristic, proved", he.total_cost, he.total_cost, True, he.circuit, seconds, info)
    bound = lb if bound is None else max(lb, float(np.ceil(bound - 1e-6)) if integral else bound)
    if arcs is not None and total < he.total_cost - 1e-9:
        return RuralSolution("branch-and-cut", total, bound, proved, _circuit(arcs, start or P.depot), seconds, info)
    return RuralSolution("heuristic", he.total_cost, min(bound, he.total_cost), False, he.circuit, seconds, info)
