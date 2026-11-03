/* Interface for the in-browser solver.
   solver-worker.js runs the JavaScript solver (instant start). Python (Pyodide, worker.js) is
   loaded only on request, to prove the optimum of networks with both one-way and two-way streets. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);

  // ---------------------------------------------------------------- workers
  function makeRpc(url) {
    const w = new Worker(url);
    let seq = 0;
    const pending = new Map();
    const api = { onProgress: () => {}, worker: w };
    w.onmessage = e => {
      if (e.data.progress) { api.onProgress(e.data.progress); return; }
      const { id, ok, out, error } = e.data, p = pending.get(id);
      pending.delete(id);
      ok ? p.resolve(out) : p.reject(new Error(error));
    };
    w.onerror = e => { for (const p of pending.values()) p.reject(new Error(e.message || "worker error")); pending.clear(); };
    api.call = (cmd, args) => new Promise((resolve, reject) => {
      const id = ++seq; pending.set(id, { resolve, reject });
      w.postMessage({ id, cmd, args: args || {} });
    });
    return api;
  }
  const js = makeRpc("solver-worker.js");
  let py = null;                       // created on demand

  // ---------------------------------------------------------------- state
  let busy = false, inst = null, base = null, result = null, view = null, seed = 0, shareSeed = 1, map = null;
  const speeds = [0.5, 1, 2, 4, 8, 16];
  const status = (text, error) => { $("status").textContent = text; $("status").classList.toggle("error", !!error); };
  const kindOf = I => { if (I.links.some(l => l.w2 !== undefined && l.w2 !== l.w)) return "windy"; const o = I.links.map(l => l.oneway); return o.every(Boolean) ? "directed" : o.some(Boolean) ? "mixed" : "undirected"; };
  const kindName = k => ({ undirected: "two-way streets only", directed: "one-way streets only", mixed: "one-way and two-way streets", windy: "a different cost each way" }[k]);
  const fmtLen = v => {                // one unit per network: km when the streets add up to 10 km or more
    if (!inst || inst.units !== "m") return (Math.round(v * 100) / 100).toLocaleString("en");
    const total = inst.links.reduce((s, l) => s + l.w, 0);
    return total >= 10000 ? `${(v / 1000).toFixed(1)} km` : `${Math.round(v).toLocaleString("en")} m`;
  };

  function setBusy(b) { busy = b; $("solve").disabled = b || !inst; $("fetch-osm").disabled = b; }

  // ---------------------------------------------------------------- service settings
  function pickDepot(I) {               // the junction nearest the middle of the drawing
    const xs = I.nodes.map(n => n.x), ys = I.nodes.map(n => n.y);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    let best = I.nodes[0];
    for (const n of I.nodes) if (Math.hypot(n.x - cx, n.y - cy) < Math.hypot(best.x - cx, best.y - cy)) best = n;
    return best.id;
  }
  function rng(seed) {
    let a = (seed >>> 0) + 0x9e3779b9;
    return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a);
                   t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  function derive() {                   // the network as it will be solved: who serves what
    const mode = $("serve").value, onFoot = $("source").value === "osm" && $("on-foot").checked;
    const r = rng(shareSeed), share = +$("serve-share").value;
    const links = base.links.map(l => {
      const c = Object.assign({}, l);
      if (onFoot) c.oneway = false;
      delete c.req;
      if (mode === "share") c.req = r() < share;
      else if (mode === "main") c.req = !!l.main;
      else if (mode === "marked") c.req = l.marked !== false;
      return c;
    });
    if (links.length && !links.some(l => l.req !== false)) links[0].req = true;
    return Object.assign({}, base, { links, depot: pickDepot(base) });
  }
  function serveOptions() {
    const has = { all: true, share: true, main: base && base.links.some(l => l.main) && base.links.some(l => !l.main),
                  marked: base && !!base.marked };
    for (const o of $("serve").options) o.hidden = o.disabled = !has[o.value];
    if (!has[$("serve").value]) $("serve").value = "all";
    $("share-field").hidden = $("serve").value !== "share";
  }
  function serviceHint() {
    if (!inst) return "";
    const k = +$("postmen").value, partial = inst.links.some(l => l.req === false);
    if (kindOf(inst) !== "undirected" && (k > 1 || partial))
      return "Serving only some streets, or sharing them among several postmen, works on two-way networks." +
             ($("source").value === "osm" ? " Tick “On foot” to let the postmen walk one-way streets both ways." : " Choose a network without one-way streets.");
    return "";
  }
  function applyService() {
    if (!base) return;
    serveOptions();
    showInst(derive());
  }

  function showFields() {
    const src = $("source").value;
    document.querySelectorAll("[data-for]").forEach(f => f.classList.toggle("hidden", !f.dataset.for.split(" ").includes(src)));
    $("osm-map").classList.toggle("hidden", src !== "osm");
    if (src === "osm") ensureMap();
  }

  // ---------------------------------------------------------------- drawing
  function legend(mode) {
    const k = (cls, text) => `<span class="key"><i class="${cls}"></i>${text}</span>`;
    const parts = [];
    if (mode === "postmen") parts.push("Each colour: the streets one postman serves.", k("k-street", "walked through or not yet served"));
    else parts.push(k("k-street", "street"), k("k-route", "served"), k("k-repeat", "walked again, or only walked through"));
    if (inst.links.some(l => l.req === false)) parts.push(k("k-optional", "no service needed"));
    if (inst.depot !== undefined && (mode === "postmen" || inst.links.some(l => l.req === false))) parts.push(k("k-depot", "depot"));
    if (kindOf(inst) === "undirected" && inst.nodes.length <= 400 && mode !== "postmen" && !inst.links.some(l => l.req === false))
      parts.push("Dark dots: junctions with an odd number of streets.");
    if (inst.links.some(l => l.oneway)) parts.push("Arrows: one-way streets.");
    $("legend").innerHTML = parts.join("&nbsp;&nbsp; ");
  }

  // What is being solved, and what kind of answer to expect
  function requiredPieces(I) {
    const up = new Map(), find = x => { while (up.get(x) !== x) { up.set(x, up.get(up.get(x))); x = up.get(x); } return x; };
    const add = x => { if (!up.has(x)) up.set(x, x); };
    if (I.depot !== undefined) add(I.depot);
    for (const l of I.links) if (l.req !== false) { add(l.u); add(l.v); up.set(find(l.u), find(l.v)); }
    return new Set([...up.keys()].map(find)).size;
  }

  function problemOf(I) {
    const k = +$("postmen").value, partial = I.links.some(l => l.req === false), kind = kindOf(I);
    const proof = ["Exact proof on request", "method"];
    if (kind !== "undirected" && (k > 1 || partial))
      return { name: "Combination not available", tone: "off", link: "",
               chips: [["Not available", "off"]],
               text: "Serving only some streets, or sharing them among several postmen, works on two-way networks with one cost per street." };
    if (k > 1)
      return { name: "Several postmen", tone: "hard", link: "104-several-postmen",
               chips: [["NP-hard", "hard"], ["Heuristic with a lower bound", "method"]],
               text: "Share the streets among the postmen so that the longest route is as short as possible." };
    if (partial) {
      const one = requiredPieces(I) === 1;
      return { name: "Rural postman", tone: one ? "easy" : "hard", link: "103-the-rural-postman-problem",
               chips: one ? [["Polynomial here", "easy"], ["Exact method", "method"]]
                          : [["NP-hard", "hard"], ["Heuristic with a lower bound", "method"], proof],
               text: one ? "Only some streets need service, and they form one connected piece with the depot, so the problem stays easy."
                         : "Only some streets need service, and joining their separate pieces is the hard part." };
    }
    return {
      undirected: { name: "Undirected Chinese postman", tone: "easy", link: "32-edmonds-method",
                    chips: [["Polynomial", "easy"], ["Exact method", "method"]],
                    text: "Drive every street at least once and return. Every street can be driven both ways." },
      directed: { name: "Directed Chinese postman", tone: "easy", link: "63-directed-graphs",
                  chips: [["Polynomial", "easy"], ["Exact method", "method"]],
                  text: "Drive every street at least once and return. Every street is one-way." },
      mixed: { name: "Mixed Chinese postman", tone: "hard", link: "9-the-mixed-chinese-postman-problem",
               chips: [["NP-hard", "hard"], ["Heuristic with a lower bound", "method"], proof],
               text: "One-way and two-way streets together. Choosing a direction for each two-way street is the hard part." },
      windy: { name: "Windy postman", tone: "hard", link: "106-the-windy-postman",
               chips: [["NP-hard", "hard"], ["Win's heuristic with a lower bound", "method"], proof],
               text: "Every street can be driven both ways, at a different cost each way." },
    }[kind];
  }

  function showProblem(I, verdict) {
    const p = problemOf(I), chips = p.chips.concat(verdict ? [verdict] : []);
    $("problem").hidden = false;
    $("problem").dataset.tone = p.tone;
    $("problem-name").textContent = p.name;
    $("problem-text").textContent = p.text;
    $("problem-chips").innerHTML = chips.map(([t, c]) => `<li class="chip ${c}">${t}</li>`).join("");
    $("problem-link").hidden = !p.link;
    $("problem-link").href = `../report/#${p.link}`;
  }

  function showInst(newInst) {
    inst = newInst; result = null;
    $("empty").classList.add("hidden");
    const twoWay = kindOf(inst) === "undirected", partial = inst.links.some(l => l.req === false);
    const showDepot = partial || +$("postmen").value > 1;
    view = Postman.draw($("net"), inst, { labels: "auto", weights: "auto",
                                          odd: twoWay && !partial && inst.nodes.length <= 400,
                                          depot: showDepot ? inst.depot : undefined });
    $("cost-hint").textContent = view.costsShown ? "The label on each street gives its cost."
      : "Too many streets to label: rest the pointer on a street, or tap it, to see its cost.";
    $("cost-hint").hidden = false;
    legend(+$("postmen").value > 1 ? "postmen" : "single");
    $("routes").hidden = true;
    $("service-hint").textContent = serviceHint();
    showProblem(inst);
    $("speed").value = inst.links.length > 1000 ? 5 : inst.links.length > 200 ? 3 : 1;
    view.setSpeed(speeds[+$("speed").value]);
    view.onProgress((i, n) => { $("progress").textContent = n ? `${i} of ${n} streets walked` : ""; });
    view.onEnd(() => { $("play").textContent = "Play again"; });
    $("player").hidden = $("stats").hidden = $("downloads").hidden = $("proof").hidden = true;
    $("method").textContent = "";
    const total = inst.links.reduce((s, l) => s + l.w, 0);
    const req = inst.links.filter(l => l.req !== false), serve = req.reduce((s, l) => s + l.w, 0);
    const part = partial ? ` ${req.length.toLocaleString("en")} of them need service (${fmtLen(serve)}).` : "";
    $("note").textContent = `${inst.name}: ${inst.nodes.length.toLocaleString("en")} junctions, ${inst.links.length.toLocaleString("en")} streets (${kindName(kindOf(inst))}), total ${fmtLen(total)}.${part} ${inst.note || ""}`;
    setBusy(false);
    status("Ready. Press “Find the route”.");
  }

  let loadToken = 0;
  async function load() {
    const src = $("source").value, token = ++loadToken;
    const show = I => { if (token === loadToken) { base = I; applyService(); } };
    try {
      if (["example1997", "konigsberg", "petersen", "grid", "delaunay", "oneway-grid", "mixed-town", "hilly-town"].includes(src)) {
        setBusy(true); status("Building the network…");
        const size = src === "delaunay" ? +$("junctions").value : +$("side").value;
        show(await js.call("example", { name: src, size, share: +$("oneway").value, seed }));
      } else if (src === "benchmark") {
        const name = $("bench").value;
        if (!name) return;
        setBusy(true); status(`Loading ${name}…`);
        const text = await (await fetch(`data/carp/${name}.dat`)).text();
        show(await js.call("carp", { text, name: `Benchmark ${name}` }));
      } else if (src === "upload") {
        const f = $("file").files[0];
        if (!f) { status("Choose a .GRA file."); return; }
        setBusy(true); status(`Reading ${f.name}…`);
        show(await js.call("gra", { text: await f.text(), name: f.name }));
      } else if (src === "osm") {
        status("Choose an area on the map, then fetch its streets.");
      }
    } catch (err) { if (token === loadToken) { setBusy(false); status(err.message, true); } }
  }

  // ---------------------------------------------------------------- solving
  async function solve() {
    if (!inst || busy) return;
    setBusy(true);
    const target = inst, k = Math.max(1, Math.min(8, Math.round(+$("postmen").value || 1)));
    const hint = serviceHint();
    if (hint) { setBusy(false); status(hint, true); return; }
    const partial = inst.links.some(l => l.req === false);
    status(k > 1 ? `Sharing the streets among ${k} postmen (a few seconds)…` :
           partial ? "Planning the route (a few seconds when the streets to serve are scattered)…" :
           kindOf(inst) === "mixed" ? "Solving (one-way and two-way streets: a few seconds)…" : "Solving…");
    try {
      const res = await js.call("solve", { inst, maxSeconds: 4, k });
      if (target !== inst) return;
      showResult(res);
      status("Done.");
    } catch (err) { status(err.message, true); }
    finally { setBusy(false); }
  }

  function showResult(res) {
    result = res;
    view.setResult(res);
    renderStats(res);
    $("player").hidden = $("downloads").hidden = false;
    $("play").textContent = "Play the tour";
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) view.finish();
    legend(res.kind === "postmen" ? "postmen" : "single");
    renderRoutes(res);
    showProblem(inst, res.optimal ? ["Proven optimal", "easy"] : [`Within ${res.gap_pct.toFixed(2)}% of the bound`, "hard"]);
    const needProof = ["mixed", "rural", "windy"].includes(res.kind) && !res.optimal;
    $("proof").hidden = !needProof;
    $("proof-status").textContent = "";
    $("proof-status").classList.remove("error");
    $("proof-controls").hidden = false;
    if (needProof) {
      const why = res.kind === "rural"
        ? `The streets to serve lie in ${res.pieces} separate pieces, and choosing how to join them is what makes the exact problem hard`
        : "Streets that mix one-way and two-way traffic make the exact problem hard";
      $("proof-text").textContent =
        `This tour is at most ${res.gap_pct.toFixed(2)}% longer than the best possible one, and usually much closer. ` +
        `${why}, so proving the optimum needs a branch-and-cut solver: the page can download Python with it ` +
        `(about 37 MB the first time) and search for a shorter tour.`;
    }
  }

  function renderRoutes(r) {
    const ul = $("routes");
    if (r.kind !== "postmen") { ul.hidden = true; return; }
    ul.innerHTML = r.routes.map((rt, k) =>
      `<li><i style="background:${view.colorOf(k)}"></i>Postman ${k + 1}: ${fmtLen(rt.cost)}, ${rt.streets} streets</li>`).join("");
    ul.hidden = false;
  }

  function renderStats(r) {
    const quality = r.optimal ? "Proven optimal" : `Within ${r.gap_pct.toFixed(2)}%`;
    if (r.kind === "postmen") {
      const items = [
        ["Postmen", String(r.k)],
        ["Longest route", fmtLen(r.longest)],
        ["All routes together", fmtLen(r.total)],
        ["Lower bound, longest route", fmtLen(r.lower_bound)],
        ["Quality", quality],
        ["Time", `${r.seconds.toFixed(2)} s`],
      ];
      $("stats").innerHTML = items.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");
      $("stats").hidden = false;
      $("method").textContent = `Method: ${r.method}. One postman alone would walk ${fmtLen(r.single)}; ` +
        `the best split of that tour gave a longest route of ${fmtLen(r.split_longest)} before streets were moved between routes.`;
      return;
    }
    if (r.kind === "rural") {
      const items = [
        ["Streets to serve", fmtLen(r.served)],
        ["Postman's route", fmtLen(r.total)],
        ["Walked without serving", `${fmtLen(r.deadhead)} (${(100 * r.deadhead / r.served).toFixed(1)}%)`],
        ["Pieces to join", String(r.pieces)],
        ["Quality", quality],
        ["Time", `${r.seconds.toFixed(2)} s`],
      ];
      $("stats").innerHTML = items.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");
      $("stats").hidden = false;
      $("method").textContent = `Method: ${r.method}.` + (r.optimal ? "" : ` Proven lower bound: ${fmtLen(r.lower_bound)}.`);
      return;
    }
    const extraWalks = r.steps - inst.links.length;
    const items = [
      ["Streets, once each", fmtLen(r.original)],
      ["Postman's tour", fmtLen(r.total)],
      ["Extra distance", `${fmtLen(r.added)} (${r.added_pct.toFixed(1)}%)`],
      ["Streets walked again", extraWalks.toLocaleString("en")],
      ["Quality", quality],
      ["Time", `${r.seconds.toFixed(2)} s`],
    ];
    $("stats").innerHTML = items.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");
    $("stats").hidden = false;
    let m = `Method: ${r.method}.`;
    if (r.kind === "mixed" || r.kind === "windy") m += ` Proven lower bound: ${fmtLen(r.lower_bound)}.`;
    $("method").textContent = m;
  }

  // ---------------------------------------------------------------- exact proof with Python (on demand)
  const OWN_PYODIDE = new URL("../pyodide/", location.href).href;
  const CDN_PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";
  async function pyodideURL() {
    const override = new URLSearchParams(location.search).get("pyodide");
    if (override) return override;
    try { if ((await fetch(OWN_PYODIDE + "pyodide-lock.json", { method: "HEAD" })).ok) return OWN_PYODIDE; } catch (e) { /* CDN */ }
    return CDN_PYODIDE;
  }
  let pyReady = null;
  async function prove() {
    if (!inst || !result || busy) return;
    const target = inst, ps = $("proof-status");
    setBusy(true); $("prove").disabled = true; ps.classList.remove("error");
    const t0 = performance.now(), secs = () => Math.round((performance.now() - t0) / 1000);
    let stage = "Starting Python…";
    const timer = setInterval(() => { ps.textContent = `${stage} ${secs()} s`; }, 1000);
    try {
      if (!py) {
        py = makeRpc("worker.js");
        py.onProgress = text => { stage = text; ps.textContent = `${stage} ${secs()} s`; };
        pyReady = pyodideURL().then(indexURL => py.call("init", { indexURL }));
      }
      await pyReady;
      const limit = +$("time-limit").value;
      stage = `Branch-and-cut: searching for a shorter tour (up to ${limit} s)…`;
      const res = JSON.parse(await py.call("solve", { inst: JSON.stringify(inst), timeLimit: limit, gapTol: 0 }));
      if (!res.ok) throw new Error(res.error);
      if (target !== inst) return;
      res.method = "branch-and-cut (HiGHS), started from the heuristic tour";
      const before = result.total;
      showResult(res);
      $("proof").hidden = false;
      if (res.optimal) {
        $("proof-text").textContent = res.total < before
          ? `Branch-and-cut found a tour ${fmtLen(before - res.total)} shorter than the heuristic one and proved that no shorter tour exists.`
          : "Branch-and-cut proved that the heuristic tour was already the shortest possible.";
        $("proof-controls").hidden = true;
      } else {
        $("proof-text").textContent = `The time limit was reached: the tour is now within ${res.gap_pct.toFixed(2)}% of the optimum. A longer time limit may prove it.`;
      }
      ps.textContent = `Python and the proof took ${secs()} s.`;
    } catch (err) {
      ps.textContent = "Could not prove the optimum: " + err.message + ". Reload the page to try again.";
      ps.classList.add("error");
      py = null;
    } finally { clearInterval(timer); setBusy(false); $("prove").disabled = false; }
  }

  // ---------------------------------------------------------------- OpenStreetMap
  function addCss(href) { const l = document.createElement("link"); l.rel = "stylesheet"; l.href = href; document.head.appendChild(l); }
  function addJs(src) { return new Promise((ok, bad) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = bad; document.head.appendChild(s); }); }
  async function ensureMap() {
    if (map) { setTimeout(() => map.invalidateSize(), 50); return; }
    addCss("https://unpkg.com/leaflet@1.9.4/dist/leaflet.css");
    try { await addJs("https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"); }
    catch (e) { status("The map could not be loaded. Check your connection.", true); return; }
    map = L.map("osm-map").setView([41.3925, 2.1635], 17);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(map);
  }
  async function fetchOsm() {
    if (!map || busy) return;
    const b = map.getBounds(), s = b.getSouth(), w = b.getWest(), n = b.getNorth(), e = b.getEast();
    const km2 = (n - s) * 111 * (e - w) * 111 * Math.cos((n + s) / 2 * Math.PI / 180);
    if (km2 > 1.5) { status(`This view covers ${km2.toFixed(1)} km². Zoom in to about 1 km² or less.`, true); return; }
    const token = ++loadToken;
    setBusy(true); status("Fetching streets from OpenStreetMap…");
    try {
      const q = await js.call("query", { s, w, n, e });
      const resp = await fetch("https://overpass-api.de/api/interpreter", {
        method: "POST", body: "data=" + encodeURIComponent(q), headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      if (resp.status === 429) throw new Error("OpenStreetMap is busy (too many requests). Try again in a minute.");
      if (!resp.ok) throw new Error(`OpenStreetMap answered with error ${resp.status}. Try a smaller area.`);
      const text = await resp.text();
      status("Building the street network…");
      const I = await js.call("osm", { text, name: `OpenStreetMap area around ${((s + n) / 2).toFixed(4)}, ${((w + e) / 2).toFixed(4)}` });
      if (token === loadToken) { base = I; applyService(); }
    } catch (err) { setBusy(false); status(err.message, true); }
  }

  // ---------------------------------------------------------------- downloads
  function download(name, text, type) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type }));
    a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  $("dl-tour").addEventListener("click", () => {
    if (!result) return;
    const lab = new Map(inst.nodes.map(n => [n.id, n.label]));
    const routes = result.routes ? result.routes.map(r => r.circuit) : [result.circuit];
    const rows = ["postman,step,from,to"];
    routes.forEach((c, p) => { for (let k = 0; k + 1 < c.length; k++) rows.push(`${p + 1},${k + 1},${lab.get(c[k])},${lab.get(c[k + 1])}`); });
    download("postman-tour.csv", rows.join("\n"), "text/csv");
  });
  $("dl-net").addEventListener("click", () => inst && download("network.json", JSON.stringify(inst, null, 1), "application/json"));

  // ---------------------------------------------------------------- wiring
  $("source").addEventListener("change", () => { showFields(); load(); });
  $("serve").addEventListener("change", applyService);
  $("serve-share").addEventListener("input", () => { $("serve-out").textContent = Math.round($("serve-share").value * 100) + "%"; });
  $("serve-share").addEventListener("change", applyService);
  $("reshare").addEventListener("click", () => { shareSeed++; applyService(); });
  $("postmen").addEventListener("change", applyService);
  $("on-foot").addEventListener("change", applyService);
  ["side", "junctions", "bench", "file"].forEach(id => $(id).addEventListener("change", load));
  $("oneway").addEventListener("input", () => { $("oneway-out").textContent = Math.round($("oneway").value * 100) + "%"; });
  $("oneway").addEventListener("change", load);
  $("reseed").addEventListener("click", () => { seed++; load(); });
  $("solve").addEventListener("click", solve);
  $("prove").addEventListener("click", prove);
  $("fetch-osm").addEventListener("click", fetchOsm);
  $("play").addEventListener("click", () => {
    if (!view) return;
    if (view.isPlaying()) { view.pause(); $("play").textContent = "Play the tour"; }
    else { view.play(); $("play").textContent = "Pause"; }
  });
  $("final").addEventListener("click", () => { if (view) { view.finish(); $("play").textContent = "Play again"; } });
  $("speed").addEventListener("input", () => view && view.setSpeed(speeds[+$("speed").value]));

  fetch("data/benchmarks.json").then(r => r.json()).then(list => {
    $("bench").innerHTML = list.map(b => `<option value="${b.name}">${b.name} (${b.vertices} junctions, ${b.edges} streets)</option>`).join("");
  }).catch(() => {});

  showFields();
  load();
})();
