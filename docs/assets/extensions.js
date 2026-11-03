/* Extensions proposed in 1997, in plain JavaScript (twin of chinese_postman/rural.py, fleet.py and
   sequence.py; tests/js/test_extensions.mjs checks them against the Python results).

   Instance: {nodes, links:[{u, v, w, req}]}, two-way streets only; req === false marks a street
   that may be used but need not be served.

   rural(inst, opts)      -> one postman serving the required streets (rural postman problem).
                             Exact when the required streets form one piece (matching);
                             otherwise Frederickson's heuristic + local search, with a lower bound.
   postmen(inst, k, opts) -> k postmen from one depot, longest route as short as possible:
                             optimal split of one tour into k routes + local search, with a bound.
*/
(function (root) {
  "use strict";
  const CPP = root.CPP || (typeof require !== "undefined" ? require("./cpp.js") : null);
  function rng(seed) {                     // mulberry32, as in networks.js
    let a = (seed >>> 0) + 0x9e3779b9;
    return () => {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // ------------------------------------------------------------------ problem
  function problem(inst, depotId) {
    if (inst.links.some(l => l.oneway || (l.w2 !== undefined && l.w2 !== l.w))) throw new Error("This method works on two-way networks with one cost per street");
    const ids = [], idx = new Map();
    for (const nd of inst.nodes) { idx.set(nd.id, ids.length); ids.push(nd.id); }
    const n = ids.length;
    const arcs = [], R = [];
    inst.links.forEach((l, li) => {
      const a = idx.get(l.u), b = idx.get(l.v);
      arcs.push([a, b, l.w], [b, a, l.w]);
      if (l.req !== false) R.push([a, b, l.w, li]);
    });
    if (!R.length) throw new Error("No street needs service");
    const adj = CPP.simpleAdjacency(n, arcs);
    const depot = depotId !== undefined && idx.has(depotId) ? idx.get(depotId) : R[0][0];
    const set = new Set([depot]);
    for (const [a, b] of R) { set.add(a); set.add(b); }
    const V = [...set].sort((p, q) => p - q), vi = new Map(V.map((v, i) => [v, i]));
    const m = V.length, D = new Float64Array(m * m), pred = [];
    for (let i = 0; i < m; i++) {
      const r = CPP.dijkstra(adj, V[i]);
      pred.push(r.pred);
      for (let j = 0; j < m; j++) {
        const d = r.dist[V[j]];
        if (d === Infinity) throw new Error("Some streets to serve cannot be reached from the others");
        D[i * m + j] = d;
      }
    }
    const req = R.map(([a, b, s, li]) => [vi.get(a), vi.get(b), s, li]);   // li: index in inst.links
    const service = req.reduce((t, e) => t + e[2], 0);
    const uf = Array.from({ length: m }, (_, i) => i);
    const find = x => { while (uf[x] !== x) { uf[x] = uf[uf[x]]; x = uf[x]; } return x; };
    for (const [a, b] of req) uf[find(a)] = find(b);
    const groups = new Map();
    for (let i = 0; i < m; i++) { const r = find(i); if (!groups.has(r)) groups.set(r, []); groups.get(r).push(i); }
    const pieces = [...groups.values()], pieceOf = new Int32Array(m);
    pieces.forEach((p, k) => p.forEach(v => { pieceOf[v] = k; }));
    const deg = new Int32Array(m);
    for (const [a, b] of req) { deg[a]++; deg[b]++; }
    return { ids, n, V, vi, m, D, pred, req, service, pieces, pieceOf, deg, dep: vi.get(depot) };
  }

  const dist = (P, i, j) => P.D[i * P.m + j];

  function path(P, i, j) {                 // node ids from V[i] to V[j]
    const out = [P.V[j]], s = P.V[i], pr = P.pred[i];
    while (out[out.length - 1] !== s) out.push(pr[out[out.length - 1]]);
    return out.reverse().map(v => P.ids[v]);
  }

  function pairing(P, extra) {             // odd vertices of required streets + extra links, matched
    const deg = P.deg.slice();
    for (const [i, j] of extra) { deg[i]++; deg[j]++; }
    const odd = []; for (let i = 0; i < P.m; i++) if (deg[i] % 2) odd.push(i);
    const t = odd.length;
    if (!t) return { pairs: [], cost: 0 };
    const Dt = new Float64Array(t * t);
    for (let a = 0; a < t; a++) for (let b = 0; b < t; b++) Dt[a * t + b] = dist(P, odd[a], odd[b]);
    const mate = CPP.minWeightPerfectMatching(Dt, t), pairs = [];
    let cost = 0;
    for (let a = 0; a < t; a++) if (mate[a] > a) { pairs.push([odd[a], odd[mate[a]]]); cost += Dt[a * t + mate[a]]; }
    return { pairs, cost };
  }

  // ------------------------------------------------------------------ sequences
  // a route = array of [i, j, s]: served streets in order and direction (indices into V)
  function routeCost(P, seq) {
    if (!seq.length) return 0;
    let c = dist(P, P.dep, seq[0][0]) + dist(P, seq[seq.length - 1][1], P.dep);
    for (let t = 0; t < seq.length; t++) {
      c += seq[t][2];
      if (t + 1 < seq.length) c += dist(P, seq[t][1], seq[t + 1][0]);
    }
    return c;
  }

  function orient(P, seq) {                // best direction of every street, order kept
    const n = seq.length;
    if (!n) return seq;
    const st = (t, o) => (o ? seq[t][1] : seq[t][0]), en = (t, o) => (o ? seq[t][0] : seq[t][1]);
    let c0 = dist(P, P.dep, st(0, 0)), c1 = dist(P, P.dep, st(0, 1));
    const back = new Uint8Array(2 * n);
    for (let t = 1; t < n; t++) {
      const a0 = c0 + dist(P, en(t - 1, 0), st(t, 0)), b0 = c1 + dist(P, en(t - 1, 1), st(t, 0));
      const a1 = c0 + dist(P, en(t - 1, 0), st(t, 1)), b1 = c1 + dist(P, en(t - 1, 1), st(t, 1));
      back[2 * t] = a0 <= b0 ? 0 : 1; back[2 * t + 1] = a1 <= b1 ? 0 : 1;
      c0 = Math.min(a0, b0); c1 = Math.min(a1, b1);
    }
    c0 += dist(P, en(n - 1, 0), P.dep); c1 += dist(P, en(n - 1, 1), P.dep);
    let o = c0 <= c1 ? 0 : 1;
    const out = new Array(n);
    for (let t = n - 1; t >= 0; t--) { out[t] = [st(t, o), en(t, o), seq[t][2], seq[t][3]]; o = back[2 * t + o]; }
    return out;
  }

  function insertion(P, seq, e) {          // cheapest place and direction for street e
    let best = Infinity, at = 0, flip = false;
    for (let t = 0; t <= seq.length; t++) {
      const p = t === 0 ? P.dep : seq[t - 1][1], q = t === seq.length ? P.dep : seq[t][0];
      const base = dist(P, p, q);
      const f = dist(P, p, e[0]) + e[2] + dist(P, e[1], q) - base;
      const r = dist(P, p, e[1]) + e[2] + dist(P, e[0], q) - base;
      if (f < best) { best = f; at = t; flip = false; }
      if (r < best) { best = r; at = t; flip = true; }
    }
    const ne = flip ? [e[1], e[0], e[2], e[3]] : [e[0], e[1], e[2], e[3]];
    return { extra: best, seq: seq.slice(0, at).concat([ne], seq.slice(at)) };
  }

  function improve(P, seq, deadline) {     // 2-opt and drop/re-add on one route
    seq = orient(P, seq);
    let improved = true;
    while (improved && Date.now() < deadline) {
      improved = false;
      const n = seq.length;
      for (let i = 0; i < n - 1 && !improved; i++) {
        const p = i === 0 ? P.dep : seq[i - 1][1];
        for (let j = i + 1; j < n; j++) {
          const q = j === n - 1 ? P.dep : seq[j + 1][0];
          const delta = dist(P, p, seq[j][1]) + dist(P, seq[i][0], q) - dist(P, p, seq[i][0]) - dist(P, seq[j][1], q);
          if (delta < -1e-9) {
            const mid = seq.slice(i, j + 1).reverse().map(e => [e[1], e[0], e[2], e[3]]);
            seq = seq.slice(0, i).concat(mid, seq.slice(j + 1));
            improved = true; break;
          }
        }
        if (Date.now() > deadline) break;
      }
      if (improved) continue;
      for (let t = 0; t < seq.length && Date.now() < deadline; t++) {
        const e = seq[t], p = t === 0 ? P.dep : seq[t - 1][1], q = t === seq.length - 1 ? P.dep : seq[t + 1][0];
        const gain = dist(P, p, e[0]) + e[2] + dist(P, e[1], q) - dist(P, p, q);
        const rest = seq.slice(0, t).concat(seq.slice(t + 1));
        const ins = insertion(P, rest, e);
        if (ins.extra < gain - 1e-9) { seq = ins.seq; improved = true; }
      }
      seq = orient(P, seq);
    }
    return seq;
  }

  function fromCircuit(P, circ) {          // order in which a walk (over V indices) serves the streets
    const left = new Map();
    for (const e of P.req) {
      const key = Math.min(e[0], e[1]) * P.m + Math.max(e[0], e[1]);
      if (!left.has(key)) left.set(key, []);
      left.get(key).push(e);
    }
    const seq = [];
    for (let t = 0; t + 1 < circ.length; t++) {
      const a = circ[t], b = circ[t + 1], key = Math.min(a, b) * P.m + Math.max(a, b), q = left.get(key);
      if (q && q.length) { const e = q.pop(); seq.push([a, b, e[2], e[3]]); }
    }
    for (const q of left.values()) for (const e of q) seq.push(e.slice());
    return seq;
  }

  function expand(P, seq) {                // node ids of a route through the network
    let cur = P.dep;
    const out = [P.ids[P.V[P.dep]]];
    for (const [a, b] of seq) {
      if (cur !== a) out.push(...path(P, cur, a).slice(1));
      out.push(P.ids[P.V[b]]); cur = b;
    }
    if (cur !== P.dep) out.push(...path(P, cur, P.dep).slice(1));
    return out;
  }

  function abstractEdges(P, links) {
    return P.req.map(([a, b]) => [a, b]).concat(links.map(([i, j]) => [i, j]));
  }

  // ------------------------------------------------------------------ one postman
  function frederickson(P) {
    const k = P.pieces.length;
    if (k === 1) return pairing(P, []).pairs;
    const W = new Float64Array(k * k).fill(Infinity), arg = new Array(k * k);
    for (let a = 0; a < k; a++) for (let b = a + 1; b < k; b++) {
      let best = Infinity, pr = null;
      for (const i of P.pieces[a]) for (const j of P.pieces[b]) { const d = dist(P, i, j); if (d < best) { best = d; pr = [i, j]; } }
      W[a * k + b] = W[b * k + a] = best; arg[a * k + b] = arg[b * k + a] = pr;
    }
    const inTree = new Uint8Array(k), key = new Float64Array(k).fill(Infinity), par = new Int32Array(k).fill(-1);
    key[0] = 0; const links = [];
    for (let it = 0; it < k; it++) {            // Prim
      let u = -1;
      for (let v = 0; v < k; v++) if (!inTree[v] && (u < 0 || key[v] < key[u])) u = v;
      inTree[u] = 1;
      if (par[u] >= 0) links.push(arg[par[u] * k + u]);
      for (let v = 0; v < k; v++) if (!inTree[v] && W[u * k + v] < key[v]) { key[v] = W[u * k + v]; par[v] = u; }
    }
    return links.concat(pairing(P, links).pairs);
  }

  function treeBound(P) {                 // the pieces must be joined: at least a spanning tree of their distances
    const k = P.pieces.length;
    if (k === 1) return 0;
    const key = new Float64Array(k).fill(Infinity), inTree = new Uint8Array(k);
    const near = (a, b) => { let best = Infinity; for (const i of P.pieces[a]) for (const j of P.pieces[b]) best = Math.min(best, dist(P, i, j)); return best; };
    const W = new Float64Array(k * k);
    for (let a = 0; a < k; a++) for (let b = a + 1; b < k; b++) W[a * k + b] = W[b * k + a] = near(a, b);
    key[0] = 0; let total = 0;
    for (let it = 0; it < k; it++) {
      let u = -1;
      for (let v = 0; v < k; v++) if (!inTree[v] && (u < 0 || key[v] < key[u])) u = v;
      inTree[u] = 1; total += key[u];
      for (let v = 0; v < k; v++) if (!inTree[v] && W[u * k + v] < key[v]) key[v] = W[u * k + v];
    }
    return total;
  }

  function lowerBound(P) {
    const parity = P.service + Math.max(pairing(P, []).cost, treeBound(P));
    let far = 0;
    for (const [a, b, s] of P.req) far = Math.max(far, dist(P, P.dep, a) + s + dist(P, b, P.dep));
    return { parity, far };
  }

  function singleTour(P, deadline) {
    const links = frederickson(P);
    const circ = CPP.eulerianCircuit(P.m, abstractEdges(P, links), false, P.dep);
    let seq = orient(P, fromCircuit(P, circ));
    const fred = routeCost(P, seq);
    if (P.pieces.length > 1) seq = improve(P, seq, deadline);
    return { seq, fred, links };
  }

  function rural(inst, opts) {
    opts = Object.assign({ maxSeconds: 4 }, opts || {});
    const t0 = Date.now();
    const P = problem(inst, opts.depot);
    const { seq, fred } = singleTour(P, t0 + opts.maxSeconds * 1000);
    const total = routeCost(P, seq);
    const lbParts = lowerBound(P);
    const exact = P.pieces.length === 1;
    let lb = exact ? total : Math.ceil(Math.max(lbParts.parity, lbParts.far) - 1e-9);
    const optimal = total <= lb + 1e-9;
    return {
      kind: "rural", total, served: P.service, deadhead: total - P.service, lower_bound: lb, optimal,
      gap_pct: Math.round(Math.max(0, (total - lb) / lb * 100) * 1000) / 1000, circuit: expand(P, seq),
      pieces: P.pieces.length, required: P.req.length, frederickson: fred,
      method: exact ? "Matching on the odd junctions (exact: the streets to serve form one piece)"
                    : "Frederickson's heuristic + local search; bound from pairing the odd junctions",
      seconds: (Date.now() - t0) / 1000,
    };
  }

  // ------------------------------------------------------------------ several postmen
  function splitMinMax(P, seq, k) {
    const n = seq.length;
    if (!n) return [];
    k = Math.min(k, n);
    const s = seq.map(e => e[2]), link = new Float64Array(n);
    for (let t = 0; t + 1 < n; t++) link[t] = dist(P, seq[t][1], seq[t + 1][0]);
    const pre = new Float64Array(n + 1);
    for (let t = 0; t < n; t++) pre[t + 1] = pre[t] + s[t] + link[t];
    const cost = (i, j) => dist(P, P.dep, seq[i][0]) + pre[j + 1] - pre[i] - link[j] + dist(P, seq[j][1], P.dep);
    let f = new Float64Array(n);
    for (let j = 0; j < n; j++) f[j] = cost(0, j);
    const starts = [];
    for (let r = 1; r < k; r++) {
      const g = f.slice(), st = new Int32Array(n).fill(-1);
      for (let j = 1; j < n; j++) {
        for (let i = 0; i < j; i++) {           // last route serves i+1..j
          const c = Math.max(f[i], cost(i + 1, j));
          if (c < g[j] - 1e-12) { g[j] = c; st[j] = i + 1; }
        }
      }
      f = g; starts.push(st);
    }
    const routes = [];
    let j = n - 1;
    for (let r = k - 1; r > 0; r--) {
      const s0 = starts[r - 1][j];
      if (s0 >= 0) { routes.push(seq.slice(s0, j + 1)); j = s0 - 1; }
    }
    routes.push(seq.slice(0, j + 1));
    return routes.reverse().filter(r => r.length);
  }

  const keyOf = costs => [Math.max(...costs), costs.reduce((a, b) => a + b, 0)];
  const better = (x, y) => x[0] < y[0] - 1e-9 || (Math.abs(x[0] - y[0]) <= 1e-9 && x[1] < y[1] - 1e-9);

  function descent(P, routes, deadline) {
    routes = routes.map(r => orient(P, r));
    let costs = routes.map(r => routeCost(P, r));
    const total = routes.reduce((a, r) => a + r.length, 0);
    while (Date.now() < deadline) {
      const L = costs.indexOf(Math.max(...costs));
      let best = null;
      const swaps = routes[L].length * total < 60000;
      for (let t = 0; t < routes[L].length && Date.now() < deadline; t++) {
        const e = routes[L][t];
        const rest = orient(P, routes[L].slice(0, t).concat(routes[L].slice(t + 1)));
        const cRest = routeCost(P, rest);
        for (let r = 0; r < routes.length; r++) {
          if (r === L) continue;
          const ins = insertion(P, routes[r], e);
          const trial = costs.slice(); trial[L] = cRest; trial[r] = costs[r] + ins.extra;
          const kt = keyOf(trial);
          if (better(kt, keyOf(costs)) && (!best || better(kt, best.key))) best = { key: kt, A: rest, B: ins.seq, a: L, b: r };
          if (!swaps) continue;
          for (let u = 0; u < routes[r].length; u++) {
            const f = routes[r][u];
            const i1 = insertion(P, rest, f);
            const other = routes[r].slice(0, u).concat(routes[r].slice(u + 1));
            const i2 = insertion(P, other, e);
            const tr = costs.slice(); tr[L] = cRest + i1.extra; tr[r] = routeCost(P, other) + i2.extra;
            const k2 = keyOf(tr);
            if (better(k2, keyOf(costs)) && (!best || better(k2, best.key))) best = { key: k2, A: i1.seq, B: i2.seq, a: L, b: r };
          }
        }
      }
      if (!best) {
        const re = routes.map(r => improve(P, r, deadline)), rc = re.map(r => routeCost(P, r));
        if (better(keyOf(rc), keyOf(costs))) { routes = re; costs = rc; continue; }
        break;
      }
      routes[best.a] = orient(P, best.A); routes[best.b] = orient(P, best.B);
      costs[best.a] = routeCost(P, routes[best.a]); costs[best.b] = routeCost(P, routes[best.b]);
    }
    return { routes, costs };
  }

  function improveMinMax(P, routes, deadline, seed) {
    const rnd = rng(seed || 1);
    let best = descent(P, routes, deadline), cur = best, stall = 0;
    while (Date.now() < deadline && stall < 300) {
      const trial = cur.routes.map(r => r.slice());
      const moves = 1 + Math.floor(rnd() * 3);
      for (let q = 0; q < moves; q++) {
        const ne = trial.map((r, i) => (r.length ? i : -1)).filter(i => i >= 0);
        const a = ne[Math.floor(rnd() * ne.length)];
        const e = trial[a].splice(Math.floor(rnd() * trial[a].length), 1)[0];
        const b = Math.floor(rnd() * trial.length);
        trial[b] = insertion(P, trial[b], e).seq;
      }
      const res = descent(P, trial, deadline);
      if (better(keyOf(res.costs), keyOf(cur.costs)) || rnd() < 0.05) cur = res;
      if (better(keyOf(res.costs), keyOf(best.costs))) { best = res; stall = 0; } else stall++;
    }
    return best;
  }

  function tourVariants(P, edges, count, seed) {
    const rnd = rng(seed || 7);
    const base = CPP.eulerianCircuit(P.m, edges, false, P.dep);
    const out = [base, base.slice().reverse()];
    for (let c = 2; c < count; c++) {
      const sh = edges.slice();
      for (let i = sh.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [sh[i], sh[j]] = [sh[j], sh[i]]; }
      out.push(CPP.eulerianCircuit(P.m, sh, false, P.dep));
    }
    return out;
  }

  function postmen(inst, k, opts) {
    opts = Object.assign({ maxSeconds: 4 }, opts || {});
    const t0 = Date.now(), deadline = t0 + opts.maxSeconds * 1000;
    const P = problem(inst, opts.depot);
    const single = singleTour(P, t0 + opts.maxSeconds * 300);
    const singleCost = routeCost(P, single.seq);
    // several written-out orders of the same walk, each split optimally into k routes
    const walk = [];
    const exp = [P.dep];
    for (const [a, b] of single.seq) {
      if (exp[exp.length - 1] !== a) walk.push([exp[exp.length - 1], a]);
      walk.push([a, b]); exp.push(b);
    }
    if (exp[exp.length - 1] !== P.dep) walk.push([exp[exp.length - 1], P.dep]);
    let start = null;
    for (const circ of tourVariants(P, walk, P.req.length <= 400 ? 8 : 2)) {
      const routes = splitMinMax(P, orient(P, fromCircuit(P, circ)), k);
      const mx = Math.max(...routes.map(r => routeCost(P, r)));
      if (!start || mx < start.mx) start = { mx, routes };
    }
    const res = improveMinMax(P, start.routes, deadline);
    const lbp = lowerBound(P);
    const singleLb = P.pieces.length === 1 ? singleCost : Math.max(lbp.parity, lbp.far);
    const lb = Math.ceil(Math.max(lbp.far, singleLb / k) - 1e-9);
    const longest = Math.max(...res.costs), total = res.costs.reduce((a, b) => a + b, 0);
    const order = res.costs.map((c, i) => i).sort((a, b) => res.costs[b] - res.costs[a]);
    return {
      kind: "postmen", k, longest, total, lower_bound: lb, optimal: longest <= lb + 1e-9,
      gap_pct: Math.round(Math.max(0, (longest - lb) / lb * 100) * 1000) / 1000,
      split_longest: start.mx, single: singleCost,
      routes: order.map(i => ({ circuit: expand(P, res.routes[i]), cost: res.costs[i],
                                served: res.routes[i].reduce((a, e) => a + e[2], 0), streets: res.routes[i].length,
                                links: res.routes[i].map(e => e[3]) })),
      method: "One tour split into routes at least cost, then streets moved between routes; bound from the farthest street and the single tour",
      seconds: (Date.now() - t0) / 1000,
    };
  }

  // ------------------------------------------------------------------ directed, mixed and windy networks
  /** Some streets, or several postmen, on any network (as chinese_postman.windyrural and kpostmen):
      orient the required links, rebalance by a min-cost flow, join the pieces by shortest paths at
      the cheapest rebalanced total, and for several postmen cut the route at least cost. */
  function general(inst, k, opts) {
    opts = Object.assign({ maxSeconds: 4 }, opts || {});
    const t0 = Date.now(), CP = CPP;
    const ids = inst.nodes.map(nd => nd.id), idx = new Map(ids.map((v, i) => [v, i])), n = ids.length;
    const L = inst.links.map((l, li) => ({ a: idx.get(l.u), b: idx.get(l.v), f: l.w,
      r: l.oneway ? null : (l.w2 === undefined ? l.w : l.w2), req: l.req !== false, li }));
    const allowed = [];
    for (const l of L) { allowed.push([l.a, l.b, l.f]); if (l.r !== null) allowed.push([l.b, l.a, l.r]); }
    const adj = CP.simpleAdjacency(n, allowed), deadhead = [];
    for (let v = 0; v < n; v++) for (let e = adj.start[v]; e < adj.start[v + 1]; e++) deadhead.push([v, adj.to[e], Infinity, adj.wt[e]]);
    const req = L.filter(l => l.req), service = req.reduce((s, l) => s + Math.min(l.f, l.r === null ? l.f : l.r), 0);
    const depot = inst.depot !== undefined && idx.has(inst.depot) ? idx.get(inst.depot) : req[0].a;
    const memo = new Map(), from = v => { if (!memo.has(v)) memo.set(v, CP.dijkstra(adj, v)); return memo.get(v); };
    const reach = from(depot).dist;
    for (const l of req) if (!isFinite(reach[l.a]) || !isFinite(reach[l.b]) || !isFinite(from(l.b).dist[depot]) || !isFinite(from(l.a).dist[depot]))
      throw new Error("Some street to serve cannot be reached from the depot and back");
    const arcCost = new Map(deadhead.map(([a, b, , w]) => [a * n + b, w]));
    const path = (a, b) => {
      const { pred } = from(a), out = [];
      for (let v = b; v !== a; v = pred[v]) out.push([pred[v], v, arcCost.get(pred[v] * n + v)]);
      return out.reverse();
    };
    const pieces = edges => {
      const up = new Int32Array(n).map((_, i) => i), find = x => { while (up[x] !== x) { up[x] = up[up[x]]; x = up[x]; } return x; };
      for (const [a, b] of edges) up[find(a)] = find(b);
      const groups = new Map();
      const note = v => { const r = find(v); if (!groups.has(r)) groups.set(r, new Set()); groups.get(r).add(v); };
      note(depot);
      for (const l of req) { note(l.a); note(l.b); }
      return [...groups.values()];
    };
    const balance = forced => {
      const sup = new Float64Array(n);
      for (const [a, b] of forced) { sup[a] -= 1; sup[b] += 1; }
      return CP.minCostFlow(n, deadhead, sup);
    };
    const complete = start => {
      let forced = start.slice();
      for (;;) {
        const f = balance(forced), edges = forced.map(e => [e[0], e[1]]);
        deadhead.forEach(([a, b], j) => { for (let r = 0; r < f.flow[j]; r++) edges.push([a, b]); });
        const groups = pieces(edges);
        if (groups.length === 1) return { total: forced.reduce((s, e) => s + e[2], 0) + f.cost, edges };
        const first = [...groups[0]], cand = [];
        for (const S of groups.slice(1)) {
          let best = null;
          for (const x of S) {
            const dx = from(x).dist;
            for (const y of first) {
              const fwd = from(y).dist[x], back = dx[y];
              if (!best || fwd < best[0]) best = [fwd, y, x];
              if (back < best[0]) best = [back, x, y];
            }
          }
          cand.push(best);
        }
        cand.sort((p, q) => p[0] - q[0]);
        let pick = null;
        for (const [, a, b] of cand.slice(0, 3)) {
          const trial = forced.concat(path(a, b)), f2 = balance(trial);
          const value = trial.reduce((s, e) => s + e[2], 0) + f2.cost;
          if (!pick || value < pick[0]) pick = [value, trial];
        }
        forced = pick[1];
      }
    };
    const cheaper = l => (l.r === null || l.f <= l.r ? [l.a, l.b, l.f] : [l.b, l.a, l.r]);
    let best = complete(req.map(cheaper));
    if (L.some(l => l.r !== null)) {          // start from the undirected route on summed costs
      const summed = Object.assign({}, inst, { links: inst.links.map(l => Object.assign({}, l, {
        w: l.oneway ? 2 * l.w : l.w + (l.w2 === undefined ? l.w : l.w2), oneway: false, w2: undefined })) });
      const seq = rural(summed, { maxSeconds: Math.min(1.5, opts.maxSeconds / 3), depot: inst.depot }).circuit.map(v => idx.get(v));
      const seen = new Map();
      for (let i = 0; i + 1 < seq.length; i++) { const key = seq[i] * n + seq[i + 1]; seen.set(key, (seen.get(key) || 0) + 1); }
      const forced = req.map(l => {
        if (l.r !== null && (seen.get(l.b * n + l.a) || 0) > 0 && !(seen.get(l.a * n + l.b) > 0)) return [l.b, l.a, l.r];
        return l.r === null || (seen.get(l.a * n + l.b) || 0) > 0 ? [l.a, l.b, l.f] : cheaper(l);
      });
      const other = complete(forced);
      if (other.total < best.total) best = other;
    }
    // lower bound: each required link driven the cheaper way or reversed, with free rebalancing
    const sup = new Float64Array(n), arcs = deadhead.slice();
    let base = 0;
    for (const l of req) {
      const [a, b, lo] = cheaper(l), hi = l.r === null ? null : Math.max(l.f, l.r);
      sup[a] -= 1; sup[b] += 1; base += lo;
      if (hi !== null) arcs.push([b, a, 2, (hi - lo) / 2]);
    }
    const lower = Math.ceil(base + CP.minCostFlow(n, arcs, sup).cost - 1e-9);
    const circuit = CP.eulerianCircuit(n, best.edges, true, depot);
    const onePiece = pieces(req.map(l => [l.a, l.b])).length;
    if (k <= 1) {
      const total = best.total, optimal = total <= lower + 1e-9;
      return { kind: "rural", total, served: service, deadhead: total - service, lower_bound: lower, optimal,
               gap_pct: Math.round(Math.max(0, (total - lower) / lower * 100) * 1000) / 1000,
               circuit: circuit.map(v => ids[v]), pieces: onePiece, required: req.length,
               method: "Orientation of the required streets, min-cost rebalance and shortest joins; bound from the same flow",
               seconds: (Date.now() - t0) / 1000 };
    }
    // several postmen: cut the served streets of the route at least cost
    const open = new Map();
    for (const l of req) for (const key of [l.a * n + l.b, l.b * n + l.a]) { if (!open.has(key)) open.set(key, []); open.get(key).push(l); }
    const used = new Set(), tasks = [];
    for (let i = 0; i + 1 < circuit.length; i++) {
      const a = circuit[i], b = circuit[i + 1], l = (open.get(a * n + b) || []).find(x => !used.has(x.li) &&
        (x.a === a ? true : x.r !== null));
      if (l) { used.add(l.li); tasks.push([a, b, l.a === a ? l.f : l.r, l.li]); }
    }
    const m = tasks.length, K = Math.min(k, m), d = (a, b) => from(a).dist[b];
    const hop = new Float64Array(m), pre = new Float64Array(m + 1);
    for (let t = 0; t + 1 < m; t++) hop[t] = d(tasks[t][1], tasks[t + 1][0]);
    for (let t = 0; t < m; t++) pre[t + 1] = pre[t] + tasks[t][2] + hop[t];
    const cost = (i, j) => d(depot, tasks[i][0]) + pre[j + 1] - pre[i] - hop[j] + d(tasks[j][1], depot);
    let f = Float64Array.from({ length: m }, (_, j) => cost(0, j));
    const cuts = [];
    for (let r = 1; r < K; r++) {
      const g = f.slice(), st = new Int32Array(m).fill(-1);
      for (let j = 1; j < m; j++) for (let i = 0; i < j; i++) {
        const c = Math.max(f[i], cost(i + 1, j));
        if (c < g[j] - 1e-12) { g[j] = c; st[j] = i + 1; }
      }
      f = g; cuts.push(st);
    }
    const spans = [];
    let j = m - 1;
    for (let r = K - 1; r > 0; r--) { const s0 = cuts[r - 1][j]; if (s0 >= 0) { spans.push([s0, j]); j = s0 - 1; } }
    spans.push([0, j]);
    const routes = spans.reverse().map(([s, e]) => {
      const seq = [depot];
      let at = depot;
      for (let t = s; t <= e; t++) {
        for (const [, y] of path(at, tasks[t][0])) seq.push(y);
        seq.push(tasks[t][1]); at = tasks[t][1];
      }
      for (const [, y] of path(at, depot)) seq.push(y);
      return { circuit: seq.map(v => ids[v]), cost: cost(s, e), served: tasks.slice(s, e + 1).reduce((a, x) => a + x[2], 0),
               streets: e - s + 1, links: tasks.slice(s, e + 1).map(x => x[3]) };
    }).sort((p, q) => q.cost - p.cost);
    const longest = routes[0].cost, total = routes.reduce((s, r) => s + r.cost, 0);
    let far = 0;
    for (const l of req) far = Math.max(far, Math.min(d(depot, l.a) + l.f + d(l.b, depot), l.r === null ? Infinity : d(depot, l.b) + l.r + d(l.a, depot)));
    const lb = Math.ceil(Math.max(far, lower / k) - 1e-9);
    return { kind: "postmen", k, longest, total, lower_bound: lb, optimal: longest <= lb + 1e-9,
             gap_pct: Math.round(Math.max(0, (longest - lb) / lb * 100) * 1000) / 1000,
             split_longest: longest, single: best.total, routes,
             method: "One route split into routes at least cost; bound from the farthest street and the share of one route",
             seconds: (Date.now() - t0) / 1000 };
  }

  const API = { problem, rural, postmen, general, splitMinMax, routeCost, orient, fromCircuit, lowerBound };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.Extensions = API;
})(typeof self !== "undefined" ? self : this);
