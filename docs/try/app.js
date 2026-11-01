/* Interface for the in-browser solver. Python runs in worker.js. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const PYODIDE = new URLSearchParams(location.search).get("pyodide")
    || "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";

  // ---------------------------------------------------------------- worker RPC
  const worker = new Worker("worker.js");
  let seq = 0;
  const pending = new Map();
  worker.onmessage = e => {
    const { id, ok, out, error } = e.data;
    const p = pending.get(id); pending.delete(id);
    ok ? p.resolve(out) : p.reject(new Error(error));
  };
  const rpc = (cmd, args) => new Promise((resolve, reject) => {
    const id = ++seq; pending.set(id, { resolve, reject });
    worker.postMessage({ id, cmd, args: args || {} });
  });

  // ---------------------------------------------------------------- state
  let ready = false, busy = false, inst = null, result = null, view = null, seed = 0, map = null;
  const speeds = [0.5, 1, 2, 4, 8, 16];

  const status = (text, error) => { $("status").textContent = text; $("status").classList.toggle("error", !!error); };
  // one unit per network: km when the streets add up to 10 km or more
  const fmtLen = (v, units) => {
    if (units !== "m") return (Math.round(v * 100) / 100).toLocaleString("en");
    const total = inst ? inst.links.reduce((s, l) => s + l.w, 0) : v;
    return total >= 10000 ? `${(v / 1000).toFixed(1)} km` : `${Math.round(v).toLocaleString("en")} m`;
  };
  const kindName = k => ({ undirected: "two-way streets only", directed: "one-way streets only", mixed: "one-way and two-way streets" }[k]);
  const kindOf = I => { const o = I.links.map(l => l.oneway); return o.every(Boolean) ? "directed" : o.some(Boolean) ? "mixed" : "undirected"; };

  function setBusy(b) {
    busy = b;
    $("solve").disabled = b || !ready || !inst;
    $("fetch-osm").disabled = b || !ready;
  }

  function showFields() {
    const src = $("source").value;
    document.querySelectorAll("[data-for]").forEach(f => f.classList.toggle("hidden", !f.dataset.for.split(" ").includes(src)));
    const mixedish = ["mixed-town", "osm"].includes(src) || (inst && kindOf(inst) === "mixed");
    document.querySelectorAll("[data-kind=mixed]").forEach(f => f.classList.toggle("hidden", !mixedish));
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
    $("player").hidden = true; $("stats").hidden = true; $("downloads").hidden = true;
    $("method").textContent = "";
    const total = inst.links.reduce((s, l) => s + l.w, 0);
    $("note").textContent = `${inst.name}: ${inst.nodes.length.toLocaleString("en")} junctions, ${inst.links.length.toLocaleString("en")} streets (${kindName(kindOf(inst))}), total ${fmtLen(total, inst.units)}. ${inst.note || ""}`;
    showFields();
    setBusy(false);
    status("Ready. Press “Find the route”.");
  }

  let loadToken = 0;
  async function load() {
    if (!ready) return;
    const src = $("source").value;
    const token = ++loadToken;                 // only the latest request may replace the network
    const show = I => { if (token === loadToken) showInst(I); };
    try {
      if (["pfc1997", "konigsberg", "petersen", "grid", "delaunay", "oneway-grid", "mixed-town"].includes(src)) {
        setBusy(true); status("Building the network…");
        const size = ["delaunay"].includes(src) ? +$("junctions").value : +$("side").value;
        show(JSON.parse(await rpc("example", { name: src, size, oneway: +$("oneway").value, seed })));
      } else if (src === "benchmark") {
        const name = $("bench").value;
        if (!name) return;
        setBusy(true); status(`Loading ${name}…`);
        const text = await (await fetch(`data/carp/${name}.dat`)).text();
        show(JSON.parse(await rpc("carp", { text, name: `Benchmark ${name}` })));
      } else if (src === "upload") {
        const f = $("file").files[0];
        if (!f) { status("Choose a .GRA file."); return; }
        setBusy(true); status(`Reading ${f.name}…`);
        show(JSON.parse(await rpc("gra", { text: await f.text(), name: f.name })));
      } else if (src === "osm") {
        status("Choose an area on the map, then fetch its streets.");
      }
    } catch (err) { setBusy(false); status(err.message, true); }
  }

  // ---------------------------------------------------------------- solving
  async function solve() {
    if (!inst || busy) return;
    setBusy(true);
    const target = inst;
    const kind = kindOf(inst);
    const limit = +$("time-limit").value;
    status(kind === "mixed" ? `Solving (up to ${limit} s for one-way and two-way mixes)…` : "Solving…");
    try {
      const res = JSON.parse(await rpc("solve", { inst: JSON.stringify(inst), timeLimit: limit, gapTol: +$("gap").value }));
      if (!res.ok) throw new Error(res.error);
      if (target !== inst) { setBusy(false); return; }   // the network changed meanwhile
      result = res;
      view.setResult(res);
      renderStats(res);
      $("player").hidden = false; $("downloads").hidden = false;
      $("play").textContent = "Play the tour";
      status("Done.");
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) view.finish();
    } catch (err) { status(err.message, true); }
    setBusy(false);
  }

  function renderStats(r) {
    const u = inst.units;
    const extraWalks = r.steps - inst.links.length;
    const quality = r.optimal ? "Proven optimal" : `Within ${r.gap_pct.toFixed(2)}% of optimal`;
    const items = [
      ["Streets, once each", fmtLen(r.original, u)],
      ["Postman's tour", fmtLen(r.total, u)],
      ["Extra distance", `${fmtLen(r.added, u)} (${r.added_pct.toFixed(1)}%)`],
      ["Streets walked again", extraWalks.toLocaleString("en")],
      ["Quality", quality],
      ["Time", `${r.seconds.toFixed(2)} s`],
    ];
    $("stats").innerHTML = items.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");
    $("stats").hidden = false;
    let m = `Method: ${r.method}.`;
    if (r.kind === "mixed" && r.heuristic != null)
      m += ` The heuristic alone found ${fmtLen(r.heuristic, u)}; the proven lower bound is ${fmtLen(r.lower_bound, u)}.`;
    $("method").textContent = m;
  }

  // ---------------------------------------------------------------- OpenStreetMap
  function addCss(href) { const l = document.createElement("link"); l.rel = "stylesheet"; l.href = href; document.head.appendChild(l); }
  function addJs(src) { return new Promise((ok, bad) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = bad; document.head.appendChild(s); }); }
  async function ensureMap() {
    if (map) { setTimeout(() => map.invalidateSize(), 50); return; }
    addCss("https://unpkg.com/leaflet@1.9.4/dist/leaflet.css");
    try { await addJs("https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"); }
    catch { status("The map could not be loaded. Check your connection.", true); return; }
    map = L.map("osm-map").setView([41.3925, 2.1635], 17);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "© OpenStreetMap contributors",
    }).addTo(map);
  }
  async function fetchOsm() {
    if (!map || busy || !ready) return;
    const b = map.getBounds();
    const s = b.getSouth(), w = b.getWest(), n = b.getNorth(), e = b.getEast();
    const km2 = (n - s) * 111 * (e - w) * 111 * Math.cos((n + s) / 2 * Math.PI / 180);
    if (km2 > 1.5) { status(`This view covers ${km2.toFixed(1)} km². Zoom in to about 1 km² or less.`, true); return; }
    setBusy(true); status("Fetching streets from OpenStreetMap…");
    try {
      const q = await rpc("query", { s, w, n, e });
      const resp = await fetch("https://overpass-api.de/api/interpreter", {
        method: "POST", body: "data=" + encodeURIComponent(q),
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      if (resp.status === 429) throw new Error("OpenStreetMap is busy (too many requests). Try again in a minute.");
      if (!resp.ok) throw new Error(`OpenStreetMap answered with error ${resp.status}. Try a smaller area.`);
      const text = await resp.text();
      status("Building the street network…");
      showInst(JSON.parse(await rpc("osm", { text, name: `OpenStreetMap area around ${((s + n) / 2).toFixed(4)}, ${((w + e) / 2).toFixed(4)}` })));
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
  $("fetch-osm").addEventListener("click", fetchOsm);
  $("play").addEventListener("click", () => {
    if (!view) return;
    if (view.isPlaying()) { view.pause(); $("play").textContent = "Play the tour"; }
    else { view.play(); $("play").textContent = "Pause"; }
  });
  $("final").addEventListener("click", () => { view && view.finish(); $("play").textContent = "Play again"; });
  $("speed").addEventListener("input", () => view && view.setSpeed(speeds[+$("speed").value]));

  fetch("data/benchmarks.json").then(r => r.json()).then(list => {
    $("bench").innerHTML = list.map(b => `<option value="${b.name}">${b.name} (${b.vertices} junctions, ${b.edges} streets)</option>`).join("");
  }).catch(() => {});

  showFields();
  const t0 = performance.now();
  rpc("init", { indexURL: PYODIDE }).then(() => {
    ready = true;
    status(`Python loaded in ${((performance.now() - t0) / 1000).toFixed(0)} s.`);
    load();
  }).catch(err => status("Python could not be loaded: " + err.message, true));
})();
