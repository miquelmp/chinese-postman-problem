/* Street networks for the website, in plain JavaScript (JavaScript twin of chinese_postman/web.py).
   Every builder returns {name, nodes:[{id,x,y,label}], links:[{u,v,w,oneway}], units, note}. */
(function (root) {
  "use strict";
  const CPP = root.CPP || (typeof require !== "undefined" ? require("./cpp.js") : null);
  const MAX_NODES = 2500;

  function rng(seed) {                       // mulberry32: small, fast, reproducible
    let a = (seed >>> 0) + 0x9e3779b9;
    return () => {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const randint = (r, a, b) => a + Math.floor(r() * (b - a + 1));

  function make(name, pos, links, extra) {
    const nodes = [...pos.keys()].map(id => ({ id, x: pos.get(id)[0], y: pos.get(id)[1], label: String(id) }));
    return Object.assign({ name, nodes, links: links.map(([u, v, w, o]) => ({ u, v, w: Math.round(w), oneway: !!o })),
                           units: "", note: "" }, extra || {});
  }

  function connected(n, edges) {             // edges: [a, b] over 0..n-1, ignores removed (null)
    const adj = Array.from({ length: n }, () => []);
    for (const e of edges) if (e) { adj[e[0]].push(e[1]); adj[e[1]].push(e[0]); }
    const seen = new Uint8Array(n), st = [0]; seen[0] = 1; let c = 1;
    while (st.length) for (const w of adj[st.pop()]) if (!seen[w]) { seen[w] = 1; c++; st.push(w); }
    return c === n;
  }

  function stronglyConnected(n, links) {
    const arcs = [];
    for (const l of links) { arcs.push([l.u, l.v, 1]); if (!l.oneway) arcs.push([l.v, l.u, 1]); }
    const adj = CPP.simpleAdjacency(n, arcs);
    return CPP.scc(adj);
  }

  // ---------------------------------------------------------------- examples
  const EXAMPLE_POS = { 1: [0.42, 0.95], 8: [0.08, 0.78], 4: [0.80, 0.86], 7: [0.36, 0.60],
                    5: [0.80, 0.48], 2: [1.00, 0.30], 6: [0.36, 0.24], 3: [0.68, 0.10] };
  const EXAMPLE_EDGES = [[1, 8, 2], [1, 7, 1], [8, 7, 5], [1, 4, 6], [7, 4, 4], [7, 6, 7],
                     [4, 5, 2], [6, 5, 1], [6, 3, 4], [3, 5, 7], [5, 2, 6], [3, 2, 9]];

  function example1997() {
    const pos = new Map(Object.entries(EXAMPLE_POS).map(([k, v]) => [+k, v]));
    return make("1997 worked example (park maintenance network)", pos, EXAMPLE_EDGES.map(([u, v, w]) => [u, v, w, false]),
                { note: "From chapter 3 of both reports; the optimum is 63 = 54 + 9." });
  }

  function konigsberg() {
    const pos = new Map([[0, [0.5, 0.5]], [1, [0.45, 0.95]], [2, [0.45, 0.05]], [3, [0.95, 0.5]]]);
    const inst = make("Seven bridges of Königsberg", pos,
      [[0, 1, 1], [0, 1, 1], [0, 2, 1], [0, 2, 1], [0, 3, 1], [1, 3, 1], [2, 3, 1]].map(e => [...e, false]),
      { note: "Cost = number of bridge crossings." });
    ["Kneiphof", "North bank", "South bank", "East"].forEach((t, i) => { inst.nodes[i].label = t; });
    return inst;
  }

  function petersen() {
    const pos = new Map(), links = [];
    for (let i = 0; i < 5; i++) {
      const a = Math.PI / 2 + i * 2 * Math.PI / 5;
      pos.set(i, [Math.cos(a), Math.sin(a)]); pos.set(i + 5, [0.5 * Math.cos(a), 0.5 * Math.sin(a)]);
      links.push([i, (i + 1) % 5, 1, false], [i, i + 5, 1, false], [i + 5, ((i + 2) % 5) + 5, 1, false]);
    }
    return make("Petersen graph", pos, links, { note: "Every vertex is odd; a perfect matching doubles 5 of the 15 edges." });
  }

  /** Grid town: short blocks along streets (80 m), long ones along avenues (270 m), 10% closed. */
  function grid(s, seed) {
    s = Math.max(2, Math.min(s, 40));
    const r = rng(seed * 7919 + s), id = (row, col) => row * s + col, edges = [], pos = new Map();
    for (let row = 0; row < s; row++) for (let col = 0; col < s; col++) {
      pos.set(id(row, col), [col, row]);
      if (col + 1 < s) edges.push([id(row, col), id(row, col + 1), 80]);
      if (row + 1 < s) edges.push([id(row, col), id(row + 1, col), 270]);
    }
    for (let k = 0; k < edges.length; k++) {
      if (r() < 0.1) { const e = edges[k]; edges[k] = null; if (!connected(s * s, edges)) edges[k] = e; }
    }
    return make(`Grid town ${s}×${s}`, pos, edges.filter(Boolean).map(([u, v, w]) => [u, v, w, false]),
                { units: "m", note: "Short blocks along streets, long ones along avenues; 10% closed." });
  }

  /** Delaunay triangulation (Bowyer–Watson). Returns unique edges [i, j]. */
  function delaunayEdges(pts) {
    const n = pts.length, big = 1e5;
    const P = pts.concat([[-big, -big], [big * 2, -big], [-big, big * 2]]);
    let tris = [[n, n + 1, n + 2]];
    const circ = t => {
      const [ax, ay] = P[t[0]], [bx, by] = P[t[1]], [cx, cy] = P[t[2]];
      const d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
      const ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d;
      const uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d;
      return [ux, uy, (ax - ux) ** 2 + (ay - uy) ** 2];
    };
    let circles = tris.map(circ);
    for (let i = 0; i < n; i++) {
      const [px, py] = P[i], bad = [], keep = [], keepC = [];
      tris.forEach((t, k) => {
        const [ux, uy, r2] = circles[k];
        ((px - ux) ** 2 + (py - uy) ** 2 < r2) ? bad.push(t) : (keep.push(t), keepC.push(circles[k]));
      });
      const count = new Map();
      for (const t of bad) for (const [a, b] of [[t[0], t[1]], [t[1], t[2]], [t[2], t[0]]]) {
        const k = a < b ? `${a},${b}` : `${b},${a}`; count.set(k, (count.get(k) || 0) + 1);
      }
      for (const [k, c] of count) if (c === 1) {
        const [a, b] = k.split(",").map(Number), t = [a, b, i];
        keep.push(t); keepC.push(circ(t));
      }
      tris = keep; circles = keepC;
    }
    const E = new Set();
    for (const t of tris) for (const [a, b] of [[t[0], t[1]], [t[1], t[2]], [t[2], t[0]]]) {
      if (a < n && b < n) E.add(a < b ? a * n + b : b * n + a);
    }
    return [...E].map(k => [Math.floor(k / n), k % n]);
  }

  /** Organic town: Delaunay triangulation of random junctions, thinned to 75% of its edges
      (spanning tree first, then shortest edges), lengths in metres. The square has a side of
      100 m × sqrt(n), so the density of junctions stays the same at any size. */
  function delaunay(n, seed) {
    n = Math.max(10, Math.min(n, MAX_NODES));
    const side = 100 * Math.sqrt(n);
    const r = rng(seed * 104729 + n), pts = Array.from({ length: n }, () => [r() * side, r() * side]);
    const E = delaunayEdges(pts).map(([a, b]) => [a, b, Math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1])]);
    E.sort((x, y) => x[2] - y[2]);
    const parent = Int32Array.from({ length: n }, (_, i) => i);
    const find = x => { while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; };
    const keep = new Set();
    E.forEach((e, k) => { const a = find(e[0]), b = find(e[1]); if (a !== b) { parent[a] = b; keep.add(k); } });
    for (let k = 0; k < E.length && keep.size < 0.75 * E.length; k++) keep.add(k);
    const pos = new Map(pts.map((p, i) => [i, p]));
    return make(`Organic town, ${n} junctions`, pos, [...keep].map(k => [E[k][0], E[k][1], Math.max(1, Math.round(E[k][2])), false]),
                { units: "m" });
  }

  /** One-way grid: alternating one-way streets and avenues, two-way outer ring and every fourth street. */
  function onewayGrid(s, seed) {
    s = Math.max(3, Math.min(s, 40));
    const r = rng(seed * 31 + s), id = (row, col) => row * s + col, links = [], pos = new Map();
    const add = (a, b, w, mode) => { if (mode >= 0) links.push([a, b, w, true]); if (mode <= 0) links.push([b, a, w, true]); };
    for (let row = 0; row < s; row++) for (let col = 0; col < s; col++) pos.set(id(row, col), [col, row]);
    for (let row = 0; row < s; row++) for (let col = 0; col + 1 < s; col++) {
      const two = row === 0 || row === s - 1 || row % 4 === 3;
      add(id(row, col), id(row, col + 1), 80 + randint(r, -10, 10), two ? 0 : row % 2 === 0 ? 1 : -1);
    }
    for (let col = 0; col < s; col++) for (let row = 0; row + 1 < s; row++) {
      const two = col === 0 || col === s - 1;
      add(id(row, col), id(row + 1, col), 240 + randint(r, -20, 20), two ? 0 : col % 2 === 0 ? 1 : -1);
    }
    return make(`One-way grid ${s}×${s}`, pos, links, { units: "m", note: "Alternating one-way streets, two-way outer ring." });
  }

  /** Town where each whole street is one-way with probability `share`, in a random direction;
      streets that break strong connectivity are turned back into two-way streets. */
  /** Hilly town: a grid town on a smooth surface. A street costs more uphill than downhill, in
      proportion to its slope, so each direction has its own cost (the windy postman). */
  function hillyTown(s, seed) {
    const G = grid(Math.max(3, s), seed), r = rng(seed * 257 + s);
    const p1 = r() * 6.28, p2 = r() * 6.28, height = (x, y) => 12 * Math.sin(x / 2.3 + p1) + 12 * Math.cos(y / 2.9 + p2);
    const at = new Map(G.nodes.map(nd => [nd.id, nd]));
    G.links.forEach(l => {
      const a = at.get(l.u), b = at.get(l.v), rise = height(b.x, b.y) - height(a.x, a.y);
      const base = l.w, extra = Math.max(-0.6 * base, Math.min(0.6 * base, 6 * rise));
      l.w = Math.max(1, Math.round(base + extra));
      l.w2 = Math.max(1, Math.round(base - extra));
    });
    G.name = `Hilly town ${Math.max(3, s)}×${Math.max(3, s)}`;
    G.note = "A street costs more uphill than downhill, so each direction has its own cost.";
    return G;
  }

  function mixedTown(s, share, seed) {
    s = Math.max(3, Math.min(s, 40));
    const r = rng(seed * 131 + s * 7 + Math.round(share * 100)), id = (row, col) => row * s + col;
    const links = [], pos = new Map();
    for (let row = 0; row < s; row++) for (let col = 0; col < s; col++) pos.set(id(row, col), [col, row]);
    for (let row = 0; row < s; row++) {
      const one = r() < share, d = r() < 0.5;
      for (let col = 0; col + 1 < s; col++) {
        const a = id(row, col), b = id(row, col + 1);
        links.push({ u: d ? b : a, v: d ? a : b, w: 80 + randint(r, -8, 8), oneway: one });
      }
    }
    for (let col = 0; col < s; col++) {
      const one = r() < share, d = r() < 0.5;
      for (let row = 0; row + 1 < s; row++) {
        const a = id(row, col), b = id(row + 1, col);
        links.push({ u: d ? b : a, v: d ? a : b, w: 270 + randint(r, -20, 20), oneway: one });
      }
    }
    for (;;) {
      const { comp, ncomp } = stronglyConnected(s * s, links);
      if (ncomp === 1) break;
      const k = links.findIndex(l => l.oneway && comp[l.u] !== comp[l.v]);
      links[k].oneway = false;
    }
    return make(`Mixed town ${s}×${s}`, pos, links.map(l => [l.u, l.v, l.w, l.oneway]),
                { units: "m", note: `Each whole street is one-way with probability ${Math.round(share * 100)}%.` });
  }

  // ---------------------------------------------------------------- files
  /** Force-directed layout (Fruchterman–Reingold) for networks without coordinates. */
  function layout(n, edges, seed) {
    const r = rng(seed || 1), x = Float64Array.from({ length: n }, () => r()), y = Float64Array.from({ length: n }, () => r());
    const k = Math.sqrt(1 / n), iters = n > 800 ? 60 : n > 300 ? 150 : 300;
    const dx = new Float64Array(n), dy = new Float64Array(n);
    let temp = 0.1;
    for (let it = 0; it < iters; it++) {
      dx.fill(0); dy.fill(0);
      for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
        let ex = x[i] - x[j], ey = y[i] - y[j], d2 = ex * ex + ey * ey || 1e-9;
        const f = k * k / d2; dx[i] += ex * f; dy[i] += ey * f; dx[j] -= ex * f; dy[j] -= ey * f;
      }
      for (const [a, b] of edges) {
        const ex = x[a] - x[b], ey = y[a] - y[b], d = Math.sqrt(ex * ex + ey * ey) || 1e-9, f = d / k;
        dx[a] -= ex * f; dy[a] -= ey * f; dx[b] += ex * f; dy[b] += ey * f;
      }
      for (let i = 0; i < n; i++) {
        const d = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]) || 1e-9, s = Math.min(d, temp) / d;
        x[i] += dx[i] * s; y[i] += dy[i] * s;
      }
      temp *= 1 - 1 / iters;
    }
    return { x, y };
  }

  function fromEdgeList(name, n, list, labelOf) {
    const used = new Set(); for (const [a, b] of list) { used.add(a); used.add(b); }
    const ids = [...used].sort((p, q) => p - q), map = new Map(ids.map((v, i) => [v, i]));
    const { x, y } = layout(ids.length, list.map(([a, b]) => [map.get(a), map.get(b)]));
    const pos = new Map(ids.map((v, i) => [v, [x[i], y[i]]]));
    const inst = make(name, pos, list.map(([a, b, w]) => [a, b, w, false]));
    if (labelOf) inst.nodes.forEach(nd => { nd.label = labelOf(nd.id); });
    return inst;
  }

  /** The 1997 .GRA format: junctions, streets, then one 'from to cost' line per street. */
  function fromGra(text, name) {
    const tok = text.trim().split(/\s+/).map(Number);
    const n = tok[0], m = tok[1];
    if (!(n > 0) || !(m > 0) || tok.length < 2 + 3 * m) throw new Error("This is not a valid .GRA file: expected junctions, streets, then 'from to cost' lines");
    if (n > MAX_NODES) throw new Error(`${n} junctions: the browser version accepts up to ${MAX_NODES}`);
    const list = [];
    for (let k = 0; k < m; k++) {
      const a = tok[2 + 3 * k], b = tok[3 + 3 * k], c = tok[4 + 3 * k];
      if (!Number.isInteger(a) || !Number.isInteger(b) || !(c >= 0)) throw new Error(`Line ${k + 3} is not 'from to cost'`);
      list.push([a, b, Math.round(c)]);
    }
    return fromEdgeList(name, n, list);
  }

  /** Classical CARP benchmark file: 0-based vertices, 'from to cost demand' per edge. */
  function fromCarp(text, name) {
    const v = text.trim().split(/\s+/).map(Number), m = v[1], list = [], req = [];
    for (let k = 0; k < m; k++) { list.push([v[2 + 4 * k] + 1, v[3 + 4 * k] + 1, v[4 + 4 * k]]); req.push(v[5 + 4 * k] > 0); }
    const inst = fromEdgeList(name, v[0], list);
    if (req.some(r => !r)) {                  // the file marks which streets need service
      inst.links.forEach((l, k) => { l.marked = req[k]; });
      inst.marked = req.filter(Boolean).length;
    }
    return inst;
  }

  // ---------------------------------------------------------------- OpenStreetMap
  const DRIVABLE = ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
                    "living_street", "motorway_link", "trunk_link", "primary_link", "secondary_link",
                    "tertiary_link", "road"];

  function overpassQuery(s, w, n, e) {
    return `[out:json][timeout:25];way["highway"~"^(${DRIVABLE.slice().sort().join("|")})$"]["area"!="yes"]` +
           `(${s},${w},${n},${e});(._;>;);out body;`;
  }

  const MAIN = new Set(["motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link",
                        "primary_link", "secondary_link", "tertiary_link"]);

  /** Street network from an Overpass answer: junctions are shared OSM nodes or way ends,
      shape points only add length; oneway=yes/1/-1 and roundabouts make one-way links.
      Only the largest strongly connected part is kept, so that a tour exists. */
  function fromOsm(data, name, maxNodes) {
    if (typeof data === "string") data = JSON.parse(data);
    maxNodes = maxNodes || 1500;
    const nodes = new Map(), ways = [];
    for (const e of data.elements || []) {
      if (e.type === "node") nodes.set(e.id, [e.lat, e.lon]);
      else if (e.type === "way" && (e.nodes || []).length >= 2) ways.push(e);
    }
    if (!ways.length) throw new Error("No drivable streets in this area");
    let lat0 = 0; for (const p of nodes.values()) lat0 += p[0]; lat0 /= nodes.size;
    const kx = 111320 * Math.cos(lat0 * Math.PI / 180);
    const xy = id => { const [la, lo] = nodes.get(id); return [lo * kx, la * 110540]; };
    const use = new Map();
    for (const w of ways) w.nodes.forEach((id, k) => use.set(id, (use.get(id) || 0) + (k > 0 && k < w.nodes.length - 1 ? 1 : 2)));
    const junction = new Set([...use].filter(([, c]) => c >= 2).map(([id]) => id));
    const raw = [];
    for (const w of ways) {
      const tags = w.tags || {};
      let ow = String(tags.oneway || "no").toLowerCase();
      if (tags.junction === "roundabout" && ow === "no") ow = "yes";
      let seq = w.nodes.filter(id => nodes.has(id));
      if (seq.length < 2) continue;
      if (ow === "-1") seq = seq.reverse();
      const one = ["yes", "1", "true", "-1"].includes(ow);
      let start = seq[0], len = 0;
      for (let i = 1; i < seq.length; i++) {
        const [ax, ay] = xy(seq[i - 1]), [bx, by] = xy(seq[i]);
        len += Math.hypot(bx - ax, by - ay);
        if (junction.has(seq[i]) || i === seq.length - 1) {
          if (start !== seq[i] && len > 0) raw.push([start, seq[i], Math.max(1, Math.round(len)), one, MAIN.has(tags.highway)]);
          start = seq[i]; len = 0;
        }
      }
    }
    const ids = [...new Set(raw.flatMap(l => [l[0], l[1]]))], map = new Map(ids.map((v, i) => [v, i]));
    const { comp } = stronglyConnected(ids.length, raw.map(([a, b, w, o]) => ({ u: map.get(a), v: map.get(b), oneway: o })));
    const size = new Map(); for (const c of comp) size.set(c, (size.get(c) || 0) + 1);
    const big = [...size].sort((p, q) => q[1] - p[1])[0][0];
    const keepIds = ids.filter((v, i) => comp[i] === big);
    if (keepIds.length > maxNodes) throw new Error(`${keepIds.length} junctions: zoom in (the browser version accepts up to ${maxNodes})`);
    const keep = new Set(keepIds), local = new Map(keepIds.map((v, i) => [v, i]));
    const pts = keepIds.map(xy), x0 = Math.min(...pts.map(p => p[0])), y0 = Math.min(...pts.map(p => p[1]));
    const pos = new Map(keepIds.map((v, i) => [i, [pts[i][0] - x0, pts[i][1] - y0]]));
    const kept = raw.filter(l => keep.has(l[0]) && keep.has(l[1]));
    const links = kept.map(([a, b, w, o]) => [local.get(a), local.get(b), w, o]);
    const inst = make(name, pos, links, { units: "m", note: "Street data © OpenStreetMap contributors (ODbL)." });
    inst.links.forEach((l, k) => { l.main = kept[k][4]; });
    inst.nodes.forEach((nd, i) => { [nd.lat, nd.lon] = nodes.get(keepIds[i]); });
    return inst;
  }

  // ---------------------------------------------------------------- entry
  function example(name, size, share, seed) {
    seed = seed || 0;
    switch (name) {
      case "example1997": return example1997();
      case "konigsberg": return konigsberg();
      case "petersen": return petersen();
      case "grid": return grid(size || 10, seed);
      case "delaunay": return delaunay(size || 150, seed);
      case "oneway-grid": return onewayGrid(size || 10, seed);
      case "mixed-town": return mixedTown(size || 10, share === undefined ? 0.6 : share, seed);
      case "hilly-town": return hillyTown(size || 10, seed);
      default: throw new Error(`Unknown example ${name}`);
    }
  }

  const API = { example, fromGra, fromCarp, fromOsm, overpassQuery, delaunayEdges, layout, rng, MAX_NODES };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.Networks = API;
})(typeof self !== "undefined" ? self : this);
