import numpy as np
import pytest

cpl = pytest.importorskip("cellpylib")
pytest.importorskip("numba")
from examples.cellpylib_multistate import RULES, rule_callback, simulate


@pytest.mark.parametrize("states", [4, 8, 16, 32])
@pytest.mark.parametrize("rule", RULES)
def test_real_cellpylib(states, rule):
    a = np.random.default_rng(321).integers(0, states, (7, 11), dtype=np.uint8)
    expected = cpl.evolve2d(a[None], 5, rule_callback(rule, states))
    before = a.copy()
    for backend in ("numpy", "dense", "packed", "word-aligned"):
        actual = simulate(a, 4, states, rule, backend, full_history=True)
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(
            simulate(a, 4, states, rule, backend), expected[-1]
        )
        np.testing.assert_array_equal(simulate(a, 0, states, rule, backend), a)
    np.testing.assert_array_equal(a, before)


@pytest.mark.parametrize("shape", [(1, 1), (2, 3), (3, 65)])
def test_boundaries(shape):
    a = np.random.default_rng(8).integers(0, 32, shape, dtype=np.uint8)
    for rule in RULES:
        expected = cpl.evolve2d(a[None], 4, rule_callback(rule, 32))[-1]
        for backend in ("dense", "packed", "word-aligned"):
            np.testing.assert_array_equal(simulate(a, 3, 32, rule, backend), expected)
