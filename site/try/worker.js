/* Runs Python (Pyodide) and the cartero solver off the main thread. */
let pyodide = null;

function lastLine(err) {
  const msg = String(err && err.message ? err.message : err).trim().split("\n");
  for (let k = msg.length - 1; k >= 0; k--) {
    const m = msg[k].match(/^\w*(Error|Exception)\w*: (.*)$/);
    if (m) return m[2];
  }
  return msg[msg.length - 1];
}

async function init(indexURL) {
  importScripts(indexURL + "pyodide.js");
  pyodide = await loadPyodide({ indexURL });
  await pyodide.loadPackage(["numpy", "scipy"]);
  // NetworkX alone: its declared extras (Matplotlib, Pillow…) are not needed by the solver
  const lock = await (await fetch(indexURL + "pyodide-lock.json")).json();
  await pyodide.loadPackage(indexURL + lock.packages.networkx.file_name);
  const manifest = await (await fetch("py/manifest.json")).json();
  pyodide.FS.mkdirTree("/home/pyodide/cartero");
  for (const f of manifest.files) {
    const text = await (await fetch("py/cartero/" + f)).text();
    pyodide.FS.writeFile("/home/pyodide/cartero/" + f, text);
  }
  pyodide.runPython(`
import sys, json
sys.path.insert(0, "/home/pyodide")
from cartero import web

def example_json(name, size, oneway, seed):
    return json.dumps(web.example(name, size=int(size), oneway=float(oneway), seed=int(seed)))

def gra_json(text, name):
    return json.dumps(web.from_gra(text, name))

def carp_json(text, name):
    return json.dumps(web.from_carp_text(text, name))

def osm_json(text, name):
    return json.dumps(web.from_osm(text, name))

def query(s, w, n, e):
    return web.overpass_query(s, w, n, e)
`);
}

const call = (fn, ...args) => pyodide.globals.get(fn)(...args);

self.onmessage = async (e) => {
  const { id, cmd, args } = e.data;
  try {
    let out = null;
    if (cmd === "init") await init(args.indexURL);
    else if (cmd === "example") out = call("example_json", args.name, args.size, args.oneway, args.seed);
    else if (cmd === "gra") out = call("gra_json", args.text, args.name);
    else if (cmd === "carp") out = call("carp_json", args.text, args.name);
    else if (cmd === "osm") out = call("osm_json", args.text, args.name);
    else if (cmd === "query") out = call("query", args.s, args.w, args.n, args.e);
    else if (cmd === "solve") out = pyodide.globals.get("web").solve_json(args.inst, args.timeLimit, args.gapTol);
    else throw new Error("Unknown command " + cmd);
    self.postMessage({ id, ok: true, out });
  } catch (err) {
    self.postMessage({ id, ok: false, error: lastLine(err) });
  }
};
