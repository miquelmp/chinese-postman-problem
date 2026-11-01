// Checks the JavaScript network builders: node tests/js/test_networks.mjs
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(import.meta.url);
const CPP = require("../../site/assets/cpp.js");
globalThis.CPP = CPP;
const NW = require("../../site/assets/networks.js");

let fail = 0;
const check = (cond, msg) => { if (!cond) { console.log("FAIL", msg); fail++; } };

for (const [name, size, share] of [["example1997"], ["konigsberg"], ["petersen"], ["grid", 12], ["grid", 40],
                                    ["delaunay", 200], ["delaunay", 2500], ["oneway-grid", 15], ["mixed-town", 12, 0.6],
                                    ["mixed-town", 25, 1.0]]) {
  for (const seed of [0, 1]) {
    const t = Date.now();
    const inst = NW.example(name, size, share, seed);
    const r = CPP.solve(inst, { maxSeconds: 3 });
    check(r.circuit.length - 1 >= inst.links.length, `${name} tour too short`);
    check(r.total >= r.original, `${name} total`);
    if (seed === 0) console.log(`${inst.name.padEnd(34)} ${String(inst.nodes.length).padStart(5)} junctions ${String(inst.links.length).padStart(5)} streets  ${r.kind.padEnd(10)} total ${r.total}  ${r.optimal ? "optimal" : "gap " + r.gap_pct + "%"}  ${Date.now() - t} ms`);
  }
}
check(CPP.solve(NW.example("example1997")).total === 63, "1997 example optimum 63");
check(CPP.solve(NW.example("konigsberg")).total === 9, "Königsberg 9 crossings");
check(CPP.solve(NW.example("petersen")).total === 20, "Petersen 20");

const gra = fs.readFileSync(new URL("../../examples/example_1997.gra", import.meta.url), "utf8");
check(CPP.solve(NW.fromGra(gra, "example")).total === 63, ".GRA parsing");
let threw = false; try { NW.fromGra("hello world", "x"); } catch (e) { threw = /not a valid/.test(e.message); }
check(threw, "invalid .GRA reported");
const carp = fs.readFileSync(new URL("../../data/carp/gdb1.dat", import.meta.url), "utf8");
check(CPP.solve(NW.fromCarp(carp, "gdb1")).total === 294, "gdb1 optimum 294, as computed in Python");

// same synthetic Overpass answer as tests/test_web.py
const nodes = [], ways = [], grid = {};
let nid = 1;
for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) { grid[`${r},${c}`] = nid; nodes.push({ type: "node", id: nid++, lat: 41.22 + r * 0.001, lon: 1.72 + c * 0.0013 }); }
nodes.push({ type: "node", id: 99, lat: 41.2205, lon: 1.72065 });
let wid = 1000;
for (let r = 0; r < 3; r++) {
  let seq = [grid[`${r},0`], grid[`${r},1`], grid[`${r},2`]];
  if (r === 0) seq = [grid["0,0"], 99, grid["0,1"], grid["0,2"]];
  ways.push({ type: "way", id: wid++, nodes: seq, tags: r === 1 ? { highway: "residential", oneway: "yes" } : { highway: "residential" } });
}
for (let c = 0; c < 3; c++) ways.push({ type: "way", id: wid++, nodes: [grid[`0,${c}`], grid[`1,${c}`], grid[`2,${c}`]], tags: { highway: "residential" } });
const osm = NW.fromOsm({ elements: nodes.concat(ways) }, "sample");
check(osm.nodes.length === 9, `OSM junctions ${osm.nodes.length} (expected 9)`);
check(osm.links.length === 12, `OSM streets ${osm.links.length} (expected 12)`);
check(osm.links.filter(l => l.oneway).length === 2, "OSM one-way streets");
const ro = CPP.solve(osm);
check(ro.kind === "mixed" && ro.circuit.length > 12, "OSM network solves");
check(NW.overpassQuery(41.2, 1.7, 41.21, 1.71).includes("(41.2,1.7,41.21,1.71)"), "Overpass query box");

console.log(fail ? `${fail} FAILURES` : "all network checks passed");
process.exit(fail ? 1 : 0);
