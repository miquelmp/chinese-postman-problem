// Checks the JavaScript blossom matching against NetworkX on 3,000 random cost matrices.
//   python3 tests/js/make_matchings.py && node tests/js/test_matching.mjs
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(import.meta.url);
const CPP = require("../../site/assets/cpp.js");
const optima = JSON.parse(fs.readFileSync(new URL("./matchings.json", import.meta.url)));

function matrix(k) {                     // same generator as make_matchings.py
  let x = k + 1;
  const t = 2 * (1 + k % 12), top = k % 2 ? 20 : 1000, D = new Float64Array(t * t);
  for (let i = 0; i < t; i++) for (let j = i + 1; j < t; j++) {
    x = x * 16807 % 2147483647;
    x = x * 16807 % 2147483647;
    D[i * t + j] = D[j * t + i] = 1 + x % top;
  }
  return [t, D];
}

let fail = 0;
optima.forEach((best, k) => {
  const [t, D] = matrix(k);
  const mate = CPP.minWeightPerfectMatching(D, t);
  let cost = 0, perfect = true;
  for (let i = 0; i < t; i++) {
    if (mate[i] < 0 || mate[mate[i]] !== i) perfect = false;
    else if (i < mate[i]) cost += D[i * t + mate[i]];
  }
  if (!perfect || cost !== best) { console.log(`FAIL case ${k}: ${cost} != ${best}`); fail++; }
});
console.log(`${optima.length} matchings, ${fail} disagreements`);
process.exit(fail ? 1 : 0);
