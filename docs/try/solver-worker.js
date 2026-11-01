/* Runs the JavaScript solver off the main thread, so the page stays responsive. */
importScripts("../assets/cpp.js", "../assets/networks.js");

self.onmessage = e => {
  const { id, cmd, args } = e.data;
  try {
    let out;
    if (cmd === "example") out = Networks.example(args.name, args.size, args.share, args.seed);
    else if (cmd === "gra") out = Networks.fromGra(args.text, args.name);
    else if (cmd === "carp") out = Networks.fromCarp(args.text, args.name);
    else if (cmd === "osm") out = Networks.fromOsm(args.text, args.name);
    else if (cmd === "query") out = Networks.overpassQuery(args.s, args.w, args.n, args.e);
    else if (cmd === "solve") out = CPP.solve(args.inst, { maxSeconds: args.maxSeconds || 4 });
    else throw new Error("Unknown command " + cmd);
    self.postMessage({ id, ok: true, out });
  } catch (err) {
    self.postMessage({ id, ok: false, error: String(err && err.message ? err.message : err) });
  }
};
