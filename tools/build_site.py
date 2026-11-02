"""Build the static website into docs/ (served by GitHub Pages).

    pip install markdown          # only needed to build the site
    python3 tools/build_site.py --repo https://github.com/miquelmp/chinese-postman-problem

Inputs:  site/ (page templates, CSS, JS), report/ (2026 report as Markdown and PDF),
         the 1997 PDF, results/*.csv, data/carp/*.dat and the chinese_postman package itself.
Output:  docs/ — static files only; the solver runs in the browser through Pyodide.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import shutil
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE, DOCS = ROOT / "site", ROOT / "docs"
sys.path.insert(0, str(ROOT))

PDF_1997 = ROOT / "report" / "monserrat-1997-chinese-postman.pdf"
PDF_2026 = ROOT / "report" / "chinese-postman-2026.pdf"
MD_2026 = ROOT / "report" / "report-2026.md"

NAV = [("try", "try/", "Solve a network"), ("extensions", "extensions/", "Extensions"),
       ("report", "report/", "2026 report"), ("1997", "1997/", "1997 report"), ("code", "{REPO}", "Code")]


# ------------------------------------------------------------------ page chrome
def head(prefix):
    return (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Overpass:wght@400;600;700;800'
        '&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap">\n'
        f'<link rel="stylesheet" href="{prefix}assets/site.css">\n'
        f'<link rel="icon" href="{prefix}assets/favicon.svg" type="image/svg+xml">'
    )


def header(prefix, current, repo):
    links = []
    for key, href, text in NAV:
        url = repo if href == "{REPO}" else prefix + href
        cur = ' aria-current="page"' if key == current else ""
        links.append(f'<a href="{url}"{cur}>{text}</a>')
    return (f'<header class="site-header"><div class="inner">'
            f'<a class="brand" href="{prefix or "./"}">The Chinese Postman</a>'
            f'<nav class="site-nav" aria-label="Main">{"".join(links)}</nav></div></header>')


def footer(repo):
    return (
        '<footer class="site-footer"><div class="inner">'
        '<p>Miquel Monserrat Pons. Final-year project, ETSEIB (Universitat Politècnica de Catalunya), 1997; '
        'revised 2026.</p>'
        f'<p>Code under the MIT licence; texts and figures under CC BY 4.0. <a href="{repo}">Source on GitHub</a>.</p>'
        '<p>Benchmark instances from the arc-routing literature, as collected in CARPData.jl (MIT). '
        'Street data © OpenStreetMap contributors (ODbL). The in-browser solver is written in JavaScript; the optional '
        'exact proof runs Python through Pyodide, with NetworkX and SciPy (HiGHS).</p>'
        '</div></footer>'
    )


def render(text, prefix, repo):
    text = text.replace("{{HEAD}}", head(prefix)).replace("{{FOOTER}}", footer(repo))
    text = text.replace("{{REPO}}", repo)
    return re.sub(r"\{\{HEADER:(\w+)\}\}", lambda m: header(prefix, m.group(1), repo), text)


# ------------------------------------------------------------------ charts (inline SVG)
def _rows(name):
    with open(ROOT / "results" / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def chart_scaling():
    nx_rows = [r for r in _rows("scaling.csv")]
    bv_rows = [r for r in _rows("scaling_blossom5.csv")]
    W, H, x0, x1, y0, y1 = 760, 400, 70, 730, 60, 330
    lx = math.log10
    X = lambda o: x0 + (lx(o) - lx(30)) / (lx(20000) - lx(30)) * (x1 - x0)
    Y = lambda s: y1 - (lx(s) + 2) / (lx(300) + 2) * (y1 - y0)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="With Blossom V, two minutes covers 12,000 odd junctions instead of 800">',
           '<text x="0" y="22" font-size="17" font-weight="800" fill="var(--ink)">With Blossom V, two minutes now covers 12,000 odd junctions instead of 800</text>']
    for t in (0.01, 0.1, 1, 10, 100):
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="var(--rule)"/>'
                   f'<text x="{x0 - 8}" y="{Y(t) + 4:.1f}" text-anchor="end" font-size="12" fill="var(--ink-soft)">{t:g} s</text>')
    for t in (30, 100, 300, 1000, 3000, 10000):
        out.append(f'<text x="{X(t):.1f}" y="{y1 + 20}" text-anchor="middle" font-size="12" fill="var(--ink-soft)">{t:,}</text>')
    out.append(f'<line x1="{x0}" x2="{x1}" y1="{y1}" y2="{y1}" stroke="var(--ink)"/>')
    out.append(f'<text x="{(x0 + x1) / 2}" y="{y1 + 44}" text-anchor="middle" font-size="12" fill="var(--ink-soft)">odd junctions to pair</text>')
    out.append(f'<line x1="{x0}" x2="{x1}" y1="{Y(120):.1f}" y2="{Y(120):.1f}" stroke="var(--street)" stroke-dasharray="4 4"/>'
               f'<text x="{x0 + 6}" y="{Y(120) - 6:.1f}" font-size="12" fill="var(--ink-soft)">two minutes</text>')

    def series(rows, fam, color, dash):
        pts = sorted(((int(r["odd"]), float(r["seconds"]), int(r["vertices"])) for r in rows
                      if r["family"].endswith(fam)), key=lambda p: p[0])
        d = "".join(f'{"M" if i == 0 else "L"}{X(o):.1f} {Y(s):.1f}' for i, (o, s, _) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.5" stroke-dasharray="{dash}"/>')
        for o, s, n in pts:
            out.append(f'<circle cx="{X(o):.1f}" cy="{Y(s):.1f}" r="4" fill="{color}"><title>{n:,} junctions, {o:,} odd: {s:.2f} s</title></circle>')
        return pts[-1]

    a = series(nx_rows, "manhattan", "var(--street)", "none")
    b = series(nx_rows, "delaunay", "var(--street)", "6 4")
    c = series(bv_rows, "manhattan", "var(--ink)", "none")
    series(bv_rows, "delaunay", "var(--ink)", "6 4")
    nxe = max([a, b], key=lambda p: p[0])
    out.append(f'<text x="{X(nxe[0]) - 10:.1f}" y="{Y(nxe[1]) - 12:.1f}" text-anchor="end" font-size="13" fill="var(--ink-soft)">Pure Python: {nxe[0]:,} odd, {nxe[1]:.0f} s</text>')
    out.append(f'<text x="{X(c[0]) - 10:.1f}" y="{Y(c[1]) - 14:.1f}" text-anchor="end" font-size="13" font-weight="700" fill="var(--ink)">Blossom V: {c[0]:,} odd, {c[1]:.0f} s</text>')
    out.append(f'<text x="{x1}" y="{y1 - 10}" text-anchor="end" font-size="12" fill="var(--ink-soft)">solid: grid cities; dashed: organic towns</text>')
    out.append("</svg>")
    return "\n".join(out)


def chart_carp():
    rows = [r for r in _rows("benchmarks.csv") if r["all_required"] == "True"]
    rows.sort(key=lambda r: float(r["cpp_over_carp_ub_pct"]))
    vals = [float(r["cpp_over_carp_ub_pct"]) for r in rows]
    med = statistics.median(vals)
    W, H, x0, x1, y0, y1 = 760, 360, 60, 730, 60, 310
    X = lambda i: x0 + i * (x1 - x0) / (len(rows) - 1)
    Y = lambda v: y1 - (v - 60) / 40 * (y1 - y0)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="A single postman tour costs a median {med:.1f}% of the best known fleet solution">',
           f'<text x="0" y="22" font-size="17" font-weight="800" fill="var(--ink)">One postman costs a median {med:.1f}% of the best known fleet solution</text>']
    for t in (60, 70, 80, 90, 100):
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="var(--rule)"/>'
                   f'<text x="{x0 - 8}" y="{Y(t) + 4:.1f}" text-anchor="end" font-size="12" fill="var(--ink-soft)">{t}%</text>')
    out.append(f'<line x1="{x0}" x2="{x1}" y1="{Y(100):.1f}" y2="{Y(100):.1f}" stroke="var(--ink)"/>'
               f'<text x="{x0}" y="{Y(100) - 8:.1f}" font-size="12" fill="var(--ink-soft)">100% = best known solution with several vehicles</text>')
    out.append(f'<line x1="{x0}" x2="{x1}" y1="{Y(med):.1f}" y2="{Y(med):.1f}" stroke="var(--street)" stroke-dasharray="4 4"/>'
               f'<text x="{x0}" y="{Y(med) + 16:.1f}" font-size="12" fill="var(--ink-soft)">median {med:.1f}%</text>')
    for i, r in enumerate(rows):
        v = float(r["cpp_over_carp_ub_pct"])
        out.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="5" fill="var(--route)" stroke="var(--ink)" stroke-width="1">'
                   f'<title>{html.escape(r["instance"])}: {v}% with {r["vehicles"]} vehicles</title></circle>')
    lo = rows[0]
    out.append(f'<text x="{X(0) + 10:.1f}" y="{Y(float(lo["cpp_over_carp_ub_pct"])) + 4:.1f}" font-size="12" fill="var(--ink-soft)">'
               f'{lo["instance"]}, {lo["vehicles"]} vehicles: {lo["cpp_over_carp_ub_pct"]}%</text>')
    n100 = sum(v >= 100 for v in vals)
    out.append(f'<text x="{x1}" y="{Y(100) - 8:.1f}" text-anchor="end" font-size="12" fill="var(--ink)">{n100} networks at 100%: capacity adds nothing</text>')
    out.append(f'<text x="{(x0 + x1) / 2}" y="{H - 8}" text-anchor="middle" font-size="12" fill="var(--ink-soft)">{len(rows)} networks, sorted</text>')
    out.append("</svg>")
    return "\n".join(out)


# ------------------------------------------------------------------ extensions page
def _pct(x):
    return f"{x:.2f}%".replace(".00%", "%") if x >= 0.005 else "0%"


def ext_stats():
    """Numbers quoted on the extensions page, from the result files."""
    f = lambda r, k: float(r[k])
    out = {}
    mixed = _rows("mixed_city.csv") + _rows("mixed_benchmarks.csv")
    g = [f(r, "heur_gap_pct") for r in mixed if r["exact_optimal"] == "True"]
    out["MIXED_MEAN"] = _pct(statistics.mean(g))
    out["MIXED_GAP"] = f"Heuristic: mean {_pct(statistics.mean(g))}, worst {_pct(max(g))} ({len(g)} networks solved exactly)"
    rb, rt = _rows("rural_benchmarks.csv"), _rows("rural_towns.csv")
    one = sum(r["pieces"] == "1" for r in rb)
    proved = [r for r in rb + rt if r["optimal"] == "True"]
    multi = [r for r in proved if r["pieces"] != "1"]
    fg = [100 * (f(r, "frederickson") - f(r, "best")) / f(r, "best") for r in multi]
    hg = [100 * (f(r, "heuristic") - f(r, "best")) / f(r, "best") for r in multi]
    open_ = [r for r in rt if r["optimal"] != "True"]
    bg = [f(r, "bound_gap_pct") for r in open_]
    tmax = max(f(r, "seconds") for r in proved if r["pieces"] != "1")
    out["RURAL_EXACT"] = (f"proved on all {len(rb)} benchmark networks and {sum(r['optimal'] == 'True' for r in rt)} "
                          f"of {len(rt)} synthetic towns within two minutes")
    out["RURAL_GAP"] = (f"Frederickson: mean {_pct(statistics.mean(fg))}, worst {_pct(max(fg))}; "
                        f"after local search: mean {_pct(statistics.mean(hg))}, worst {_pct(max(hg))}")
    out["RURAL_TEXT"] = (
        f"Of the {len(rb)} benchmark networks whose files mark only some streets for service, {one} have their "
        f"streets to serve in a single piece and are solved exactly by matching, in at most "
        f"{max(f(r, 'seconds') for r in rb if r['pieces'] == '1'):.0f} seconds; branch-and-cut "
        f"proves the other {len(rb) - one} in at most {max(f(r, 'seconds') for r in rb):.0f} seconds. On {len(rt)} synthetic "
        f"grid towns with 20% or 50% of the streets to serve, branch-and-cut proves {sum(r['optimal'] == 'True' for r in rt)} "
        f"within two minutes, the largest with {max(int(r['required']) for r in rt if r['optimal'] == 'True')} streets to serve. "
        f"Over the {len(multi)} networks with several pieces and a proven optimum, Frederickson's heuristic alone is a mean "
        f"{_pct(statistics.mean(fg))} above the optimum (worst {_pct(max(fg))}, well inside its guarantee of 50%), and the local "
        f"search brings this to {_pct(statistics.mean(hg))} (worst {_pct(max(hg))}). "
        + (f"On the {len(open_)} largest towns, with up to {max(int(r['required']) for r in open_)} streets to serve, the "
           f"optimum is not proved in two minutes, but the best route is within {_pct(max(bg))} of the lower bound."
           if open_ else ""))
    if not all((ROOT / "results" / n).exists() for n in ("fleet_small.csv", "fleet_benchmarks.csv", "carp.csv")):
        for k in ("K_GAP", "K_TEXT", "CARP_GAP", "CARP_TEXT"):
            out[k] = "(results pending)"
        return out
    ks = _rows("fleet_small.csv")
    sg = [f(r, "split_gap_pct") for r in ks]
    hk = [f(r, "heuristic_gap_pct") for r in ks]
    ratio = max(f(r, "split_ratio") for r in ks)
    bgap = [100 * (f(r, "optimum") - f(r, "lower_bound")) / f(r, "lower_bound") for r in ks]
    kb = [r for r in _rows("fleet_benchmarks.csv") if int(r["k"]) <= 10]
    kg = [f(r, "gap_pct") for r in kb]
    out["K_GAP"] = (f"Small networks, against the exact optimum: split alone mean {_pct(statistics.mean(sg))}, "
                    f"after local search mean {_pct(statistics.mean(hk))}, worst {_pct(max(hk))}")
    out["K_TEXT"] = (
        f"On {len(ks)} small networks where branch-and-cut finds the exact optimum (two or three postmen), the best cut of "
        f"one tour is a mean {_pct(statistics.mean(sg))} above it, and never more than {100 * (ratio - 1):.0f}% (the guarantee "
        f"allows 50% to 67%); after the local search the routes are optimal in {sum(h < 0.005 for h in hk)} cases, and a mean "
        f"{_pct(statistics.mean(hk))} above the optimum (worst {_pct(max(hk))}). On {len(set(r['instance'] for r in kb))} benchmark networks "
        f"with 2 to 10 postmen the exact optimum is out of reach, and only the bound is available: the longest route is within a "
        f"median {_pct(statistics.median(kg))} of it (worst {_pct(max(kg))}). Much of that distance is the bound's: on the small "
        f"networks, where the optimum is known, the same bound is up to {max(bgap):.0f}% below it.")
    cp = _rows("carp.csv")
    cg = [f(r, "gap_to_best_known_pct") for r in cp]
    out["CARP_GAP"] = (f"Against the best known solutions: median {_pct(statistics.median(cg))}, "
                       f"mean {_pct(statistics.mean(cg))}, worst {_pct(max(cg))}")
    out["CARP_TEXT"] = (
        f"On the {len(cp)} classical CARP instances, this simple method is a median {_pct(statistics.median(cg))} above the best "
        f"solutions published (mean {_pct(statistics.mean(cg))}; it matches the best known on {sum(c <= 0.005 for c in cg)}). "
        f"The best published solutions come from decades of dedicated metaheuristics and exact methods; the point here is how "
        f"far the 1997 tour already goes when it is simply cut into vehicle loads.")
    return out


# ------------------------------------------------------------------ 2026 report
def build_report(repo):
    import markdown
    md = MD_2026.read_text(encoding="utf-8")
    md = re.sub(r"^Nov 1, 2026 · @\w+\s*$", "Miquel Monserrat Pons · November 2026", md, flags=re.M)

    maths = []

    def keep_math(m):
        maths.append(m.group(1).strip())
        return f"\n\nMATHBLOCK{len(maths) - 1}\n\n"
    md = re.sub(r"```latex\n(.*?)```", keep_math, md, flags=re.S)
    md = md.replace("\\_", "_")
    charts = {"results/benchmarks.csv": chart_carp(), "results/scaling.csv": chart_scaling()}

    def keep_chart(m):
        for key, svg in charts.items():
            if key in m.group(0):
                return f'\n\n<figure class="chart">{svg}<figcaption>{html.escape(m.group(1).replace(chr(92), ""))}</figcaption></figure>\n\n'
        return ""
    md = re.sub(r"&#91;embedded content: (.*?)\\?\]", keep_chart, md)
    body = markdown.markdown(md, extensions=["tables", "fenced_code", "toc", "sane_lists"],
                             extension_configs={"toc": {"permalink": False}})
    for i, m in enumerate(maths):
        body = body.replace(f"<p>MATHBLOCK{i}</p>", f'<div class="math-display">{html.escape(m)}</div>')
    body = body.replace("<table>", '<div class="table-scroll"><table>').replace("</table>", "</table></div>")
    body = re.sub(r'<p>Miquel Monserrat Pons · November 2026</p>',
                  '<p class="byline">Miquel Monserrat Pons · November 2026</p>', body)
    toc = "\n".join(f'      <li><a href="#{a}">{re.sub("<.*?>", "", t)}</a></li>'
                    for a, t in re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', body))
    tpl = (SITE / "report" / "template.html").read_text(encoding="utf-8")
    return tpl.replace("{{TOC}}", toc).replace("{{BODY}}", body)


# ------------------------------------------------------------------ build
def build(repo):
    from chinese_postman import web
    DOCS.mkdir(exist_ok=True)
    for item in DOCS.iterdir():          # docs/pyodide is vendored once, not rebuilt
        if item.name == "pyodide":
            continue
        shutil.rmtree(item) if item.is_dir() else item.unlink()
    shutil.copytree(SITE / "assets", DOCS / "assets")
    (DOCS / ".nojekyll").write_text("")

    # home
    inst = web.example("example1997")
    res = web.solve(inst)
    page = (SITE / "index.html").read_text(encoding="utf-8")
    page = page.replace("{{HERO_INSTANCE}}", json.dumps(inst)).replace("{{HERO_RESULT}}",
                                                                         json.dumps({"circuit": res["circuit"]}))
    page = page.replace("{{CHART_SCALING}}", chart_scaling()).replace("{{CHART_CARP}}", chart_carp())
    (DOCS / "index.html").write_text(render(page, "", repo), encoding="utf-8")

    # try
    T = DOCS / "try"
    (T / "py" / "chinese_postman").mkdir(parents=True)
    files = []
    for f in sorted((ROOT / "chinese_postman").glob("*.py")):
        if f.name == "fast.py":          # native backend: not usable in the browser
            continue
        shutil.copy(f, T / "py" / "chinese_postman" / f.name)
        files.append(f.name)
    (T / "py" / "manifest.json").write_text(json.dumps({"files": files}))
    for name in ("app.js", "worker.js", "solver-worker.js"):
        shutil.copy(SITE / "try" / name, T / name)
    (T / "index.html").write_text(render((SITE / "try" / "index.html").read_text(encoding="utf-8"), "../", repo),
                                  encoding="utf-8")
    (T / "data" / "carp").mkdir(parents=True)
    bench = []
    for r in _rows("benchmarks.csv"):
        shutil.copy(ROOT / "data" / "carp" / f"{r['instance']}.dat", T / "data" / "carp")
        bench.append({"name": r["instance"], "vertices": int(r["vertices"]), "edges": int(r["edges"])})
    bench.sort(key=lambda b: (re.sub(r"\d.*", "", b["name"]), b["vertices"]))
    (T / "data" / "benchmarks.json").write_text(json.dumps(bench))

    # extensions
    (DOCS / "extensions").mkdir()
    page = (SITE / "extensions" / "index.html").read_text(encoding="utf-8")
    for k, v in ext_stats().items():
        page = page.replace("{{" + k + "}}", v)
    (DOCS / "extensions" / "index.html").write_text(render(page, "../", repo), encoding="utf-8")
    for k, v in ext_stats().items():
        print(f"{k}: {v}")

    # reports
    (DOCS / "1997").mkdir()
    shutil.copy(PDF_1997, DOCS / "1997" / PDF_1997.name)
    (DOCS / "1997" / "index.html").write_text(render((SITE / "1997" / "index.html").read_text(encoding="utf-8"),
                                                     "../", repo), encoding="utf-8")
    (DOCS / "report").mkdir()
    shutil.copy(PDF_2026, DOCS / "report" / PDF_2026.name)
    (DOCS / "report" / "index.html").write_text(render(build_report(repo), "../", repo), encoding="utf-8")
    if not (DOCS / "pyodide" / "pyodide.js").exists():
        print("Note: docs/pyodide is missing; run tools/fetch_pyodide.sh, or the site will use the CDN.")
    print(f"Built {sum(1 for _ in DOCS.rglob('*') if _.is_file())} files into {DOCS}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="https://github.com/miquelmp/chinese-postman-problem",
                    help="URL of the GitHub repository, used in links")
    build(ap.parse_args().repo)
