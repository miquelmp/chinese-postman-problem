// Solve one matching for tools/certify_matching.py: node match_sparse.mjs in.json out.json
// in.json: {"edges": [[i, j, weight], ...]}. out.json: mate, vertex duals, blossoms.
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(import.meta.url);
const CPP = require("../site/assets/cpp.js");
const [input, output] = process.argv.slice(2);
const { edges } = JSON.parse(fs.readFileSync(input));
const dual = {};
const mate = CPP.maxWeightMatching(edges, true, dual);
fs.writeFileSync(output, JSON.stringify({ mate: Array.from(mate), vertex: dual.vertex, blossoms: dual.blossoms }));
