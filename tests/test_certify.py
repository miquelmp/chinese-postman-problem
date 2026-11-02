"""The dual certificate of tools/certify_matching.py, and the reader of published instances."""
import importlib.util
import itertools
import random
import shutil
from pathlib import Path

import numpy as np
import pytest

from chinese_postman.mixed import read_mcpp, solve_exact
from chinese_postman.cpp import min_weight_pairing

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("certify_matching", ROOT / "tools" / "certify_matching.py")
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")


def matrix(t, seed):
    rnd = random.Random(seed)
    D = np.zeros((t, t), dtype=np.int32)
    for i, j in itertools.combinations(range(t), 2):
        D[i, j] = D[j, i] = rnd.randint(1, 60)
    return D


def test_small_certificate_by_hand():
    D = np.array([[0, 2], [2, 0]], dtype=np.int32)      # C = 3, w = 1, u = 1/2 each
    assert cm.check(D, [1, 0], np.array([1.0, 1.0]), []) == 2


def test_rejects_a_dual_that_is_too_low():
    D = np.array([[0, 2], [2, 0]], dtype=np.int32)
    with pytest.raises(ValueError):
        cm.check(D, [1, 0], np.array([0.0, 0.0]), [])


def test_rejects_an_imperfect_matching():
    D = np.array([[0, 2], [2, 0]], dtype=np.int32)
    with pytest.raises(ValueError):
        cm.check(D, [-1, -1], np.array([1.0, 1.0]), [])


@needs_node
@pytest.mark.parametrize("seed", range(10))
def test_certified_cost_is_the_blossom_optimum(seed):
    t = 2 * (3 + seed)
    D = matrix(t, seed)
    mate, u, blossoms, *_ = cm.solve(D, k=3)
    best = sum(int(D[p]) for p in min_weight_pairing(list(range(t)), {(i, j): D[i, j] for i in range(t) for j in range(t)}))
    assert cm.check(D, mate, u, blossoms) == best


@needs_node
def test_a_worse_matching_fails_the_certificate():
    D = matrix(8, 3)
    mate, u, blossoms, *_ = cm.solve(D, k=3)
    a, b = 0, int(mate[0])
    c = next(x for x in range(8) if x not in (a, b))
    d = int(mate[c])
    worse = list(mate)
    worse[a], worse[c], worse[b], worse[d] = c, a, d, b
    if sum(int(D[i, worse[i]]) for i in range(8)) != sum(int(D[i, mate[i]]) for i in range(8)):
        with pytest.raises(ValueError):
            cm.check(D, worse, u, blossoms)


def test_read_mcpp(tmp_path):
    text = """NOMBRE : T
VERTICES : 3
LISTA_ARISTAS_REQ :
(   1,   2)   coste        5 99999999
(   2,   3)   coste        4 99999999
(   1,   3)   coste        3        3
"""
    path = tmp_path / "T"
    path.write_text(text, encoding="latin-1")
    M = read_mcpp(str(path))
    assert sorted(M.links) == [(1, 2, 5, True), (1, 3, 3, False), (2, 3, 4, True)]
    assert solve_exact(M).optimal


def test_read_mcpp_rejects_windy_costs(tmp_path):
    path = tmp_path / "T"
    path.write_text("(1, 2) coste 5 6\n", encoding="latin-1")
    with pytest.raises(ValueError):
        read_mcpp(str(path))
