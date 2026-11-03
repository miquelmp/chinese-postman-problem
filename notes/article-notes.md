# Notes for a possible article

Working notes, not part of the report or the website. Checked on 3 November 2026.

## Related tools

The report's section 6.8 covers OAR Lib, `postman_problems` and Route Crafter. An article could add
a line on the practical tools below. None was run; each was read on its own page or repository.

| Tool | What it is | Method | One-way streets | Proves the optimum? |
| --- | --- | --- | --- | --- |
| [Run Every Street](https://solipsia.github.io/RunEveryStreet/) | Website, GPX output | Random search: many routes, keeps the shortest | Not stated | No |
| [rkistner/chinese-postman](https://github.com/rkistner/chinese-postman) | QGIS plugin, MIT | Blossom matching, exact on the undirected case | No, bidirectional graph | Undirected case only, implicitly |
| [Wandrer](https://news.wandrer.earth/2026/04/02/chinese-postman-routing.html) | Paid service for cyclists | Not stated | Not stated | No, it says so itself |
| [Antwerp Postman Optimizer](https://rvanbruggen.github.io/ChinesePostman) | Website for postal rounds, with a right-turn mode | Not stated | Not stated | Says "optimal", without verification |
| [Missing Mapillary GraphHopper Routing](https://github.com/vizsim/missing_mapillary_gh-routing), [fork](https://github.com/atchisson/street_view_routing) | A-to-B routes that favour streets without imagery | GraphHopper | Through GraphHopper | Not a CPP tool |
| [Valhalla CPP](https://pretalx.com/fossgis2022/talk/EU8RPG/) | Prototype presented in 2022 | Directed case | Yes, all directed | Not stated |
| [everystreet](https://github.com/matejker/everystreet) | Python project with a website | Edmonds and Johnson | Ignored | Undirected case only |
| [MetricGate](https://metricgate.com/docs/chinese-postman-problem/) | Explanation and calculator | Edmonds and Johnson | Undirected only | Undirected case only |

## Still to do for an article

- Compare with independent implementations on the same machine, such as Blossom V and OAR Lib.
- Add a statement that the author reviewed the results and takes responsibility for the content, if
  the journal asks for one.
- Choose the journal. JOSS asks for more than six months of public history. SoftwareX has a limit of
  4,000 words, a template and a `src/` layout.
- Enable the repository on Zenodo first, then create the git tag and the release.
- Decide how a PyPI package distributes LEMON, and check that the package name is free.
- A full mathematical audit has not been done.
