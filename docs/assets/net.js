/* Draws a street network as SVG and animates a postman tour over it.
   Instance: {nodes:[{id,x,y,label}], links:[{u,v,w,oneway}]}
   Result:   {circuit:[node ids]}
   Streets turn yellow on their first traversal and red on the second. */
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  };

  function draw(svg, inst, opts) {
    opts = Object.assign({ labels: "auto", weights: false, odd: false, width: 800 }, opts || {});
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const nodes = new Map(inst.nodes.map(n => [n.id, n]));
    const xs = inst.nodes.map(n => n.x), ys = inst.nodes.map(n => n.y);
    const minx = Math.min(...xs), maxx = Math.max(...xs), miny = Math.min(...ys), maxy = Math.max(...ys);
    const spanx = Math.max(maxx - minx, 1e-9), spany = Math.max(maxy - miny, 1e-9);
    const W = opts.width, pad = inst.nodes.length > 400 ? 14 : 34;
    let aspect = spany / spanx;
    aspect = Math.min(Math.max(aspect, 0.45), 1.3);
    const H = Math.round(W * aspect);
    const s = Math.min((W - 2 * pad) / spanx, (H - 2 * pad) / spany);
    const ox = (W - s * spanx) / 2, oy = (H - s * spany) / 2;
    const P = id => { const n = nodes.get(id); return [ox + (n.x - minx) * s, oy + (maxy - n.y) * s]; };
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.classList.add("net");

    const big = inst.links.length > 600;
    const streetW = big ? 1.2 : inst.links.length > 150 ? 1.8 : 2.4;
    const gStreets = el("g", {}, svg), gArrows = el("g", {}, svg), gText = el("g", {}, svg), gNodes = el("g", {}, svg);

    // parallel streets between the same pair are drawn as gentle curves
    const pairs = new Map();
    inst.links.forEach((l, i) => {
      const key = l.u < l.v ? `${l.u}|${l.v}` : `${l.v}|${l.u}`;
      if (!pairs.has(key)) pairs.set(key, []);
      pairs.get(key).push(i);
    });
    const paths = [];
    pairs.forEach(list => {
      list.forEach((i, k) => {
        const l = inst.links[i];
        const [x1, y1] = P(l.u), [x2, y2] = P(l.v);
        const off = (k - (list.length - 1) / 2) * 26;
        let d;
        if (off === 0) d = `M${x1} ${y1}L${x2} ${y2}`;
        else {
          const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, len = Math.hypot(x2 - x1, y2 - y1) || 1;
          const sign = l.u < l.v ? 1 : -1;
          const cx = mx - (y2 - y1) / len * off * 2 * sign, cy = my + (x2 - x1) / len * off * 2 * sign;
          d = `M${x1} ${y1}Q${cx} ${cy} ${x2} ${y2}`;
        }
        const p = el("path", { d, class: "street" + (l.oneway ? " oneway" : ""), "stroke-width": streetW }, gStreets);
        p.dataset.base = streetW;
        paths[i] = p;
      });
    });

    // one-way arrows at mid-street
    if (inst.links.some(l => l.oneway) && inst.links.length <= 1500) {
      const a = Math.max(3.2, Math.min(6, streetW * 2.4));
      inst.links.forEach((l, i) => {
        if (!l.oneway) return;
        const p = paths[i], L = p.getTotalLength();
        if (L < a * 3) return;
        const m = p.getPointAtLength(L / 2), m2 = p.getPointAtLength(L / 2 + 1);
        const ang = Math.atan2(m2.y - m.y, m2.x - m.x) * 180 / Math.PI;
        el("path", { d: `M${a} 0L${-a} ${-a * 0.75}L${-a} ${a * 0.75}Z`, class: "arrow",
                     transform: `translate(${m.x} ${m.y}) rotate(${ang})` }, gArrows);
      });
    }

    const n = inst.nodes.length;
    const showLabels = opts.labels === true || (opts.labels === "auto" && n <= 30);
    if (opts.weights && inst.links.length <= 40) {
      inst.links.forEach((l, i) => {
        const p = paths[i], L = p.getTotalLength(), m = p.getPointAtLength(L / 2), m2 = p.getPointAtLength(L / 2 + 1);
        const dx = m2.x - m.x, dy = m2.y - m.y, len = Math.hypot(dx, dy) || 1;
        const t = el("text", { x: m.x - dy / len * 11, y: m.y + dx / len * 11 + 4, class: "weight", "text-anchor": "middle" }, gText);
        t.textContent = l.w;
      });
    }
    const deg = new Map();
    inst.links.forEach(l => { deg.set(l.u, (deg.get(l.u) || 0) + 1); deg.set(l.v, (deg.get(l.v) || 0) + 1); });
    const r = n > 1500 ? 0 : n > 400 ? 1.6 : n > 100 ? 2.6 : 5;
    if (r > 0) {
      inst.nodes.forEach(nd => {
        const [x, y] = P(nd.id);
        el("circle", { cx: x, cy: y, r, class: "node" + (opts.odd && deg.get(nd.id) % 2 ? " odd" : "") }, gNodes);
        if (showLabels) {
          const t = el("text", { x: x + r + 3, y: y - r - 2, class: "label" }, gText);
          t.textContent = nd.label;
        }
      });
    }
    const postman = el("circle", { r: big ? 4 : 7, class: "postman", visibility: "hidden" }, svg);

    // ---------------------------------------------------------------- tour animation
    let steps = [], count = [], i = 0, frac = 0, playing = false, raf = 0, last = 0, speed = 1;
    let onProgress = () => {}, onEnd = () => {};
    const pxPerSec = () => 140 * speed * (big ? 4 : 1);

    function paint(li) {
      const c = count[li], p = paths[li], b = +p.dataset.base;
      p.classList.toggle("done", c === 1);
      p.classList.toggle("twice", c >= 2);
      p.setAttribute("stroke-width", c ? Math.max(b * 1.9, 3) : b);
    }
    function setResult(res) {
      stop();
      count = inst.links.map(() => 0);
      paths.forEach((_, li) => paint(li));
      steps = [];
      const used = inst.links.map(() => 0);
      const c = res.circuit;
      for (let k = 0; k + 1 < c.length; k++) {
        const a = c[k], b = c[k + 1];
        const key = a < b ? `${a}|${b}` : `${b}|${a}`;
        const cand = (pairs.get(key) || []).filter(li => { const l = inst.links[li]; return !l.oneway || l.u === a; });
        if (!cand.length) continue;
        cand.sort((x, y) => used[x] - used[y] || inst.links[x].w - inst.links[y].w);
        const li = cand[0];
        used[li]++;
        steps.push({ li, fwd: inst.links[li].u === a });
      }
      i = 0; frac = 0;
      postman.setAttribute("visibility", steps.length ? "visible" : "hidden");
      place();
      onProgress(0, steps.length);
    }
    function place() {
      if (!steps.length) return;
      const st = steps[Math.min(i, steps.length - 1)];
      const p = paths[st.li], L = p.getTotalLength();
      const f = i >= steps.length ? 1 : frac;
      const pt = p.getPointAtLength((st.fwd ? f : 1 - f) * L);
      postman.setAttribute("cx", pt.x); postman.setAttribute("cy", pt.y);
    }
    function tick(t) {
      if (!playing) return;
      const dt = last ? (t - last) / 1000 : 0; last = t;
      let budget = dt * pxPerSec();
      while (budget > 0 && i < steps.length) {
        const st = steps[i], L = Math.max(paths[st.li].getTotalLength(), 6);
        const left = (1 - frac) * L;
        if (budget >= left) {
          budget -= left; count[st.li]++; paint(st.li); i++; frac = 0;
        } else { frac += budget / L; budget = 0; }
      }
      place();
      onProgress(i, steps.length);
      if (i >= steps.length) { playing = false; onEnd(); return; }
      raf = requestAnimationFrame(tick);
    }
    function play() {
      if (!steps.length) return;
      if (i >= steps.length) reset();
      playing = true; last = 0; raf = requestAnimationFrame(tick);
    }
    function stop() { playing = false; cancelAnimationFrame(raf); }
    function reset() {
      stop(); i = 0; frac = 0; count = inst.links.map(() => 0);
      paths.forEach((_, li) => paint(li)); place(); onProgress(0, steps.length);
    }
    function finish() {
      stop();
      count = inst.links.map(() => 0);
      steps.forEach(st => count[st.li]++);
      paths.forEach((_, li) => paint(li));
      i = steps.length; frac = 0; place(); onProgress(i, steps.length);
    }
    return {
      setResult, play, pause: stop, reset, finish,
      isPlaying: () => playing,
      setSpeed: v => { speed = v; },
      onProgress: f => { onProgress = f; },
      onEnd: f => { onEnd = f; },
    };
  }

  window.Postman = { draw };
})();
