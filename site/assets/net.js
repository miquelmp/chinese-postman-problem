/* Draws a street network as SVG and animates a postman tour over it.
   Instance: {nodes:[{id,x,y,label}], links:[{u,v,w,oneway}]}
   Result:   {circuit:[node ids]}
   Streets turn yellow on the pass that serves them and red on any other pass.
   Several postmen: {routes:[{circuit, links}]} - every postman walks at the same speed and the
   streets he serves take his colour. */
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
    // A street's cost, or for a windy street its cost each way, with arrows as drawn on screen
    const costText = l => {
      if (l.w2 === undefined || l.w2 === l.w) return `${l.w}`;
      const [x1, y1] = P(l.u), [x2, y2] = P(l.v), dx = x2 - x1, dy = y2 - y1;
      const [go, back] = Math.abs(dx) >= Math.abs(dy) ? (dx >= 0 ? ["→", "←"] : ["←", "→"]) : (dy >= 0 ? ["↓", "↑"] : ["↑", "↓"]);
      return `${go} ${l.w}  ${back} ${l.w2}`;
    };
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
        const p = el("path", { d, class: "street" + (l.oneway ? " oneway" : "") + (l.req === false ? " optional" : ""),
                               "stroke-width": l.req === false ? streetW * 0.6 : streetW }, gStreets);
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
    const labelAt = i => {
      const p = paths[i], L = p.getTotalLength(), m = p.getPointAtLength(L / 2), m2 = p.getPointAtLength(L / 2 + 1);
      const dx = m2.x - m.x, dy = m2.y - m.y, len = Math.hypot(dx, dy) || 1;
      const along = Math.abs(dx) / len;
      if (along < 0.5) {                 // beside a steep street, on the side with room
        const right = m.x + 6 + costText(inst.links[i]).length * 6 <= W;
        return { L, x: right ? m.x + 6 : m.x - 6, y: m.y + 4, along, anchor: right ? "start" : "end" };
      }
      return { L, x: m.x - dy / len * 11, y: m.y + dx / len * 11 + 4, along, anchor: "middle" };
    };
    // "auto": label every street only if every label fits on its street and clear of the others
    const allFit = () => {
      if (inst.links.length > 300) return false;
      const boxes = inst.links.map((l, i) => {
        const q = labelAt(i), w = costText(l).length * 6;
        return { x: q.anchor === "start" ? q.x + w / 2 : q.anchor === "end" ? q.x - w / 2 : q.x, y: q.y, w, fits: q.along < 0.5 || w <= q.L - 4 };
      });
      if (boxes.some(b => !b.fits)) return false;
      return boxes.every((a, i) => boxes.every((b, j) => j <= i ||
        Math.abs(a.x - b.x) > (a.w + b.w) / 2 + 2 || Math.abs(a.y - b.y) > 13));
    };
    const showCosts = opts.weights === "auto" ? allFit() : opts.weights && inst.links.length <= 40;
    if (showCosts) {
      inst.links.forEach((l, i) => {
        const { x, y, anchor } = labelAt(i);
        const t = el("text", { x, y, class: "weight", "text-anchor": anchor }, gText);
        t.textContent = costText(l);
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
    if (opts.depot !== undefined && nodes.has(opts.depot)) {
      const [x, y] = P(opts.depot), q = big ? 6 : 9;
      el("rect", { x: x - q, y: y - q, width: 2 * q, height: 2 * q, class: "depot" }, svg);
    }
    // Resting the pointer on a street shows its cost. Wide invisible strokes make streets easy to hit.
    if (opts.weights === "auto") {
      const gHit = el("g", {}, svg), tip = el("g", { class: "tip", visibility: "hidden" }, svg);
      const box = el("rect", { rx: 4 }, tip), text = el("text", {}, tip);
      const show = (ev, i) => {
        const scale = W / (svg.getBoundingClientRect().width || W), size = 13 * scale;
        const pt = new DOMPoint(ev.clientX, ev.clientY).matrixTransform(svg.getScreenCTM().inverse());
        text.textContent = `${costText(inst.links[i])}${inst.units ? " " + inst.units : ""}`;
        text.setAttribute("font-size", size);
        const b = text.getBBox(), m = 5 * scale;
        const x = Math.min(Math.max(pt.x - b.width / 2, m), W - b.width - m), y = Math.max(pt.y - 14 * scale, b.height + m);
        text.setAttribute("x", x); text.setAttribute("y", y);
        const c = text.getBBox();
        box.setAttribute("x", c.x - m); box.setAttribute("y", c.y - m / 2);
        box.setAttribute("width", c.width + 2 * m); box.setAttribute("height", c.height + m);
        tip.setAttribute("visibility", "visible");
      };
      paths.forEach((p, i) => {
        const h = el("path", { d: p.getAttribute("d"), class: "hit" }, gHit);
        h.addEventListener("pointerover", ev => show(ev, i));
        h.addEventListener("pointermove", ev => show(ev, i));
        h.addEventListener("pointerout", () => tip.setAttribute("visibility", "hidden"));
        if (opts.onStreet) { h.classList.add("pickable"); h.addEventListener("click", () => opts.onStreet(i)); }
      });
    }

    const postman = el("circle", { r: big ? 4 : 7, class: "postman", visibility: "hidden" }, svg);
    let crew = [];                       // one dot per postman in several-postmen mode

    // ---------------------------------------------------------------- tour animation
    let steps = [], count = [], i = 0, frac = 0, playing = false, raf = 0, last = 0, speed = 1;
    let onProgress = () => {}, onEnd = () => {};
    const pxPerSec = () => 140 * speed * (big ? 4 : 1);

    const PALETTE = ["#f2b705", "#2f6690", "#3a9d5d", "#8e5bbf", "#e07a1f", "#1b998b", "#c8102e", "#6b4f2a"];
    let multi = null;                    // several postmen: [{steps, i, frac, color, serves:Set, dot}]
    function paint(li) {
      const p = paths[li], b = +p.dataset.base;
      if (multi) {
        const col = owner[li];
        p.style.stroke = col || "";
        p.setAttribute("stroke-width", col ? Math.max(b * 1.9, 3) : b);
        return;
      }
      const c = count[li], opt = inst.links[li].req === false;
      p.classList.toggle("done", c === 1 && !opt);
      p.classList.toggle("twice", c >= 2 || (c === 1 && opt));
      p.setAttribute("stroke-width", c ? Math.max((opt ? b / 0.6 : b) * 1.9, 3) : b);
    }
    let owner = [];
    function stepsOf(c) {
      const out = [], used = inst.links.map(() => 0);
      for (let k = 0; k + 1 < c.length; k++) {
        const a = c[k], b = c[k + 1];
        const key = a < b ? `${a}|${b}` : `${b}|${a}`;
        const cand = (pairs.get(key) || []).filter(li => { const l = inst.links[li]; return !l.oneway || l.u === a; });
        if (!cand.length) continue;
        cand.sort((x, y) => used[x] - used[y] || inst.links[x].w - inst.links[y].w);
        const li = cand[0];
        used[li]++;
        out.push({ li, fwd: inst.links[li].u === a });
      }
      return out;
    }
    function setResult(res) {
      stop();
      crew.forEach(d => d.remove()); crew = [];
      paths.forEach(p => { p.style.stroke = ""; });
      count = inst.links.map(() => 0);
      owner = inst.links.map(() => null);
      if (res.routes) {
        multi = res.routes.map((r, k) => {
          const color = PALETTE[k % PALETTE.length];
          const dot = el("circle", { r: big ? 4 : 6, class: "postman crew", fill: color, visibility: "visible" }, svg);
          crew.push(dot);
          return { steps: stepsOf(r.circuit), i: 0, frac: 0, color, serves: new Set(r.links || []), dot };
        });
        steps = [].concat(...multi.map(m => m.steps));
        postman.setAttribute("visibility", "hidden");
      } else {
        multi = null;
        steps = stepsOf(res.circuit);
        postman.setAttribute("visibility", steps.length ? "visible" : "hidden");
      }
      paths.forEach((_, li) => paint(li));
      i = 0; frac = 0;
      place();
      onProgress(0, steps.length);
    }
    function colorOf(k) { return PALETTE[k % PALETTE.length]; }
    function placeDot(m) {
      if (!m.steps.length) { const [x, y] = P(opts.depot); m.dot.setAttribute("cx", x); m.dot.setAttribute("cy", y); return; }
      const st = m.steps[Math.min(m.i, m.steps.length - 1)];
      const p = paths[st.li], L = p.getTotalLength();
      const f = m.i >= m.steps.length ? 1 : m.frac;
      const pt = p.getPointAtLength((st.fwd ? f : 1 - f) * L);
      m.dot.setAttribute("cx", pt.x); m.dot.setAttribute("cy", pt.y);
    }
    function place() {
      if (multi) { multi.forEach(placeDot); return; }
      if (!steps.length) return;
      const st = steps[Math.min(i, steps.length - 1)];
      const p = paths[st.li], L = p.getTotalLength();
      const f = i >= steps.length ? 1 : frac;
      const pt = p.getPointAtLength((st.fwd ? f : 1 - f) * L);
      postman.setAttribute("cx", pt.x); postman.setAttribute("cy", pt.y);
    }
    function walked() { return multi ? multi.reduce((a, m) => a + Math.min(m.i, m.steps.length), 0) : i; }
    function tickMulti(dt) {
      let running = false;
      for (const m of multi) {
        let budget = dt * pxPerSec();
        while (budget > 0 && m.i < m.steps.length) {
          const st = m.steps[m.i], L = Math.max(paths[st.li].getTotalLength(), 6), left = (1 - m.frac) * L;
          if (budget >= left) {
            budget -= left;
            if (m.serves.has(st.li) && !owner[st.li]) { owner[st.li] = m.color; paint(st.li); }
            m.i++; m.frac = 0;
          } else { m.frac += budget / L; budget = 0; }
        }
        if (m.i < m.steps.length) running = true;
      }
      return running;
    }
    function tick(t) {
      if (!playing) return;
      const dt = last ? (t - last) / 1000 : 0; last = t;
      if (multi) {
        const running = tickMulti(dt);
        place(); onProgress(walked(), steps.length);
        if (!running) { playing = false; onEnd(); return; }
        raf = requestAnimationFrame(tick); return;
      }
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
      if (walked() >= steps.length) reset();
      playing = true; last = 0; raf = requestAnimationFrame(tick);
    }
    function stop() { playing = false; cancelAnimationFrame(raf); }
    function reset() {
      stop(); i = 0; frac = 0; count = inst.links.map(() => 0); owner = inst.links.map(() => null);
      if (multi) multi.forEach(m => { m.i = 0; m.frac = 0; });
      paths.forEach((_, li) => paint(li)); place(); onProgress(0, steps.length);
    }
    function finish() {
      stop();
      count = inst.links.map(() => 0);
      if (multi) {
        owner = inst.links.map(() => null);
        multi.forEach(m => { m.steps.forEach(st => { if (m.serves.has(st.li) && !owner[st.li]) owner[st.li] = m.color; }); m.i = m.steps.length; m.frac = 0; });
      } else steps.forEach(st => count[st.li]++);
      paths.forEach((_, li) => paint(li));
      i = steps.length; frac = 0; place(); onProgress(steps.length, steps.length);
    }
    return {
      costsShown: !!showCosts,
      setResult, play, pause: stop, reset, finish, colorOf,
      isPlaying: () => playing,
      setSpeed: v => { speed = v; },
      onProgress: f => { onProgress = f; },
      onEnd: f => { onEnd = f; },
    };
  }

  window.Postman = { draw };
})();
