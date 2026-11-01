import json

import pytest

from chinese_postman import web


def walk_ok(inst, res):
    """The tour is closed, uses only allowed moves and covers every link."""
    c = res["circuit"]
    assert c[0] == c[-1]
    allowed = set()
    for l in inst["links"]:
        allowed.add((l["u"], l["v"]))
        if not l["oneway"]:
            allowed.add((l["v"], l["u"]))
    assert all((a, b) in allowed for a, b in zip(c, c[1:]))
    covered = {frozenset((a, b)) for a, b in zip(c, c[1:])}
    assert all(frozenset((l["u"], l["v"])) in covered for l in inst["links"])


@pytest.mark.parametrize("name,kw,kind", [
    ("example1997", {}, "undirected"),
    ("konigsberg", {}, "undirected"),
    ("petersen", {}, "undirected"),
    ("grid", {"size": 8}, "undirected"),
    ("delaunay", {"size": 120}, "undirected"),
    ("oneway-grid", {"size": 6}, "directed"),
    ("mixed-town", {"size": 8}, "mixed"),
])
def test_examples_solve(name, kw, kind):
    inst = web.example(name, **kw)
    res = json.loads(web.solve_json(json.dumps(inst)))
    assert res["ok"], res
    assert res["kind"] == kind
    assert res["total"] >= res["original"]
    walk_ok(inst, res)


def test_known_values():
    assert web.solve(web.example("example1997"))["total"] == 63
    assert web.solve(web.example("konigsberg"))["total"] == 9


def test_gra_roundtrip():
    text = open("examples/example_1997.gra").read()
    res = web.solve(web.from_gra(text))
    assert res["total"] == 63


def test_carp_text():
    inst = web.from_carp_text(open("data/carp/gdb1.dat").read(), "gdb1")
    assert web.solve(inst)["optimal"]


def test_errors_are_reported():
    inst = web.example("example1997")
    inst["links"] = inst["links"][:2]            # disconnected
    inst["links"].append({"u": 6, "v": 7, "w": 1, "oneway": False})
    res = json.loads(web.solve_json(json.dumps(inst)))
    assert not res["ok"] and "connected" in res["error"]


def overpass_sample():
    """A 3×3 block of streets with one one-way street and one roundabout-free loop."""
    nodes, ways, nid = [], [], 1
    grid = {}
    for r in range(3):
        for c in range(3):
            grid[r, c] = nid
            nodes.append({"type": "node", "id": nid, "lat": 41.22 + r * 0.001, "lon": 1.72 + c * 0.0013})
            nid += 1
    # an intermediate shape point on one street
    nodes.append({"type": "node", "id": 99, "lat": 41.2205, "lon": 1.72065})
    wid = 1000
    for r in range(3):
        seq = [grid[r, 0], grid[r, 1], grid[r, 2]]
        if r == 0:
            seq = [grid[0, 0], 99, grid[0, 1], grid[0, 2]]
        tags = {"highway": "residential", "oneway": "yes"} if r == 1 else {"highway": "residential"}
        ways.append({"type": "way", "id": wid, "nodes": seq, "tags": tags}); wid += 1
    for c in range(3):
        ways.append({"type": "way", "id": wid, "nodes": [grid[0, c], grid[1, c], grid[2, c]],
                     "tags": {"highway": "residential"}}); wid += 1
    return {"elements": nodes + ways}


def test_from_osm():
    inst = web.from_osm(overpass_sample(), "sample")
    assert len(inst["nodes"]) == 9                   # shape point 99 is not a junction
    assert len(inst["links"]) == 12
    assert sum(l["oneway"] for l in inst["links"]) == 2
    res = web.solve(inst)
    assert res["kind"] == "mixed" and res["optimal"]
    walk_ok(inst, res)


def test_overpass_query_is_bbox():
    q = web.overpass_query(41.2, 1.7, 41.21, 1.71)
    assert "(41.2,1.7,41.21,1.71)" in q and q.startswith("[out:json]")
