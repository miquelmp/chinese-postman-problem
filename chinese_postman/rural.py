"""Rural Postman Problem: serve only some streets, travel along any.

This is the second extension proposed in the 1997 conclusions: a street costs one amount the
first time (it is served: snow ploughed, bins emptied) and another on any later pass (the
vehicle only travels along it). Here every street carries

    weight   - the cost of travelling along it (deadheading)
    service  - the cost of the pass that serves it (default: weight)
    required - whether it must be served (default: True)

and the tour must serve every required street once, starting and ending at the depot.

* All streets required, connected network: polynomial. The served passes cost sum(service);
  the extra passes are an ordinary CPP augmentation on `weight` (Edmonds' matching).
* Required streets forming one connected piece (plus the depot): still polynomial, by the
  same matching, with shortest paths through the whole network.
* Otherwise the problem is NP-hard (Lenstra & Rinnooy Kan 1976). Three methods share one
  reduced graph on the required vertices:
    - `heuristic`  Frederickson (1979): join the pieces by a minimum spanning tree, then fix
      parity by a matching. At most 3/2 times the optimum (Benavent et al. 1985); a local
      search on the joining tree then removes most of the excess in practice.
    - `lower_bound` the linear relaxation of the model below, with the cut of every piece.
    - `solve_exact` integer program on the reduced graph, solved by HiGHS, with connectivity
      cuts added whenever the solution falls apart (Ghiani & Laporte 2000 use the same model).
  `solve_rural` combines them like `mixed.solve_mixed`: heuristic, then branch-and-cut told
  to beat it; if it cannot, the heuristic tour is proven optimal.
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.csgraph import dijkstra, minimum_spanning_tree

from .cpp import min_weight_pairing
from .euler import eulerian_circuit


@dataclass
class RuralSolution:
    method: str
    total_cost: float           # service + deadheading
    service_cost: float         # sum of service costs of the required streets
    deadhead_cost: float        # cost of every pass that does not serve
    lower_bound: float
    optimal: bool
    circuit: list               # vertex sequence from the depot back to the depot
    seconds: float
    info: dict = field(default_factory=dict)

    @property
    def gap_pct(self) -> float:
        lb = self.lower_bound
        return 100.0 * max(self.total_cost - lb, 0.0) / lb if lb else 0.0


# ---------------------------------------------------------------------------- preparation

class Problem:
    """Shortest paths between the required vertices and the pieces of the required streets."""

    def __init__(self, G: nx.MultiGraph, depot=None):
        if G.is_directed():
            raise ValueError("rural.Problem expects an undirected graph")
        self.G = G
        self.nodes = list(G.nodes)
        self.pos = {v: i for i, v in enumerate(self.nodes)}
        self.R = []                                   # (u, v, service) required streets
        best = {}
        for u, v, d in G.edges(data=True):
            w = float(d.get("weight", 1))
            if d.get("required", True):
                self.R.append((u, v, float(d.get("service", w))))
            if u != v:
                a, b = self.pos[u], self.pos[v]
                if (a, b) not in best or best[a, b] > w:
                    best[a, b] = best[b, a] = w
        if not self.R:
            raise ValueError("No required streets")
        n = len(self.nodes)
        rows, cols = zip(*best) if best else ((), ())
        self.A = csr_matrix((list(best.values()), (rows, cols)), shape=(n, n))
        self.depot = depot if depot is not None else self.R[0][0]
        vr = {self.depot}
        for u, v, _ in self.R:
            vr.update((u, v))
        self.V = sorted(vr, key=lambda x: self.pos[x])          # required vertices
        self.vi = {v: i for i, v in enumerate(self.V)}
        src = [self.pos[v] for v in self.V]
        dist, self.pred = dijkstra(self.A, indices=src, return_predecessors=True)
        self.D = dist[:, src]                                   # |V| x |V| distances
        if not np.isfinite(self.D).all():
            raise ValueError("The required streets and the depot are not all connected")
        self.service = sum(s for *_, s in self.R)
        # pieces: connected components of the required streets, the depot alone if isolated
        uf = list(range(len(self.V)))

        def find(x):
            while uf[x] != x:
                uf[x] = uf[uf[x]]
                x = uf[x]
            return x
        for u, v, _ in self.R:
            uf[find(self.vi[u])] = find(self.vi[v])
        comp = {}
        for i in range(len(self.V)):
            comp.setdefault(find(i), []).append(i)
        self.pieces = list(comp.values())
        self.piece_of = np.empty(len(self.V), int)
        for p, members in enumerate(self.pieces):
            self.piece_of[members] = p
        self.deg = np.zeros(len(self.V), int)                   # degree in the required streets
        for u, v, _ in self.R:
            self.deg[self.vi[u]] += 1
            self.deg[self.vi[v]] += 1

    def path(self, i, j):
        """Shortest path between required vertices i and j (indices into V) as graph nodes."""
        row, target = i, self.pos[self.V[j]]
        out = [target]
        while out[-1] != self.pos[self.V[i]]:
            out.append(self.pred[row, out[-1]])
        return [self.nodes[k] for k in reversed(out)]

    def deadhead_edges(self):
        """Edges of the reduced graph: pairs of required vertices whose shortest path does not
        pass through a third required vertex (the others are never needed)."""
        D, m = self.D, len(self.V)
        out = []
        for i in range(m):
            for j in range(i + 1, m):
                d = D[i, j]
                via = D[i, :] + D[:, j]
                via[[i, j]] = np.inf
                if via.min() > d + 1e-9:
                    out.append((i, j, float(d)))
        return out


# ---------------------------------------------------------------------------- tours

def _parity_pairs(P: Problem, extra):
    """Odd vertices of required streets + `extra` deadhead links, paired at minimum cost."""
    deg = P.deg.copy()
    for i, j in extra:
        deg[i] += 1
        deg[j] += 1
    odd = [i for i in range(len(P.V)) if deg[i] % 2]
    if not odd:
        return [], 0.0
    pairs = min_weight_pairing(odd, P.D)
    return pairs, float(sum(P.D[i, j] for i, j in pairs))


def _connected(P: Problem, links):
    uf = list(range(len(P.pieces)))

    def find(x):
        while uf[x] != x:
            uf[x] = uf[uf[x]]
            x = uf[x]
        return x
    for i, j in links:
        uf[find(P.piece_of[i])] = find(P.piece_of[j])
    return len({find(p) for p in range(len(P.pieces))}) == 1


def _circuit(P: Problem, links):
    """Euler tour of the required streets plus deadhead links (expanded to shortest paths)."""
    E = nx.MultiGraph()
    for u, v, s in P.R:
        E.add_edge(u, v, weight=s)
    for i, j in links:
        p = P.path(i, j)
        for a, b in zip(p, p[1:]):
            E.add_edge(a, b, weight=0)
    return eulerian_circuit(E, P.depot)


def _solution(P, method, links, bound, optimal, t0, info=None, seq=None):
    """From deadhead links (exact methods) or from a sequence of served streets (heuristic)."""
    from . import sequence as S
    if seq is not None:
        total = S.route_cost(P, seq)
        circ = S.expand(P, seq)
    else:
        total = P.service + float(sum(P.D[i, j] for i, j in links))
        circ = _circuit(P, links)
    return RuralSolution(method, total, P.service, total - P.service, bound,
                         optimal or total <= bound + 1e-9, circ, time.perf_counter() - t0, info or {})


# ---------------------------------------------------------------------------- heuristic

def _piece_distances(P: Problem):
    k = len(P.pieces)
    W = np.full((k, k), np.inf)
    arg = {}
    for a in range(k):
        for b in range(a + 1, k):
            sub = P.D[np.ix_(P.pieces[a], P.pieces[b])]
            r, c = np.unravel_index(np.argmin(sub), sub.shape)
            W[a, b] = W[b, a] = sub[r, c]
            arg[a, b] = arg[b, a] = (P.pieces[a][r], P.pieces[b][c])
    return W, arg


def heuristic(P: Problem, local_seconds: float = 10.0):
    """Frederickson's method plus a local search on the links that join the pieces.
    Returns (deadhead links, cost of deadheading, info)."""
    k = len(P.pieces)
    info = {"pieces": k}
    if k == 1:
        pairs, c = _parity_pairs(P, [])
        return pairs, c, info
    W, arg = _piece_distances(P)
    T = minimum_spanning_tree(csr_matrix(np.where(np.isfinite(W), W + 1e-12, 0))).tocoo()
    tree = [(int(a), int(b)) for a, b in zip(T.row, T.col)]

    def evaluate(tree):
        joins = [arg[a, b] for a, b in tree]
        pairs, c = _parity_pairs(P, joins)
        return joins + list(pairs), c + sum(W[a, b] for a, b in tree)

    links, cost = evaluate(tree)
    info["frederickson"] = P.service + cost
    # local search: drop one tree link, reconnect the two sides by another link, keep if cheaper;
    # also try dropping a tree link outright when the parity links already join the pieces
    t0, improved = time.perf_counter(), True
    while improved and time.perf_counter() - t0 < local_seconds:
        improved = False
        for e in list(tree):
            if time.perf_counter() - t0 > local_seconds:
                break
            rest = [x for x in tree if x != e]
            side = _side(k, rest, e[0])
            cands = [(W[a, b], a, b) for a in side for b in range(k) if b not in side]
            cands.sort()
            options = [rest + [(a, b)] for _, a, b in cands[:6] if (a, b) != e and (b, a) != e]
            joins = [arg[a, b] for a, b in rest]
            pairs, c = _parity_pairs(P, joins)
            if _connected(P, joins + list(pairs)):
                options.append(rest)
            for t in options:
                l2, c2 = evaluate(t)
                if c2 < cost - 1e-9 and _connected(P, l2):
                    tree, links, cost, improved = t, l2, c2, True
                    break
            if improved:
                break
    info["local_search_s"] = time.perf_counter() - t0
    return links, cost, info


def _side(k, tree, start):
    adj = {i: [] for i in range(k)}
    for a, b in tree:
        adj[a].append(b)
        adj[b].append(a)
    seen, stack = {start}, [start]
    while stack:
        for y in adj[stack.pop()]:
            if y not in seen:
                seen.add(y)
                stack.append(y)
    return seen


# ---------------------------------------------------------------------------- exact model

def _model(P: Problem):
    """x_e in {0,1,2}: passes over reduced edge e; z_v integer: half the degree.
    Parity: x(delta(v)) - 2 z_v = -deg_R(v) mod 2."""
    E = P.deadhead_edges()
    m, n = len(E), len(P.V)
    r, c, val = [], [], []
    for j, (a, b, _) in enumerate(E):
        r += [a, b]; c += [j, j]; val += [1.0, 1.0]
    for v in range(n):
        r.append(v); c.append(m + v); val.append(-2.0)
    A = coo_matrix((val, (r, c)), shape=(n, m + n)).tocsr()
    rhs = -(P.deg % 2).astype(float)
    cost = np.array([d for *_, d in E] + [0.0] * n)
    lb = np.zeros(m + n)
    ub = np.array([2.0] * m + [np.inf] * n)
    cons = [LinearConstraint(A, rhs, rhs)]
    odd = [v for v in range(n) if P.deg[v] % 2]
    if odd:                                   # an odd vertex needs at least one extra pass
        r2, c2 = [], []
        for t, v in enumerate(odd):
            for j, (a, b, _) in enumerate(E):
                if v in (a, b):
                    r2.append(t); c2.append(j)
        B = coo_matrix((np.ones(len(r2)), (r2, c2)), shape=(len(odd), m + n)).tocsr()
        cons.append(LinearConstraint(B, 1, np.inf))
    return E, cost, cons, Bounds(lb, ub)


def _cut(P: Problem, E, S, nvars):
    """x(delta(S)) >= 2 for a set S of required-vertex indices."""
    row = np.zeros(nvars)
    for j, (a, b, _) in enumerate(E):
        if (a in S) != (b in S):
            row[j] = 1.0
    return row


def _piece_cuts(P, E, nvars):
    if len(P.pieces) == 1:
        return []
    return [_cut(P, E, set(p), nvars) for p in P.pieces]


def lower_bound(P: Problem, rounds: int = 30, seconds: float = 20.0) -> float:
    """Best of two bounds on the cost of any tour:
    * parity: every odd vertex of the required streets must be paired, so the deadheading
      costs at least a minimum matching of them (the CPP argument of chapter 3);
    * connectivity: the linear relaxation of the model, with the cut around every piece and
      further cuts x(delta(S)) >= 2 found by minimum cuts of the fractional solution."""
    _, parity = _parity_pairs(P, [])
    if len(P.pieces) == 1:
        return P.service + parity
    t0 = time.perf_counter()
    E, cost, cons, bnd = _model(P)
    cuts = _piece_cuts(P, E, len(cost))
    value = 0.0
    for _ in range(rounds):
        res = milp(cost, constraints=cons + [LinearConstraint(np.array(cuts), 2, np.inf)],
                   integrality=np.zeros(len(cost)), bounds=bnd)
        if res.status != 0:
            break
        value = float(res.fun)
        new = _fractional_cuts(P, E, res.x)
        if not new or time.perf_counter() - t0 > seconds:
            break
        cuts += [_cut(P, E, S, len(cost)) for S in new]
    return P.service + max(parity, value)


def _fractional_cuts(P, E, x):
    """Sets S (unions of pieces) with x(delta(S)) < 2, from a minimum cut of the piece graph."""
    k = len(P.pieces)
    W = nx.Graph()
    W.add_nodes_from(range(k))
    for j, (a, b, _) in enumerate(E):
        if x[j] > 1e-9:
            pa, pb = int(P.piece_of[a]), int(P.piece_of[b])
            if pa != pb:
                w = W[pa][pb]["weight"] + x[j] if W.has_edge(pa, pb) else x[j]
                W.add_edge(pa, pb, weight=w)
    out = []
    comps = list(nx.connected_components(W))
    if len(comps) > 1:
        sets = comps
    else:
        val, (A, _) = nx.stoer_wagner(W)
        sets = [A] if val < 2 - 1e-6 else []
    for C in sets:
        out.append({v for p in C for v in P.pieces[p]})
    return out


def _components_of(P, E, x):
    uf = list(range(len(P.V)))

    def find(a):
        while uf[a] != a:
            uf[a] = uf[uf[a]]
            a = uf[a]
        return a
    for u, v, _ in P.R:
        uf[find(P.vi[u])] = find(P.vi[v])
    for j, (a, b, _) in enumerate(E):
        if x[j] > 0.5:
            uf[find(a)] = find(b)
    comp = {}
    for i in range(len(P.V)):
        comp.setdefault(find(i), set()).add(i)
    return list(comp.values())


def solve_exact(P: Problem, time_limit: float = 60.0, cutoff: float | None = None):
    """Branch-and-cut: HiGHS solves the integer program; whenever its solution is disconnected,
    the cut around each component is added and the program solved again.
    Returns (status, deadhead links or None, best lower bound on deadheading, rounds)."""
    t0 = time.perf_counter()
    E, cost, cons, bnd = _model(P)
    nv = len(cost)
    cuts = _piece_cuts(P, E, nv)
    integral = np.allclose(cost, np.round(cost))
    rounds, bound = 0, 0.0
    while True:
        left = time_limit - (time.perf_counter() - t0)
        if left <= 0.5:
            return "time limit", None, bound, rounds
        cc = list(cons)
        if cuts:
            cc.append(LinearConstraint(np.array(cuts), 2, np.inf))
        if cutoff is not None:
            cc.append(LinearConstraint(cost[None, :], -np.inf, cutoff))
        res = milp(cost, constraints=cc, integrality=np.ones(nv), bounds=bnd,
                   options={"time_limit": left, "disp": False})
        rounds += 1
        if res.status == 2:
            return "infeasible", None, bound, rounds
        dual = getattr(res, "mip_dual_bound", None)
        if dual is not None and np.isfinite(dual):
            bound = max(bound, float(dual))
        if res.x is None:
            return "time limit", None, bound, rounds
        comps = _components_of(P, E, res.x)
        if len(comps) == 1:
            if res.status != 0:            # feasible but not proven within the time limit
                return "time limit", _links(E, res.x), bound, rounds
            return "optimal", _links(E, res.x), float(res.fun), rounds
        for S in comps:
            cuts.append(_cut(P, E, S, nv))


def _links(E, x):
    out = []
    for j, (a, b, _) in enumerate(E):
        out += [(a, b)] * int(round(x[j]))
    return out


# ---------------------------------------------------------------------------- combined

def solve_rural(G: nx.MultiGraph, depot=None, time_limit: float = 60.0,
                local_seconds: float = 10.0) -> RuralSolution:
    """Serve every required street at least cost.

    One piece of required streets: exact, polynomial (matching), always.
    Several pieces: Frederickson's heuristic, a local search on the resulting route, then
    branch-and-cut told to beat it within `time_limit`. The result carries the best tour found
    and the best proven lower bound."""
    from . import sequence as S
    t0 = time.perf_counter()
    P = Problem(G, depot)
    links, cost, info = heuristic(P, local_seconds / 2)
    if len(P.pieces) == 1:
        return _solution(P, "matching (exact, polynomial)", links, P.service + cost, True, t0, info)
    seq = S.from_circuit(P, _circuit(P, links))
    seq, total = S.improve(P, seq, local_seconds / 2)
    use_seq = total < P.service + cost - 1e-9
    best = min(total, P.service + cost)
    lb = lower_bound(P, seconds=min(20.0, time_limit / 4))
    integral = all(float(c).is_integer() for *_, c in P.R) and np.allclose(P.D, np.round(P.D))
    if integral:
        lb = float(np.ceil(lb - 1e-6))
    info.update({"heuristic_cost": best, "lp_bound": lb, "heuristic_s": time.perf_counter() - t0})

    def heur(method, bound, optimal):
        return _solution(P, method, links, bound, optimal, t0, info, seq if use_seq else None)
    if best <= lb + 1e-9:
        return heur("heuristic (proven optimal by bound)", lb, True)
    left = time_limit - (time.perf_counter() - t0)
    if left > 1:
        dead = best - P.service
        cutoff = dead - 1 if integral else dead * (1 - 1e-9)
        status, ex, dbound, rounds = solve_exact(P, left, cutoff)
        info.update({"exact_status": status, "cut_rounds": rounds})
        if status == "infeasible":
            return heur("heuristic (proven optimal by branch-and-cut)", best, True)
        lb = max(lb, P.service + dbound)
        if integral:
            lb = float(np.ceil(lb - 1e-6))
        if ex is not None:
            d2 = float(sum(P.D[i, j] for i, j in ex))
            if P.service + d2 < best - 1e-9:
                opt = status == "optimal"
                return _solution(P, "branch-and-cut" if opt else "branch-and-cut (time limit)",
                                 ex, P.service + d2 if opt else lb, opt, t0, info)
    return heur("heuristic", lb, False)


def solve_brute_force(G: nx.MultiGraph, depot=None) -> float:
    """Optimum by enumerating multiplicities 0..2 of every reduced edge (tiny graphs only)."""
    P = Problem(G, depot)
    E = P.deadhead_edges()
    if len(E) > 13:
        raise ValueError("too many reduced edges for brute force")
    best = np.inf
    for xs in itertools.product((0, 1, 2), repeat=len(E)):
        deg = P.deg.copy()
        c = 0.0
        for (a, b, d), x in zip(E, xs):
            deg[a] += x; deg[b] += x; c += x * d
        if c >= best or (deg % 2).any():
            continue
        if len(_components_of(P, E, np.array(xs, float))) == 1:
            best = c
    return P.service + best


def solve_two_costs(G, start=None):
    """Every street required, first pass at `service`, later passes at `weight`:
    exact and polynomial, undirected (matching) or directed (min-cost flow)."""
    from .cpp import solve_directed
    if G.is_directed():
        service = sum(d.get("service", d.get("weight", 1)) for *_, d in G.edges(data=True))
        sol = solve_directed(G, start)
        return service + sol.added_cost, sol
    H = nx.MultiGraph()
    for u, v, d in G.edges(data=True):
        H.add_edge(u, v, **{**d, "required": True})
    return solve_rural(H, depot=start)
