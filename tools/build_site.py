"""Build the static website into docs/ (served by GitHub Pages).

    pip install markdown          # only needed to build the site
    python3 tools/build_site.py --repo https://github.com/miquelmp/chinese-postman-problem

Inputs:  site/ (page templates, CSS, JS), report/ (2026 report as Markdown and PDF),
         the 1997 PDF, results/*.csv, data/carp/*.dat and the cartero package itself.
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

NAV = [("try", "try/", "Solve a network"), ("report", "report/", "2026 report"),
       ("1997", "1997/", "1997 report"), ("code", "{REPO}", "Code")]


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
    from cartero import web
    DOCS.mkdir(exist_ok=True)
    for item in DOCS.iterdir():          # docs/pyodide is vendored once, not rebuilt
        if item.name == "pyodide":
            continue
        shutil.rmtree(item) if item.is_dir() else item.unlink()
    shutil.copytree(SITE / "assets", DOCS / "assets")
    (DOCS / ".nojekyll").write_text("")

    # home
    inst = web.example("pfc1997")
    res = web.solve(inst)
    page = (SITE / "index.html").read_text(encoding="utf-8")
    page = page.replace("{{HERO_INSTANCE}}", json.dumps(inst)).replace("{{HERO_RESULT}}",
                                                                         json.dumps({"circuit": res["circuit"]}))
    page = page.replace("{{CHART_SCALING}}", chart_scaling()).replace("{{CHART_CARP}}", chart_carp())
    (DOCS / "index.html").write_text(render(page, "", repo), encoding="utf-8")

    # try
    T = DOCS / "try"
    (T / "py" / "cartero").mkdir(parents=True)
    files = []
    for f in sorted((ROOT / "cartero").glob("*.py")):
        if f.name == "fast.py":          # native backend: not usable in the browser
            continue
        shutil.copy(f, T / "py" / "cartero" / f.name)
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
