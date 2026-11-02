// Checks the JavaScript extensions against optima computed in Python:
//   python3 tests/js/make_ext_cases.py && node tests/js/test_extensions.mjs
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(import.meta.url);
const CPP = require("../../site/assets/cpp.js");
globalThis.CPP = CPP;
const EXT = require("../../site/assets/extensions.js");
const NW = require("../../site/assets/networks.js");
const cases = JSON.parse(fs.readFileSync(new URL("./ext_cases.json", import.meta.url)));

let fail = 0;
const bad = (...a) => { console.log(...a); fail++; };

function checkRoute(inst, circuit, depot) {
  if (circuit[0] !== depot || circuit[circuit.length - 1] !== depot) return "route does not start and end at the depot";
  const w = new Map();
  for (const l of inst.links) for (const k of [`${l.u}|${l.v}`, `${l.v}|${l.u}`]) w.set(k, Math.min(l.w, w.has(k) ? w.get(k) : Infinity));
  let cost = 0;
  for (let i = 0; i + 1 < circuit.length; i++) {
    const k = `${circuit[i]}|${circuit[i + 1]}`;
    if (!w.has(k)) return `no street ${k}`;
    cost += w.get(k);
  }
  return cost;
}

function covered(inst, circuits) {
  const need = new Map(), seen = new Map();
  for (const l of inst.links) if (l.req !== false) { const k = [l.u, l.v].sort().join("-"); need.set(k, (need.get(k) || 0) + 1); }
  for (const c of circuits) for (let i = 0; i + 1 < c.length; i++) { const k = [c[i], c[i + 1]].sort().join("-"); seen.set(k, (seen.get(k) || 0) + 1); }
  for (const [k, n] of need) if ((seen.get(k) || 0) < n) return k;
  return null;
}

const gaps = [];
for (const c of cases.rural) {
  const r = EXT.rural(c.inst, { depot: c.depot, maxSeconds: 2 });
  const cost = checkRoute(c.inst, r.circuit, c.depot);
  if (typeof cost === "string") { bad("BAD ROUTE", c.inst.name, cost); continue; }
  if (cost > r.total + 1e-6) bad("ROUTE LONGER THAN REPORTED", c.inst.name, cost, r.total);
  const miss = covered(c.inst, [r.circuit]);
  if (miss) bad("NOT SERVED", c.inst.name, miss);
  if (r.total < c.opt - 1e-6) bad("BELOW OPTIMUM", c.inst.name, r.total, c.opt);
  if (r.lower_bound > c.opt + 1e-6) bad("BOUND ABOVE OPTIMUM", c.inst.name, r.lower_bound, c.opt);
  if (r.optimal && Math.abs(r.total - c.opt) > 1e-6) bad("FALSE OPTIMALITY CLAIM", c.inst.name);
  if (r.frederickson > 1.5 * c.opt + 1e-6) bad("FREDERICKSON ABOVE 3/2", c.inst.name);
  gaps.push(100 * (r.total - c.opt) / c.opt);
}
const kg = [];
for (const c of cases.postmen) {
  const r = EXT.postmen(c.inst, c.k, { depot: c.depot, maxSeconds: 1 });
  for (const rt of r.routes) {
    const cost = checkRoute(c.inst, rt.circuit, c.depot);
    if (typeof cost === "string") bad("BAD ROUTE", c.inst.name, cost);
    else if (cost > rt.cost + 1e-6) bad("ROUTE LONGER THAN REPORTED", c.inst.name);
  }
  const miss = covered(c.inst, r.routes.map(x => x.circuit));
  if (miss) bad("NOT SERVED", c.inst.name, miss);
  if (r.longest < c.opt - 1e-6) bad("BELOW OPTIMUM", c.inst.name, c.k, r.longest, c.opt);
  if (r.lower_bound > c.opt + 1e-6) bad("BOUND ABOVE OPTIMUM", c.inst.name, c.k, r.lower_bound, c.opt);
  kg.push(100 * (r.longest - c.opt) / c.opt);
}
// a large network: must finish and serve everything
const town = NW.example("delaunay", 800, 0, 2);
const big = EXT.postmen(town, 4, { maxSeconds: 3 });
if (covered(town, big.routes.map(x => x.circuit))) bad("big town not served");
const st = s => { s.sort((a, b) => a - b); return `mean ${(s.reduce((a, b) => a + b, 0) / s.length).toFixed(2)}%, max ${s[s.length - 1].toFixed(2)}%, optimal in ${s.filter(g => g < 1e-6).length} of ${s.length}`; };
console.log(`rural postman: ${st(gaps)}`);
console.log(`k postmen:     ${st(kg)}`);
console.log(`800-junction town, 4 postmen: longest ${big.longest}, bound ${big.lower_bound}, gap ${big.gap_pct}% in ${big.seconds}s`);
console.log(fail ? `${fail} FAILURES` : "all extension checks passed");
process.exit(fail ? 1 : 0);
