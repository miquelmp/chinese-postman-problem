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
| 7.4 Certificates | `certificates.csv` | `python3 tools/certify_matching.py` | Node.js; 7 GB of RAM |
| 7.5 Directed networks | `directed.csv` | `python3 experiments.py directed` | |
| 8.3 Branch-and-bound | `bnb.csv` | `python3 experiments.py bnb` | |
| 9.3 Local search | `local_search.csv` | `python3 experiments.py local_search` | after `mixed` |
| 9.4 Mixed benchmarks and towns | `mixed_benchmarks.csv`, `mixed_city.csv` | `python3 experiments.py mixed` | hours |
| 9.4 Published mixed instances | `mixed_published.csv` | `sh tools/fetch_mcpp.sh`, then `python3 experiments.py mcpp` | hours |
| 10.3 Rural postman | `rural_benchmarks.csv`, `rural_towns.csv` | `python3 experiments.py rural` | |
| 10.4 Several postmen | `fleet_small.csv`, `fleet_benchmarks.csv` | `python3 experiments.py fleet_small fleet_benchmarks` | hours |
| 10.5 Capacitated fleets | `carp.csv` | `python3 experiments.py carp` | |


`python3 experiments.py` with no argument runs the quick families. `mixed_towns` and `mcpp` resume if
interrupted: delete their result file to start again.

Results from the same code and seeds give the same optima. The heuristics of chapter 10 stop on a
time limit, so their costs can change slightly with the speed of the machine.
