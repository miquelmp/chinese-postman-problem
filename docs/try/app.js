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
  let busy = false, inst = null, result = null, view = null, seed = 0, map = null;
  const speeds = [0.5, 1, 2, 4, 8, 16];
  const status = (text, error) => { $("status").textContent = text; $("status").classList.toggle("error", !!error); };
  const kindOf = I => { const o = I.links.map(l => l.oneway); return o.every(Boolean) ? "directed" : o.some(Boolean) ? "mixed" : "undirected"; };
  const kindName = k => ({ undirected: "two-way streets only", directed: "one-way streets only", mixed: "one-way and two-way streets" }[k]);
  const fmtLen = v => {                // one unit per network: km when the streets add up to 10 km or more
    if (!inst || inst.units !== "m") return (Math.round(v * 100) / 100).toLocaleString("en");
    const total = inst.links.reduce((s, l) => s + l.w, 0);
    return total >= 10000 ? `${(v / 1000).toFixed(1)} km` : `${Math.round(v).toLocaleString("en")} m`;
  };

  function setBusy(b) { busy = b; $("solve").disabled = b || !inst; $("fetch-osm").disabled = b; }

  function showFields() {
    const src = $("source").value;
    document.querySelectorAll("[data-for]").forEach(f => f.classList.toggle("hidden", !f.dataset.for.split(" ").includes(src)));
    $("osm-map").classList.toggle("hidden", src !== "osm");
    if (src === "osm") ensureMap();
  }

  // ---------------------------------------------------------------- drawing
  function showInst(newInst) {
    inst = newInst; result = null;
    $("empty").classList.add("hidden");
    const twoWay = kindOf(inst) === "undirected";
    view = Postman.draw($("net"), inst, { labels: "auto", weights: inst.links.length <= 30, odd: twoWay && inst.nodes.length <= 400 });
    $("odd-key").hidden = !twoWay;
    $("speed").value = inst.links.length > 1000 ? 5 : inst.links.length > 200 ? 3 : 1;
    view.setSpeed(speeds[+$("speed").value]);
    view.onProgress((i, n) => { $("progress").textContent = n ? `${i} of ${n} streets walked` : ""; });
    view.onEnd(() => { $("play").textContent = "Play again"; });
    $("player").hidden = $("stats").hidden = $("downloads").hidden = $("proof").hidden = true;
    $("method").textContent = "";
    const total = inst.links.reduce((s, l) => s + l.w, 0);
    $("note").textContent = `${inst.name}: ${inst.nodes.length.toLocaleString("en")} junctions, ${inst.links.length.toLocaleString("en")} streets (${kindName(kindOf(inst))}), total ${fmtLen(total)}. ${inst.note || ""}`;
    setBusy(false);
    status("Ready. Press “Find the route”.");
  }

  let loadToken = 0;
  async function load() {
    const src = $("source").value, token = ++loadToken;
    const show = I => { if (token === loadToken) showInst(I); };
    try {
      if (["example1997", "konigsberg", "petersen", "grid", "delaunay", "oneway-grid", "mixed-town"].includes(src)) {
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
    const target = inst;
    status(kindOf(inst) === "mixed" ? "Solving (one-way and two-way streets: a few seconds)…" : "Solving…");
    try {
      const res = await js.call("solve", { inst, maxSeconds: 4 });
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
    const needProof = res.kind === "mixed" && !res.optimal;
    $("proof").hidden = !needProof;
    $("proof-status").textContent = "";
    $("proof-status").classList.remove("error");
    $("proof-controls").hidden = false;
    if (needProof) {
      $("proof-text").textContent =
        `This tour is at most ${res.gap_pct.toFixed(2)}% longer than the best possible one, and usually much closer. ` +
        `Streets that mix one-way and two-way traffic make the exact problem hard, so proving the optimum needs a ` +
        `branch-and-cut solver: the page can download Python with it (about 37 MB the first time) and search for a shorter tour.`;
    }
  }

  function renderStats(r) {
    const extraWalks = r.steps - inst.links.length;
    const quality = r.optimal ? "Proven optimal" : `Within ${r.gap_pct.toFixed(2)}%`;
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
    if (r.kind === "mixed") m += ` Proven lower bound: ${fmtLen(r.lower_bound)}.`;
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
      if (token === loadToken) showInst(I);
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
    const c = result.circuit, rows = ["step,from,to"];
    for (let k = 0; k + 1 < c.length; k++) rows.push(`${k + 1},${lab.get(c[k])},${lab.get(c[k + 1])}`);
    download("postman-tour.csv", rows.join("\n"), "text/csv");
  });
  $("dl-net").addEventListener("click", () => inst && download("network.json", JSON.stringify(inst, null, 1), "application/json"));

  // ---------------------------------------------------------------- wiring
  $("source").addEventListener("change", () => { showFields(); load(); });
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
