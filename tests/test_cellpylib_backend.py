import numpy as np
import pytest

cpl = pytest.importorskip("cellpylib")
pytest.importorskip("numba")
from examples.cellpylib_backend import evolve2d


@pytest.mark.parametrize("shape", [(1, 1), (2, 3), (7, 11), (16, 16)])
@pytest.mark.parametrize("dtype", [np.uint8, np.int32])
@pytest.mark.parametrize("backend", ["dense", "packed"])
def test_full_history(shape, dtype, backend):
    initial = np.random.default_rng(11).integers(0, 2, (2, *shape), dtype=dtype)
    before = initial.copy()
    expected = cpl.evolve2d(initial, 8, cpl.game_of_life_rule)
    actual = evolve2d(initial, 8, cpl.game_of_life_rule, backend=backend)
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(initial, before)
    assert actual.dtype == expected.dtype
    np.testing.assert_array_equal(evolve2d(initial, 1, cpl.game_of_life_rule), initial)


def test_fallback():
    initial = np.zeros((1, 4, 4), dtype=np.uint8)

    def rule(n, c, t):
        return (c[0] + t) % 2

    np.testing.assert_array_equal(
        evolve2d(initial, 4, rule), cpl.evolve2d(initial, 4, rule)
    )


@pytest.mark.parametrize("backend", ["dense", "packed"])
def test_upstream_demo(backend):
    # Public demos/game_of_life_demo.py fixture, upstream Apache-2.0.
    a = cpl.init_simple2d(60, 60)
    a[:, [28, 29, 30, 30], [30, 31, 29, 31]] = 1
    a[:, [40, 40, 40], [15, 16, 17]] = 1
    a[:, [18, 18, 19, 20, 21, 21, 21, 21, 20], [45, 48, 44, 44, 44, 45, 46, 47, 48]] = 1
    expected = cpl.evolve2d(a, 60, cpl.game_of_life_rule, memoize="recursive")
    actual = evolve2d(
        a, 60, cpl.game_of_life_rule, memoize="recursive", backend=backend
    )
    np.testing.assert_array_equal(actual, expected)
    assert actual.dtype == expected.dtype
