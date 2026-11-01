/* Chinese Postman Problem solvers in plain JavaScript (browser and Node).
   JavaScript port of the Python package `chinese_postman`; tests/js checks both give the same optimum.

   Instance: {nodes:[{id,...}], links:[{u, v, w, oneway}]}  (w = non-negative integer cost)
   solve(instance) -> {kind, total, original, added, lower_bound, optimal, gap_pct, circuit, ...}

   - Two-way streets only: Edmonds' method — Dijkstra from the odd junctions, minimum-weight
     perfect matching (Van Rantwijk's implementation of Edmonds' blossom algorithm, as in
     NetworkX), duplicate the paths, Hierholzer. Proven optimal.
   - One-way streets only: minimum-cost flow, Hierholzer. Proven optimal.
   - Both (NP-hard): heuristic with a certified lower bound (see solveMixed).
*/
(function (root) {
  "use strict";

  // ------------------------------------------------------------------ binary heap
  class Heap {
    constructor() { this.k = []; this.v = []; }
    get size() { return this.k.length; }
    push(key, val) {
      const k = this.k, v = this.v; let i = k.length; k.push(key); v.push(val);
      while (i > 0) { const p = (i - 1) >> 1; if (k[p] <= key) break; k[i] = k[p]; v[i] = v[p]; i = p; }
      k[i] = key; v[i] = val;
    }
    pop() {
      const k = this.k, v = this.v, topV = v[0], topK = k[0];
      const lastK = k.pop(), lastV = v.pop(), n = k.length;
      if (n) {
        let i = 0;
        for (;;) {
          let c = 2 * i + 1; if (c >= n) break;
          if (c + 1 < n && k[c + 1] < k[c]) c++;
          if (k[c] >= lastK) break;
          k[i] = k[c]; v[i] = v[c]; i = c;
        }
        k[i] = lastK; v[i] = lastV;
      }
      this.lastKey = topK;
      return topV;
    }
  }

  // ------------------------------------------------------------------ graph helpers
  function indexNodes(inst) {
    const ids = [], idx = new Map();
    for (const nd of inst.nodes) { idx.set(nd.id, ids.length); ids.push(nd.id); }
    for (const l of inst.links) for (const x of [l.u, l.v]) if (!idx.has(x)) { idx.set(x, ids.length); ids.push(x); }
    return { ids, idx, n: ids.length };
  }

  /** Simple adjacency (cheapest parallel link) in CSR form; directed or both ways. */
  function simpleAdjacency(n, arcs) {           // arcs: [a, b, w]
    const best = new Map();
    for (const [a, b, w] of arcs) {
      if (a === b) continue;
      const key = a * n + b, old = best.get(key);
      if (old === undefined || w < old) best.set(key, w);
    }
    const deg = new Int32Array(n + 1);
    for (const key of best.keys()) deg[Math.floor(key / n) + 1]++;
    for (let i = 0; i < n; i++) deg[i + 1] += deg[i];
    const to = new Int32Array(best.size), wt = new Float64Array(best.size), pos = deg.slice(0, n);
    for (const [key, w] of best) { const a = Math.floor(key / n); to[pos[a]] = key % n; wt[pos[a]++] = w; }
    return { start: deg, to, wt, n };
  }

  function dijkstra(adj, s) {
    const n = adj.n, dist = new Float64Array(n).fill(Infinity), pred = new Int32Array(n).fill(-1);
    const h = new Heap(); dist[s] = 0; h.push(0, s);
    while (h.size) {
      const v = h.pop(), d = h.lastKey;
      if (d > dist[v]) continue;
      for (let e = adj.start[v]; e < adj.start[v + 1]; e++) {
        const w = adj.to[e], nd = d + adj.wt[e];
        if (nd < dist[w]) { dist[w] = nd; pred[w] = v; h.push(nd, w); }
      }
    }
    return { dist, pred };
  }

  /** Strongly connected components (iterative Tarjan). Returns component id per vertex. */
  function scc(adj) {
    const n = adj.n, index = new Int32Array(n).fill(-1), low = new Int32Array(n), comp = new Int32Array(n).fill(-1);
    const onStack = new Uint8Array(n), stack = [], call = [];
    let counter = 0, ncomp = 0;
    for (let s = 0; s < n; s++) {
      if (index[s] >= 0) continue;
      call.push([s, adj.start[s]]); index[s] = low[s] = counter++; stack.push(s); onStack[s] = 1;
      while (call.length) {
        const top = call[call.length - 1], v = top[0];
        if (top[1] < adj.start[v + 1]) {
          const w = adj.to[top[1]++];
          if (index[w] < 0) { index[w] = low[w] = counter++; stack.push(w); onStack[w] = 1; call.push([w, adj.start[w]]); }
          else if (onStack[w]) low[v] = Math.min(low[v], index[w]);
        } else {
          call.pop();
          if (call.length) { const u = call[call.length - 1][0]; low[u] = Math.min(low[u], low[v]); }
          if (low[v] === index[v]) {
            let w; do { w = stack.pop(); onStack[w] = 0; comp[w] = ncomp; } while (w !== v);
            ncomp++;
          }
        }
      }
    }
    return { comp, ncomp };
  }

  // ------------------------------------------------------------------ Eulerian circuit
  /** Hierholzer on a multigraph given as edge list [[a,b],...]; directed or undirected. */
  function eulerianCircuit(n, edges, directed, start) {
    const m = edges.length;
    if (!m) return [start];
    const deg = new Int32Array(n + 1);
    for (const [a, b] of edges) { deg[a + 1]++; if (!directed) deg[b + 1]++; }
    for (let i = 0; i < n; i++) deg[i + 1] += deg[i];
    const adjTo = new Int32Array(deg[n]), adjE = new Int32Array(deg[n]), pos = deg.slice(0, n);
    edges.forEach(([a, b], e) => {
      adjTo[pos[a]] = b; adjE[pos[a]++] = e;
      if (!directed) { adjTo[pos[b]] = a; adjE[pos[b]++] = e; }
    });
    const used = new Uint8Array(m), ptr = deg.slice(0, n);
    if (start === undefined || deg[start + 1] === deg[start]) start = edges[0][0];
    const stack = [start], circuit = [];
    while (stack.length) {
      const v = stack[stack.length - 1];
      while (ptr[v] < deg[v + 1] && used[adjE[ptr[v]]]) ptr[v]++;
      if (ptr[v] === deg[v + 1]) circuit.push(stack.pop());
      else { const k = ptr[v]; used[adjE[k]] = 1; stack.push(adjTo[k]); }
    }
    if (circuit.length !== m + 1) throw new Error("The network is not connected: no single tour can cover it");
    return circuit.reverse();
  }

  // ------------------------------------------------------------------ weighted matching
  /** Maximum-weight matching in a general graph (Edmonds' blossom algorithm).
      Port of Joris van Rantwijk's mwmatching.py (the code inside NetworkX).
      edges: [[i, j, w], ...] with integer weights; returns mate[] (-1 = unmatched). */
  function maxWeightMatching(edges, maxcardinality) {
    const nedge = edges.length;
    let nvertex = 0, maxweight = 0;
    for (const [i, j, w] of edges) { nvertex = Math.max(nvertex, i + 1, j + 1); if (w > maxweight) maxweight = w; }
    const n = nvertex;
    const endpoint = new Int32Array(2 * nedge);
    for (let k = 0; k < nedge; k++) { endpoint[2 * k] = edges[k][0]; endpoint[2 * k + 1] = edges[k][1]; }
    const neighbend = Array.from({ length: n }, () => []);
    for (let k = 0; k < nedge; k++) { neighbend[edges[k][0]].push(2 * k + 1); neighbend[edges[k][1]].push(2 * k); }
    const W = new Float64Array(nedge); for (let k = 0; k < nedge; k++) W[k] = edges[k][2];

    const mate = new Int32Array(n).fill(-1);
    const label = new Int32Array(2 * n), labelend = new Int32Array(2 * n).fill(-1);
    const inblossom = new Int32Array(n); for (let i = 0; i < n; i++) inblossom[i] = i;
    const blossomparent = new Int32Array(2 * n).fill(-1);
    const blossomchilds = new Array(2 * n).fill(null), blossomendps = new Array(2 * n).fill(null);
    const blossombase = new Int32Array(2 * n).fill(-1); for (let i = 0; i < n; i++) blossombase[i] = i;
    const bestedge = new Int32Array(2 * n).fill(-1), blossombestedges = new Array(2 * n).fill(null);
    const unusedblossoms = []; for (let b = n; b < 2 * n; b++) unusedblossoms.push(b);
    const dualvar = new Float64Array(2 * n); for (let i = 0; i < n; i++) dualvar[i] = maxweight;
    const allowedge = new Uint8Array(nedge);
    let queue = [];

    const slack = k => dualvar[endpoint[2 * k]] + dualvar[endpoint[2 * k + 1]] - 2 * W[k];
    function leaves(b, out) {
      if (b < n) out.push(b); else for (const t of blossomchilds[b]) leaves(t, out);
      return out;
    }
    function assignLabel(w, t, p) {
      const b = inblossom[w];
      label[w] = label[b] = t; labelend[w] = labelend[b] = p; bestedge[w] = bestedge[b] = -1;
      if (t === 1) leaves(b, queue);
      else if (t === 2) { const base = blossombase[b]; assignLabel(endpoint[mate[base]], 1, mate[base] ^ 1); }
    }
    function scanBlossom(v, w) {
      const path = []; let base = -1;
      while (v !== -1 || w !== -1) {
        let b = inblossom[v];
        if (label[b] & 4) { base = blossombase[b]; break; }
        path.push(b); label[b] = 5;
        if (labelend[b] === -1) v = -1;
        else { v = endpoint[labelend[b]]; b = inblossom[v]; v = endpoint[labelend[b]]; }
        if (w !== -1) { const t = v; v = w; w = t; }
      }
      for (const b of path) label[b] = 1;
      return base;
    }
    function addBlossom(base, k) {
      let v = endpoint[2 * k], w = endpoint[2 * k + 1];
      const bb = inblossom[base]; let bv = inblossom[v], bw = inblossom[w];
      const b = unusedblossoms.pop();
      blossombase[b] = base; blossomparent[b] = -1; blossomparent[bb] = b;
      const path = [], endps = [];
      while (bv !== bb) {
        blossomparent[bv] = b; path.push(bv); endps.push(labelend[bv]);
        v = endpoint[labelend[bv]]; bv = inblossom[v];
      }
      path.push(bb); path.reverse(); endps.reverse(); endps.push(2 * k);
      while (bw !== bb) {
        blossomparent[bw] = b; path.push(bw); endps.push(labelend[bw] ^ 1);
        w = endpoint[labelend[bw]]; bw = inblossom[w];
      }
      blossomchilds[b] = path; blossomendps[b] = endps;
      label[b] = 1; labelend[b] = labelend[bb]; dualvar[b] = 0;
      for (const x of leaves(b, [])) { if (label[inblossom[x]] === 2) queue.push(x); inblossom[x] = b; }
      const bestedgeto = new Int32Array(2 * n).fill(-1);
      for (const c of path) {
        let nblists;
        if (blossombestedges[c] === null) nblists = leaves(c, []).map(x => neighbend[x].map(p => p >> 1));
        else nblists = [blossombestedges[c]];
        for (const nblist of nblists) for (const kk of nblist) {
          let i = endpoint[2 * kk], j = endpoint[2 * kk + 1];
          if (inblossom[j] === b) { const t = i; i = j; j = t; }
          const bj = inblossom[j];
          if (bj !== b && label[bj] === 1 && (bestedgeto[bj] === -1 || slack(kk) < slack(bestedgeto[bj]))) bestedgeto[bj] = kk;
        }
        blossombestedges[c] = null; bestedge[c] = -1;
      }
      const list = []; for (const kk of bestedgeto) if (kk !== -1) list.push(kk);
      blossombestedges[b] = list; bestedge[b] = -1;
      for (const kk of list) if (bestedge[b] === -1 || slack(kk) < slack(bestedge[b])) bestedge[b] = kk;
    }
    function expandBlossom(b, endstage) {
      for (const s of blossomchilds[b]) {
        blossomparent[s] = -1;
        if (s < n) inblossom[s] = s;
        else if (endstage && dualvar[s] === 0) expandBlossom(s, endstage);
        else for (const x of leaves(s, [])) inblossom[x] = s;
      }
      if (!endstage && label[b] === 2) {
        const childs = blossomchilds[b], endps = blossomendps[b];
        const entrychild = inblossom[endpoint[labelend[b] ^ 1]];
        let j = childs.indexOf(entrychild), jstep, endptrick;
        if (j & 1) { j -= childs.length; jstep = 1; endptrick = 0; } else { jstep = -1; endptrick = 1; }
        const at = i => (i < 0 ? i + childs.length : i);
        let p = labelend[b];
        while (j !== 0) {
          label[endpoint[p ^ 1]] = 0;
          label[endpoint[endps[at(j - endptrick)] ^ endptrick ^ 1]] = 0;
          assignLabel(endpoint[p ^ 1], 2, p);
          allowedge[endps[at(j - endptrick)] >> 1] = 1;
          j += jstep;
          p = endps[at(j - endptrick)] ^ endptrick;
          allowedge[p >> 1] = 1;
          j += jstep;
        }
        let bv = childs[at(j)];
        label[endpoint[p ^ 1]] = label[bv] = 2;
        labelend[endpoint[p ^ 1]] = labelend[bv] = p;
        bestedge[bv] = -1;
        j += jstep;
        while (childs[at(j)] !== entrychild) {
          bv = childs[at(j)];
          if (label[bv] === 1) { j += jstep; continue; }
          let v = -1;
          for (const x of leaves(bv, [])) { v = x; if (label[x] !== 0) break; }
          if (label[v] !== 0) {
            label[v] = 0;
            label[endpoint[mate[blossombase[bv]]]] = 0;
            assignLabel(v, 2, labelend[v]);
          }
          j += jstep;
        }
      }
      label[b] = -1; labelend[b] = -1;
      blossomchilds[b] = blossomendps[b] = null;
      blossombase[b] = -1; blossombestedges[b] = null; bestedge[b] = -1;
      unusedblossoms.push(b);
    }
    function augmentBlossom(b, v) {
      let t = v;
      while (blossomparent[t] !== b) t = blossomparent[t];
      if (t >= n) augmentBlossom(t, v);
      const childs = blossomchilds[b], endps = blossomendps[b];
      const at = i => (i < 0 ? i + childs.length : i);
      const i = childs.indexOf(t);
      let j = i, jstep, endptrick;
      if (i & 1) { j -= childs.length; jstep = 1; endptrick = 0; } else { jstep = -1; endptrick = 1; }
      while (j !== 0) {
        j += jstep; t = childs[at(j)];
        const p = endps[at(j - endptrick)] ^ endptrick;
        if (t >= n) augmentBlossom(t, endpoint[p]);
        j += jstep; t = childs[at(j)];
        if (t >= n) augmentBlossom(t, endpoint[p ^ 1]);
        mate[endpoint[p]] = p ^ 1;
        mate[endpoint[p ^ 1]] = p;
      }
      blossomchilds[b] = childs.slice(i).concat(childs.slice(0, i));
      blossomendps[b] = endps.slice(i).concat(endps.slice(0, i));
      blossombase[b] = blossombase[blossomchilds[b][0]];
    }
    function augmentMatching(k) {
      const v = endpoint[2 * k], w = endpoint[2 * k + 1];
      for (let [s, p] of [[v, 2 * k + 1], [w, 2 * k]]) {
        for (;;) {
          const bs = inblossom[s];
          if (bs >= n) augmentBlossom(bs, s);
          mate[s] = p;
          if (labelend[bs] === -1) break;
          const t = endpoint[labelend[bs]], bt = inblossom[t];
          s = endpoint[labelend[bt]];
          const j = endpoint[labelend[bt] ^ 1];
          if (bt >= n) augmentBlossom(bt, j);
          mate[j] = labelend[bt];
          p = labelend[bt] ^ 1;
        }
      }
    }

    for (let stage = 0; stage < n; stage++) {
      label.fill(0); bestedge.fill(-1);
      for (let b = n; b < 2 * n; b++) blossombestedges[b] = null;
      allowedge.fill(0); queue = [];
      for (let v = 0; v < n; v++) if (mate[v] === -1 && label[inblossom[v]] === 0) assignLabel(v, 1, -1);
      let augmented = false;
      for (;;) {
        while (queue.length && !augmented) {
          const v = queue.pop();
          for (const p of neighbend[v]) {
            const k = p >> 1, w = endpoint[p];
            if (inblossom[v] === inblossom[w]) continue;
            let kslack = 0;
            if (!allowedge[k]) { kslack = slack(k); if (kslack <= 0) allowedge[k] = 1; }
            if (allowedge[k]) {
              if (label[inblossom[w]] === 0) assignLabel(w, 2, p ^ 1);
              else if (label[inblossom[w]] === 1) {
                const base = scanBlossom(v, w);
                if (base >= 0) addBlossom(base, k);
                else { augmentMatching(k); augmented = true; break; }
              } else if (label[w] === 0) { label[w] = 2; labelend[w] = p ^ 1; }
            } else if (label[inblossom[w]] === 1) {
              const b = inblossom[v];
              if (bestedge[b] === -1 || kslack < slack(bestedge[b])) bestedge[b] = k;
            } else if (label[w] === 0) {
              if (bestedge[w] === -1 || kslack < slack(bestedge[w])) bestedge[w] = k;
            }
          }
        }
        if (augmented) break;
        let deltatype = -1, delta = 0, deltaedge = -1, deltablossom = -1;
        if (!maxcardinality) { deltatype = 1; delta = Infinity; for (let v = 0; v < n; v++) delta = Math.min(delta, dualvar[v]); }
        for (let v = 0; v < n; v++) {
          if (label[inblossom[v]] === 0 && bestedge[v] !== -1) {
            const d = slack(bestedge[v]);
            if (deltatype === -1 || d < delta) { delta = d; deltatype = 2; deltaedge = bestedge[v]; }
          }
        }
        for (let b = 0; b < 2 * n; b++) {
          if (blossomparent[b] === -1 && label[b] === 1 && bestedge[b] !== -1) {
            const d = slack(bestedge[b]) / 2;
            if (deltatype === -1 || d < delta) { delta = d; deltatype = 3; deltaedge = bestedge[b]; }
          }
        }
        for (let b = n; b < 2 * n; b++) {
          if (blossombase[b] >= 0 && blossomparent[b] === -1 && label[b] === 2 && (deltatype === -1 || dualvar[b] < delta)) {
            delta = dualvar[b]; deltatype = 4; deltablossom = b;
          }
        }
        if (deltatype === -1) {
          deltatype = 1; delta = Infinity;
          for (let v = 0; v < n; v++) delta = Math.min(delta, dualvar[v]);
          delta = Math.max(0, delta);
        }
        for (let v = 0; v < n; v++) {
          const l = label[inblossom[v]];
          if (l === 1) dualvar[v] -= delta; else if (l === 2) dualvar[v] += delta;
        }
        for (let b = n; b < 2 * n; b++) {
          if (blossombase[b] >= 0 && blossomparent[b] === -1) {
            if (label[b] === 1) dualvar[b] += delta; else if (label[b] === 2) dualvar[b] -= delta;
          }
        }
        if (deltatype === 1) break;
        else if (deltatype === 2) {
          allowedge[deltaedge] = 1;
          let i = endpoint[2 * deltaedge], j = endpoint[2 * deltaedge + 1];
          if (label[inblossom[i]] === 0) { const t = i; i = j; j = t; }
          queue.push(i);
        } else if (deltatype === 3) {
          allowedge[deltaedge] = 1;
          queue.push(endpoint[2 * deltaedge]);
        } else if (deltatype === 4) expandBlossom(deltablossom, false);
      }
      if (!augmented) break;
      for (let b = n; b < 2 * n; b++) {
        if (blossomparent[b] === -1 && blossombase[b] >= 0 && label[b] === 1 && dualvar[b] === 0) expandBlossom(b, true);
      }
    }
    const out = new Int32Array(n);
    for (let v = 0; v < n; v++) out[v] = mate[v] >= 0 ? endpoint[mate[v]] : -1;
    return out;
  }

  /** Minimum-weight perfect matching on the complete graph with integer costs D (t×t). */
  function minWeightPerfectMatching(D, t) {
    if (t === 0) return new Int32Array(0);
    let maxw = 0;
    for (let i = 0; i < t; i++) for (let j = i + 1; j < t; j++) if (D[i * t + j] > maxw) maxw = D[i * t + j];
    const edges = [];
    for (let i = 0; i < t; i++) for (let j = i + 1; j < t; j++) edges.push([i, j, maxw + 1 - D[i * t + j]]);
    return maxWeightMatching(edges, true);
  }

  // ------------------------------------------------------------------ min-cost flow
  /** Successive shortest paths with potentials. arcs: [a, b, cap, cost] (cap may be Infinity).
      supply[v] > 0 sends flow, < 0 receives. Returns {cost, flow[arc], pot[v]}. */
  function minCostFlow(n, arcs, supply) {
    const N = n + 2, S = n, T = n + 1;
    const head = new Int32Array(N).fill(-1), nxt = [], to = [], cap = [], cost = [];
    const add = (a, b, c, w) => {
      to.push(b); cap.push(c); cost.push(w); nxt.push(head[a]); head[a] = to.length - 1;
      to.push(a); cap.push(0); cost.push(-w); nxt.push(head[b]); head[b] = to.length - 1;
      return to.length - 2;
    };
    const ids = arcs.map(([a, b, c, w]) => add(a, b, c, w));
    let need = 0;
    for (let v = 0; v < n; v++) {
      if (supply[v] > 0) { add(S, v, supply[v], 0); need += supply[v]; }
      else if (supply[v] < 0) add(v, T, -supply[v], 0);
    }
    const pot = new Float64Array(N), dist = new Float64Array(N), prevE = new Int32Array(N);
    let total = 0, flowSent = 0;
    while (flowSent < need) {
      dist.fill(Infinity); prevE.fill(-1); dist[S] = 0;
      const h = new Heap(); h.push(0, S);
      while (h.size) {
        const v = h.pop(), d = h.lastKey;
        if (d > dist[v]) continue;
        for (let e = head[v]; e !== -1; e = nxt[e]) {
          if (cap[e] <= 0) continue;
          const w = to[e], nd = d + cost[e] + pot[v] - pot[w];
          if (nd < dist[w] - 1e-9) { dist[w] = nd; prevE[w] = e; h.push(nd, w); }
        }
      }
      if (dist[T] === Infinity) throw new Error("The network is not strongly connected: some street cannot be left");
      for (let v = 0; v < N; v++) if (dist[v] < Infinity) pot[v] += dist[v];
      let f = need - flowSent;
      for (let v = T; v !== S; v = to[prevE[v] ^ 1]) f = Math.min(f, cap[prevE[v]]);
      for (let v = T; v !== S; v = to[prevE[v] ^ 1]) { cap[prevE[v]] -= f; cap[prevE[v] ^ 1] += f; total += f * cost[prevE[v]]; }
      flowSent += f;
    }
    const flow = ids.map(e => cap[e ^ 1]);
    return { cost: total, flow, pot: Array.from(pot.subarray(0, n)) };
  }

  // ------------------------------------------------------------------ undirected and directed CPP
  function undirected(inst, startId) {
    const { ids, idx, n } = indexNodes(inst);
    const L = inst.links.map(l => [idx.get(l.u), idx.get(l.v), l.w]);
    const adj = simpleAdjacency(n, L.flatMap(([a, b, w]) => [[a, b, w], [b, a, w]]));
    const deg = new Int32Array(n);
    for (const [a, b] of L) { deg[a]++; deg[b]++; }
    const odd = []; for (let v = 0; v < n; v++) if (deg[v] % 2) odd.push(v);
    const t = odd.length, D = new Float64Array(t * t), preds = [];
    for (let i = 0; i < t; i++) {
      const r = dijkstra(adj, odd[i]); preds.push(r.pred);
      for (let j = 0; j < t; j++) {
        if (r.dist[odd[j]] === Infinity) throw new Error("The network is not connected: no single tour can cover it");
        D[i * t + j] = r.dist[odd[j]];
      }
    }
    const mate = minWeightPerfectMatching(D, t);
    const edges = L.map(([a, b]) => [a, b]), wOf = new Map();
    for (const [a, b, w] of L) for (const k of [a * n + b, b * n + a]) if (!wOf.has(k) || wOf.get(k) > w) wOf.set(k, w);
    let added = 0;
    const pairs = [];
    for (let i = 0; i < t; i++) {
      const j = mate[i];
      if (j < 0) throw new Error("Internal error: no perfect matching");
      if (i > j) continue;
      pairs.push([ids[odd[i]], ids[odd[j]]]);
      for (let x = odd[j]; x !== odd[i]; x = preds[i][x]) {
        const y = preds[i][x]; edges.push([y, x]); added += wOf.get(y * n + x);
      }
    }
    const original = L.reduce((s, l) => s + l[2], 0);
    const s0 = startId !== undefined && idx.has(startId) ? idx.get(startId) : (L.length ? L[0][0] : 0);
    const circuit = eulerianCircuit(n, edges, false, s0).map(v => ids[v]);
    return { kind: "undirected", original, added, total: original + added, lower_bound: original + added,
             optimal: true, gap_pct: 0, odd: t, pairs, circuit,
             method: "Edmonds: shortest paths + blossom matching" };
  }

  function directed(inst, startId) {
    const { ids, idx, n } = indexNodes(inst);
    const L = inst.links.map(l => [idx.get(l.u), idx.get(l.v), l.w]);
    const adj = simpleAdjacency(n, L);
    if (scc(adj).ncomp > 1) throw new Error("The network is not strongly connected: some street cannot be left");
    const supply = new Float64Array(n);
    for (const [a, b] of L) { supply[a] -= 1; supply[b] += 1; }    // in - out: surplus in must flow out
    const arcs = [];
    for (let v = 0; v < n; v++) for (let e = adj.start[v]; e < adj.start[v + 1]; e++) arcs.push([v, adj.to[e], Infinity, adj.wt[e]]);
    const f = minCostFlow(n, arcs, supply);
    const edges = L.map(([a, b]) => [a, b]);
    arcs.forEach(([a, b], k) => { for (let r = 0; r < f.flow[k]; r++) edges.push([a, b]); });
    const original = L.reduce((s, l) => s + l[2], 0);
    const s0 = startId !== undefined && idx.has(startId) ? idx.get(startId) : L[0][0];
    const circuit = eulerianCircuit(n, edges, true, s0).map(v => ids[v]);
    let unbalanced = 0; for (let v = 0; v < n; v++) if (supply[v]) unbalanced++;
    return { kind: "directed", original, added: f.cost, total: original + f.cost, lower_bound: original + f.cost,
             optimal: true, gap_pct: 0, odd: unbalanced, circuit, method: "Minimum-cost flow" };
  }

  // ------------------------------------------------------------------ mixed CPP
  /** Heuristic for the mixed CPP with a certified lower bound (as chinese_postman.mixed.solve_heuristic):
      four starting orientations (two roundings of the LP relaxation, solved as a min-cost flow,
      and the Euler-circuit orientation of the undirected CPP, both ways), each completed by an
      exact min-cost rebalance, then dual-guided street reversals (local search).
      Lower bound = max(LP relaxation, undirected CPP). */
  function mixed(inst, opts) {
    opts = Object.assign({ maxSeconds: 4, tries: 25 }, opts || {});
    const t0 = Date.now();
    const { ids, idx, n } = indexNodes(inst);
    const L = inst.links.map(l => [idx.get(l.u), idx.get(l.v), l.w, !!l.oneway]);
    const allowed = [];
    for (const [a, b, w, one] of L) { allowed.push([a, b, w]); if (!one) allowed.push([b, a, w]); }
    const adj = simpleAdjacency(n, allowed);
    if (scc(adj).ncomp > 1) throw new Error("The network is not strongly connected: some street cannot be left");
    const original = L.reduce((s, l) => s + l[2], 0);
    const deadhead = [];
    for (let v = 0; v < n; v++) for (let e = adj.start[v]; e < adj.start[v + 1]; e++) deadhead.push([v, adj.to[e], Infinity, adj.wt[e]]);

    // LP relaxation as a flow: each link driven once as stored; a two-way link may be reversed
    // (2 units at cost 0) or driven again either way at its cost.
    const sup = new Float64Array(n), arcsLP = deadhead.slice(), revArc = new Map();
    for (let k = 0; k < L.length; k++) {
      const [a, b, w, one] = L[k];
      sup[a] -= 1; sup[b] += 1;
      if (!one) { revArc.set(k, arcsLP.length); arcsLP.push([b, a, 2, 0]); }
    }
    const lp = minCostFlow(n, arcsLP, sup);
    const lpBound = original + lp.cost;
    const und = undirected({ nodes: inst.nodes, links: inst.links.map(l => ({ u: l.u, v: l.v, w: l.w, oneway: false })) });
    let lb = Math.max(lpBound, und.total);
    lb = Math.ceil(lb - 1e-9);

    const balance = oriented => {
      const s = new Float64Array(n);
      for (const [a, b] of oriented) { s[a] -= 1; s[b] += 1; }
      return minCostFlow(n, deadhead, s);
    };

    // starting orientations
    const starts = {};
    for (const tie of [0, 1]) {
      starts[`lp-round-${tie}`] = L.map(([a, b, w, one], k) => {
        if (one) return [a, b];
        const f = lp.flow[revArc.get(k)];
        return f === 2 || (f === 1 && tie === 1) ? [b, a] : [a, b];
      });
    }
    const circ = und.circuit.map(x => idx.get(x));
    for (const rev of [false, true]) {
      const seq = rev ? circ.slice().reverse() : circ, pending = new Map();
      L.forEach(([a, b, w, one], k) => {
        if (one) return;
        const key = Math.min(a, b) * n + Math.max(a, b);
        if (!pending.has(key)) pending.set(key, []);
        pending.get(key).push(k);
      });
      const o = L.map(([a, b]) => [a, b]);
      for (let i = 0; i + 1 < seq.length; i++) {
        const a = seq[i], b = seq[i + 1], q = pending.get(Math.min(a, b) * n + Math.max(a, b));
        if (q && q.length) o[q.pop()] = [a, b];
      }
      starts[`euler-${rev ? "rev" : "fwd"}`] = o;
    }
    const tried = {};
    for (const name in starts) tried[name] = balance(starts[name]).cost;

    // local search from the two best starts
    const two = L.map((l, k) => (l[3] ? -1 : k)).filter(k => k >= 0);
    let best = null, flips = 0;
    const names = Object.keys(tried).sort((x, y) => tried[x] - tried[y]).slice(0, 2);
    for (const name of names) {
      const o = starts[name].map(p => p.slice());
      let cur = balance(o);
      const deadline = t0 + opts.maxSeconds * 1000 * (best ? 1 : 0.5);
      while (Date.now() < deadline) {
        const est = two.map(k => [2 * (cur.pot[o[k][1]] - cur.pot[o[k][0]]), k]).sort((x, y) => x[0] - y[0]);
        let improved = false;
        for (const [e, k] of est.slice(0, opts.tries)) {
          if (e >= -1e-9) break;
          const [a, b] = o[k]; o[k] = [b, a];
          const c2 = balance(o);
          if (c2.cost < cur.cost - 1e-9) { cur = c2; flips++; improved = true; break; }
          o[k] = [a, b];
        }
        if (!improved) break;
      }
      if (!best || cur.cost < best.flow.cost) best = { flow: cur, oriented: o, start: name };
    }
    const edges = best.oriented.map(p => p.slice());
    deadhead.forEach(([a, b], k) => { for (let r = 0; r < best.flow.flow[k]; r++) edges.push([a, b]); });
    const total = original + best.flow.cost;
    const circuit = eulerianCircuit(n, edges, true, edges[0][0]).map(v => ids[v]);
    const gap = Math.max(0, (total - lb) / lb * 100);
    return { kind: "mixed", original, added: total - original, total, lower_bound: lb,
             optimal: total <= lb + 1e-9, gap_pct: Math.round(gap * 1000) / 1000, circuit, flips,
             heuristic: total, start: best.start, lp_bound: lpBound, undirected_bound: und.total,
             candidates: Object.fromEntries(Object.entries(tried).map(([k, v]) => [k, original + v])),
             method: "heuristic: orientation + min-cost rebalance + local search; bound from LP and undirected CPP" };
  }

  // ------------------------------------------------------------------ entry point
  function kindOf(inst) {
    const o = inst.links.map(l => !!l.oneway);
    return o.every(Boolean) ? "directed" : o.some(Boolean) ? "mixed" : "undirected";
  }

  function solve(inst, opts) {
    const t0 = Date.now();
    if (!inst.links.length) throw new Error("The network has no streets");
    const k = kindOf(inst);
    const r = k === "undirected" ? undirected(inst) : k === "directed" ? directed(inst) : mixed(inst, opts);
    r.added_pct = r.original ? Math.round(10000 * r.added / r.original) / 100 : 0;
    r.steps = r.circuit.length - 1;
    r.seconds = (Date.now() - t0) / 1000;
    return r;
  }

  const API = { solve, kindOf, undirected, directed, mixed, maxWeightMatching, minWeightPerfectMatching,
                minCostFlow, dijkstra, simpleAdjacency, scc, eulerianCircuit, Heap };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.CPP = API;
})(typeof self !== "undefined" ? self : this);
