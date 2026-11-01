"""JSON-friendly entry points used by the website (run in the browser through Pyodide).

An *instance* is a plain dict:

    {"name": str,
     "nodes": [{"id": int, "x": float, "y": float, "label": str}, ...],
     "links": [{"u": int, "v": int, "w": int, "oneway": bool}, ...],
     "units": "m" | "",              # unit of the costs, for display
     "note": str}

`solve(instance)` returns a dict with the costs, the tour and how often each link is driven.
Everything here uses the pure-Python backends (NetworkX, SciPy/HiGHS); no native code.
"""
from __future__ import annotations

import json
import math
import random
import time

import networkx as nx

from . import instances as I
from .cpp import solve_directed, solve_undirected
from .mixed import MixedGraph, city_grid, solve_mixed

MAX_NODES = 2500          # browser safety limit


# ------------------------------------------------------------------ building instances
def _inst(name, pos, links, units="", note="", labels=None):
    ids = {v: i for i, v in enumerate(pos)}
    nodes = [{"id": ids[v], "x": float(pos[v][0]), "y": float(pos[v][1]),
              "label": str(labels.get(v, v)) if labels else str(v)} for v in pos]
    L = [{"u": ids[u], "v": ids[v], "w": int(round(w)), "oneway": bool(o)} for u, v, w, o in links]
    return {"name": name, "nodes": nodes, "links": L, "units": units, "note": note}


def _layout(G, seed=1):
    if G.number_of_nodes() <= 60:
        try:
            return nx.kamada_kawai_layout(nx.Graph(G), weight=None)
        except Exception:
            pass
    return nx.spring_layout(nx.Graph(G), seed=seed, iterations=200)


PFC_POS = {1: (0.42, 0.95), 8: (0.08, 0.78), 4: (0.80, 0.86), 7: (0.36, 0.60),
           5: (0.80, 0.48), 2: (1.00, 0.30), 6: (0.36, 0.24), 3: (0.68, 0.10)}
PFC_EDGES = [(1, 8, 2), (1, 7, 1), (8, 7, 5), (1, 4, 6), (7, 4, 4), (7, 6, 7),
             (4, 5, 2), (6, 5, 1), (6, 3, 4), (3, 5, 7), (5, 2, 6), (3, 2, 9)]


def example(name: str, size: int = 10, oneway: float = 0.6, seed: int = 0) -> dict:
    """Ready-made instances. `size` is the grid side or the number of junctions."""
    if name == "pfc1997":
        return _inst("1997 worked example (park maintenance network)", PFC_POS,
                     [(u, v, w, False) for u, v, w in PFC_EDGES],
                     note="From chapter 3 of both reports; the optimum is 63 = 54 + 9.")
    if name == "konigsberg":
        pos = {"A": (0.5, 0.5), "B": (0.45, 0.95), "C": (0.45, 0.05), "D": (0.95, 0.5)}
        links = [("A", "B", 1, False), ("A", "B", 1, False), ("A", "C", 1, False),
                 ("A", "C", 1, False), ("A", "D", 1, False), ("B", "D", 1, False),
                 ("C", "D", 1, False)]
        return _inst("Seven bridges of Königsberg", pos, links, note="Cost = number of bridge crossings.",
                     labels={"A": "Kneiphof", "B": "North bank", "C": "South bank", "D": "East"})
    if name == "petersen":
        G = nx.petersen_graph()
        pos = nx.shell_layout(G, [list(range(5)), list(range(5, 10))])
        return _inst("Petersen graph", {v: pos[v] for v in G}, [(u, v, 1, False) for u, v in G.edges],
                     note="Every vertex is odd; a perfect matching doubles 5 of the 15 edges.")
    if name == "grid":
        s = max(2, min(size, 40))
        G = I.manhattan(s, s, drop=0.1, seed=seed)
        pos = {v: ((v - 1) % s, (v - 1) // s) for v in G}
        return _inst(f"Grid town {s}×{s}", pos, [(u, v, w, False) for u, v, w in G.edges(data="weight")],
                     units="m", note="Short blocks along streets, long ones along avenues; 10% closed.")
    if name == "delaunay":
        n = max(10, min(size, MAX_NODES))
        G = I.delaunay_town(n, seed=seed)
        pos = {v: G.nodes[v]["pos"] for v in G}
        return _inst(f"Organic town, {n} junctions", pos,
                     [(u, v, w, False) for u, v, w in G.edges(data="weight")], units="m")
    if name == "oneway-grid":
        s = max(3, min(size, 40))
        D = I.one_way_grid(s, s, seed=seed)
        pos = {v: ((v - 1) % s, (v - 1) // s) for v in D}
        return _inst(f"One-way grid {s}×{s}", pos, [(u, v, w, True) for u, v, w in D.edges(data="weight")],
                     units="m", note="Alternating one-way streets, two-way outer ring.")
    if name == "mixed-town":
        s = max(3, min(size, 40))
        M = city_grid(s, s, oneway_street_frac=oneway, seed=seed)
        pos = {v: ((v - 1) % s, (v - 1) // s) for v in M.nodes}
        return _inst(f"Mixed town {s}×{s}", pos, M.links, units="m",
                     note=f"Each whole street is one-way with probability {oneway:.0%}.")
    raise ValueError(f"Unknown example {name!r}")


def from_gra(text: str, name: str = "uploaded graph") -> dict:
    """The 1997 .GRA format: n, m, then one 'u v cost' line per street (all two-way)."""
    tok = text.split()
    n, m = int(tok[0]), int(tok[1])
    if n > MAX_NODES:
        raise ValueError(f"{n} vertices: the browser version accepts up to {MAX_NODES}")
    G = nx.MultiGraph()
    G.add_nodes_from(range(1, n + 1))
    for k in range(m):
        a, b, c = tok[2 + 3 * k: 5 + 3 * k]
        G.add_edge(int(a), int(b), weight=float(c))
    G.remove_nodes_from([v for v in list(G) if G.degree(v) == 0])
    pos = _layout(G)
    return _inst(name, {v: pos[v] for v in G}, [(u, v, w, False) for u, v, w in G.edges(data="weight")])


def from_carp_text(text: str, name: str) -> dict:
    """Classical CARP benchmark file (0-based vertices, cost and demand per edge)."""
    v = [int(x) for x in text.split()]
    n, m = v[0], v[1]
    G = nx.MultiGraph()
    for k in range(m):
        a, b, c, _ = v[2 + 4 * k: 6 + 4 * k]
        G.add_edge(a + 1, b + 1, weight=c)
    pos = _layout(G)
    return _inst(name, {x: pos[x] for x in G}, [(a, b, w, False) for a, b, w in G.edges(data="weight")])


# ------------------------------------------------------------------ OpenStreetMap
DRIVABLE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
            "living_street", "service", "motorway_link", "trunk_link", "primary_link",
            "secondary_link", "tertiary_link", "road"}


def overpass_query(south, west, north, east) -> str:
    hw = "|".join(sorted(DRIVABLE - {"service"}))
    return (f'[out:json][timeout:25];way["highway"~"^({hw})$"]["area"!="yes"]'
            f'({south},{west},{north},{east});(._;>;);out body;')


def from_osm(data, name: str = "OpenStreetMap area", max_nodes: int = 1500) -> dict:
    """Street network from an Overpass API JSON answer.

    Ways become links between junctions (OSM nodes shared by several ways, or way ends);
    intermediate points only add length. oneway=yes/1/-1 make one-way links. Only the largest
    strongly connected part is kept, so that a postman tour exists."""
    if isinstance(data, str):
        data = json.loads(data)
    nodes = {e["id"]: (e["lat"], e["lon"]) for e in data["elements"] if e["type"] == "node"}
    ways = [e for e in data["elements"] if e["type"] == "way" and len(e.get("nodes", [])) >= 2]
    if not ways:
        raise ValueError("No drivable streets in this area")
    lat0 = sum(p[0] for p in nodes.values()) / max(1, len(nodes))
    kx = 111320 * math.cos(math.radians(lat0))

    def xy(nid):
        la, lo = nodes[nid]
        return (lo * kx, la * 110540)

    use = {}
    for w in ways:
        for k, nid in enumerate(w["nodes"]):
            use[nid] = use.get(nid, 0) + (1 if 0 < k < len(w["nodes"]) - 1 else 2)
    junction = {nid for nid, c in use.items() if c >= 2}
    links = []
    for w in ways:
        tags = w.get("tags", {})
        ow = str(tags.get("oneway", "no")).lower()
        if tags.get("junction") == "roundabout" and ow == "no":
            ow = "yes"
        seq = [n for n in w["nodes"] if n in nodes]
        if ow == "-1":
            seq = seq[::-1]
        one = ow in ("yes", "1", "true", "-1")
        start, length = seq[0], 0.0
        for a, b in zip(seq, seq[1:]):
            length += math.dist(xy(a), xy(b))
            if b in junction or b == seq[-1]:
                if start != b and length > 0:
                    links.append((start, b, max(1, round(length)), one))
                start, length = b, 0.0
    D = nx.DiGraph()
    for u, v, w, one in links:
        D.add_edge(u, v)
        if not one:
            D.add_edge(v, u)
    comp = max(nx.strongly_connected_components(D), key=len)
    links = [l for l in links if l[0] in comp and l[1] in comp]
    if len(comp) > max_nodes:
        raise ValueError(f"{len(comp)} junctions: zoom in (the browser version accepts up to {max_nodes})")
    pts = {v: xy(v) for v in comp}
    x0 = min(p[0] for p in pts.values()); y0 = min(p[1] for p in pts.values())
    pos = {v: (p[0] - x0, p[1] - y0) for v, p in pts.items()}
    inst = _inst(name, pos, links, units="m",
                 note="Street data © OpenStreetMap contributors (ODbL).")
    ids = {v: i for i, v in enumerate(pos)}
    for v, nd in zip(pos, inst["nodes"]):
        nd["lat"], nd["lon"] = nodes[v]
    return inst


# ------------------------------------------------------------------ solving
def kind_of(inst) -> str:
    ow = [l["oneway"] for l in inst["links"]]
    return "directed" if all(ow) else "mixed" if any(ow) else "undirected"


def solve(inst, time_limit: float = 20.0, gap_tol: float = 0.0) -> dict:
    t0 = time.perf_counter()
    if len(inst["nodes"]) > MAX_NODES:
        raise ValueError(f"Too large for the browser version ({MAX_NODES} junctions at most)")
    kind = kind_of(inst)
    links = [(l["u"], l["v"], l["w"], l["oneway"]) for l in inst["links"]]
    out = {"kind": kind, "original": sum(w for _, _, w, _ in links)}
    if kind == "undirected":
        G = nx.MultiGraph()
        for u, v, w, _ in links:
            G.add_edge(u, v, weight=w)
        if not nx.is_connected(G):
            raise ValueError("The network is not connected: no single tour can cover it")
        s = solve_undirected(G)
        out.update(total=s.total_cost, circuit=s.circuit, optimal=True, gap_pct=0.0,
                   lower_bound=s.total_cost, method="Edmonds: shortest paths + blossom matching",
                   odd=s.odd_vertices)
    elif kind == "directed":
        G = nx.MultiDiGraph()
        for u, v, w, _ in links:
            G.add_edge(u, v, weight=w)
        if not nx.is_strongly_connected(G):
            raise ValueError("The network is not strongly connected: some street cannot be left")
        s = solve_directed(G)
        out.update(total=s.total_cost, circuit=s.circuit, optimal=True, gap_pct=0.0,
                   lower_bound=s.total_cost, method="Minimum-cost flow", odd=s.odd_vertices)
    else:
        M = MixedGraph(links)
        if not M.is_feasible():
            raise ValueError("The network is not strongly connected: some street cannot be left")
        s = solve_mixed(M, time_limit=time_limit, gap_tol=gap_tol)
        out.update(total=s.total_cost, circuit=s.circuit, optimal=bool(s.optimal),
                   gap_pct=s.info.get("gap_pct", 0.0), lower_bound=s.lower_bound,
                   method=s.method, heuristic=s.info.get("heuristic_cost"))
    c = out["circuit"]
    out["circuit"] = [int(v) for v in c]
    out["added"] = out["total"] - out["original"]
    out["added_pct"] = round(100 * out["added"] / out["original"], 2) if out["original"] else 0.0
    out["steps"] = len(c) - 1
    # how many times each link is driven, to colour the map
    count = {}
    for a, b in zip(c, c[1:]):
        key = (min(a, b), max(a, b))
        count[key] = count.get(key, 0) + 1
    out["repeated"] = [[int(a), int(b), n] for (a, b), n in count.items() if n > 1]
    out["seconds"] = round(time.perf_counter() - t0, 3)
    for k in ("total", "original", "added", "lower_bound"):
        out[k] = float(out[k]) if out[k] is not None else None
    return out


def solve_json(inst_json: str, time_limit: float = 20.0, gap_tol: float = 0.0) -> str:
    try:
        return json.dumps({"ok": True, **solve(json.loads(inst_json), time_limit, gap_tol)})
    except Exception as e:  # report to the page instead of failing silently
        return json.dumps({"ok": False, "error": str(e)})
