// Checks the JavaScript solver against optima computed by the Python package.
//   python3 tests/js/make_cases.py && node tests/js/test_cpp.mjs
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(import.meta.url);
const CPP = require("../../site/assets/cpp.js");
const cases = JSON.parse(fs.readFileSync(new URL("./cases.json", import.meta.url)));

function checkTour(inst, r) {
  const c = r.circuit;
  if (c[0] !== c[c.length - 1]) return "tour not closed";
  const allowed = new Map(), need = new Map();
  for (const l of inst.links) {
    for (const [a, b] of l.oneway ? [[l.u, l.v]] : [[l.u, l.v], [l.v, l.u]]) {
      const k = a + "|" + b; allowed.set(k, Math.min(l.w, allowed.has(k) ? allowed.get(k) : Infinity));
    }
    const key = l.oneway ? `${l.u}>${l.v}` : [l.u, l.v].sort().join("-");
    need.set(key, (need.get(key) || 0) + 1);
  }
  let cost = 0;
  const seen = new Map();
  for (let i = 0; i + 1 < c.length; i++) {
    const a = c[i], b = c[i + 1], k = a + "|" + b;
    if (!allowed.has(k)) return `illegal move ${a}->${b}`;
    cost += allowed.get(k);
    for (const key of [`${a}>${b}`, [a, b].sort().join("-")]) seen.set(key, (seen.get(key) || 0) + 1);
  }
  for (const [k, n] of need) if ((seen.get(k) || 0) < n) return `street ${k} not covered`;
  if (Math.abs(cost - r.total) > 1e-6) return `tour length ${cost} != reported ${r.total}`;
  return null;
}

let fail = 0;
const gaps = [];
const t0 = Date.now();
for (const c of cases) {
  let r;
  try { r = CPP.solve(c.inst, { maxSeconds: 4 }); } catch (e) { console.log("ERROR", c.inst.name, e.message); fail++; continue; }
  const err = checkTour(c.inst, r);
  if (err) { console.log("BAD TOUR", c.inst.name, err); fail++; continue; }
  if (r.kind !== c.kind) { console.log("KIND", c.inst.name, r.kind, c.kind); fail++; continue; }
  if (c.kind === "mixed") {
    if (r.lower_bound > c.opt + 1e-9) { console.log("BOUND ABOVE OPTIMUM", c.inst.name, r.lower_bound, c.opt); fail++; }
    if (r.total < c.opt - 1e-9) { console.log("BELOW OPTIMUM?!", c.inst.name, r.total, c.opt); fail++; }
    if (r.optimal && r.total !== c.opt) { console.log("FALSE OPTIMALITY CLAIM", c.inst.name); fail++; }
    gaps.push(100 * (r.total - c.opt) / c.opt);
  } else if (r.total !== c.opt) { console.log("NOT OPTIMAL", c.inst.name, r.total, c.opt); fail++; }
}
const und = cases.filter(c => c.kind !== "mixed").length;
gaps.sort((a, b) => a - b);
const mean = gaps.reduce((s, x) => s + x, 0) / Math.max(1, gaps.length);
console.log(`${cases.length} cases (${und} undirected/directed exact, ${gaps.length} mixed) in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
console.log(`mixed heuristic gap to optimum: mean ${mean.toFixed(2)}%, median ${gaps[gaps.length >> 1]?.toFixed(2)}%, max ${gaps[gaps.length - 1]?.toFixed(2)}%, optimal in ${gaps.filter(g => g < 1e-9).length}`);
console.log(fail ? `${fail} FAILURES` : "all checks passed");
process.exit(fail ? 1 : 0);
