# Contributing

Questions, bug reports and improvements are welcome.

## Reporting a problem

Open an [issue](https://github.com/miquelmp/chinese-postman-problem/issues). For a wrong result, include
the network (a `.GRA` file or the code that builds it), the call you made, what you expected and your
versions of Python, NetworkX and SciPy.

## Getting help

Use the issues for questions too. The [API reference](https://miquelmp.github.io/chinese-postman-problem/api/)
and the [2026 report](https://miquelmp.github.io/chinese-postman-problem/report/) describe the methods.

## Changing the code

```bash
git clone https://github.com/miquelmp/chinese-postman-problem
cd chinese-postman-problem
pip install -e ".[test]"
pytest -q
node tests/js/test_cpp.mjs && node tests/js/test_networks.mjs
node tests/js/test_extensions.mjs && node tests/js/test_matching.mjs
```

Please work on a branch and open a pull request. Continuous integration must pass.

- A new method needs a test against an exact result, such as brute force on small networks.
- If you change a solver in `chinese_postman/`, check whether its JavaScript twin in `site/assets/` needs the same change.
- If you change a result, regenerate its file in `results/` as described in `REPRODUCING.md`, and update the report.
- `docs/` is generated: edit `site/` and `report/`, then run `tools/build_site.py`.

Files in `native/lemon_src` are LEMON sources, documented in the `README.md` there. Do not edit them, and do not add Blossom V, whose licence forbids redistribution.

By contributing you agree that your code is released under the MIT licence, and your texts under
CC BY 4.0. Please follow the [code of conduct](CODE_OF_CONDUCT.md).
