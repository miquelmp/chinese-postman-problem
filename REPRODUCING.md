# Reproducing the results

Every result file is in `results/`. Run the commands from the repository root, after
`pip install -e ".[test]"`. `requirements-lock.txt` lists the versions of the latest results, and
`results/environment.json` the machine. Times depend on the machine; optima do not.

| Report | Result file | Command | Needs |
| --- | --- | --- | --- |
| 7.2 Classic graphs | `classic.csv` | `python3 experiments.py classic` | |
| 7.3 Benchmark networks | `benchmarks.csv` | `python3 experiments.py benchmarks` | |
| 7.3 Bound for fleets | `cpp_bound.csv` | `python3 experiments.py cpp_bound` | |
| 7.4 Scaling, NetworkX | `scaling.csv` | `python3 experiments.py scaling` | |
| 7.4 Scaling, LEMON | `scaling_lemon.csv` | `bash native/build_lemon.sh`, then `python3 experiments.py scaling_fast` | C++ compiler; 7 GB of RAM |
| 10.6 Windy postman, Win on all instances | `windy_win.csv` | `sh tools/fetch_wpp.sh`, then `python3 experiments.py wpp_win` | minutes |
| 10.7 Rural postman on every network | `rural_general.csv` | Instances in `data/wrpp`, `data/mrpp` and `data/drpp` (see below), then `python3 experiments.py rural_general` | hours |
| 10.7 Several postmen, every network | `k_general.csv` | Same instances, then `python3 experiments.py k_general` | hours |
| 10.7 Rural postman, mixed, longer limit | `rural_mixed_long.csv` | Same instances, then `python3 experiments.py rural_mixed_long` | an hour |
| 10.7 Several postmen, published optima | `k_published.csv` | Instances in `data/mmwrpp` (see below), then `python3 experiments.py k_published` | about an hour |
| 10.6 Windy postman, combined method | `windy_published.csv` | `python3 experiments.py wpp` | over 2 hours; it resumes if stopped |
| 10.6 Published values | `wpp_published_values.csv` | Copied from `WPP.txt` on the instance page of Corberán et al. | — |
| 10.7 Published values, mixed rural | `mrpp_published_values.csv` | Copied from `MRPP.txt` on the instance page of Corberán et al. | — |
| 9.4 Real street networks | `mixed_osm.csv` | `python3 experiments.py osm` | minutes |
| 7.4 Repeated timing | `timing_repeats.csv` | `bash native/build_lemon.sh`, then `python3 experiments.py timing`, alone on the machine | about 75 minutes |
| 7.4 Certificates | `certificates.csv` | `python3 tools/certify_matching.py` | Node.js; 7 GB of RAM |
| 7.5 Directed networks | `directed.csv` | `python3 experiments.py directed` | |
| 8.3 Branch-and-bound | `bnb.csv` | `python3 experiments.py bnb` | |
| 9.3 Local search | `local_search.csv` | `python3 experiments.py local_search` | after `mixed` |
| 9.4 Mixed benchmarks and towns | `mixed_benchmarks.csv`, `mixed_city.csv` | `python3 experiments.py mixed` | hours |
| 9.4 Published mixed instances, sample | `mixed_published.csv` | `sh tools/fetch_mcpp.sh`, then `python3 experiments.py mcpp` | hours |
| 9.4 Published mixed instances, full set of 500 and 1,000 junctions | `mixed_crossed.csv` | the same download, then `python3 experiments.py mcpp_crossed` | about an hour |
| 9.4 Published values | `mcpp_published_values.csv` | Copied from `MCPP.txt` on the instance page of Corberán et al. | — |
| 10.3 Rural postman | `rural_benchmarks.csv`, `rural_towns.csv` | `python3 experiments.py rural` | |
| 10.4 Several postmen | `fleet_small.csv`, `fleet_benchmarks.csv` | `python3 experiments.py fleet_small fleet_benchmarks` | hours |
| 10.5 Capacitated fleets | `carp.csv` | `python3 experiments.py carp` | |


`python3 experiments.py` with no argument runs the quick families. `mixed_towns` and `mcpp` resume if
interrupted: delete their result file to start again.

Results from the same code and seeds give the same optima. The heuristics of chapter 10 stop on a
time limit, so their costs can change slightly with the speed of the machine.

## Instances of section 10.7

They are not stored here, and uv.es may refuse scripts, so they are downloaded by hand.

- `data/wrpp`, `data/mrpp` and `data/mmwrpp`: the WRPP, MRPP and MM K-WRPP data files at
  [uv.es/corberan/instancias.htm](https://www.uv.es/corberan/instancias.htm), unzipped. Only the `P...` files
  of the MM K-WRPP archive go into `data/mmwrpp`.
- `data/drpp`: `test_instances/DRPP_Instances_Campos` of
  [OAR Lib](https://github.com/Olibear/ArcRoutingLibrary).

The published values are in `results/wrpp_published_values.csv` and `results/mmwrpp_published_values.csv`.
