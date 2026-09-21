import numpy as np
import pytest

pytest.importorskip("allel")
pytest.importorskip("blosc2")
pytest.importorskip("numba")

from benchmarks.explore_genotypes import Store, make_data


@pytest.mark.parametrize("backend", ["numpy", "allel-packed", "tightarray", "blosc2"])
def test_diploid_order_partial_missing_and_query(backend):
    data = np.array(
        [[[0, 1], [1, 0], [-1, 0]], [[1, -1], [-1, -1], [1, 1]]], dtype=np.int8
    )
    store = Store(data, backend)
    np.testing.assert_array_equal(store.region(0, 2), data)
    np.testing.assert_array_equal(store.region(1, 1), data[1:])
    expected = [[1, 3, 2], [3, 0, 3]]
    np.testing.assert_array_equal(store.query(0, 2), expected)
    if backend in ("numpy", "tightarray"):
        np.testing.assert_array_equal(store.query(0, 2, True), expected)
    if backend != "blosc2":
        assert store.nbytes <= data.nbytes


@pytest.mark.parametrize("distribution", ["common", "rare"])
def test_generated_roundtrip(distribution):
    data = make_data(65, 7, distribution)
    assert set(np.unique(data)) <= {-1, 0, 1}
    store = Store(data, "tightarray")
    np.testing.assert_array_equal(store.region(3, 61), data[3:64])
    np.testing.assert_array_equal(
        store.query(3, 61, True), Store(data, "numpy").query(3, 61)
    )


def test_multiallelic_rejected():
    with pytest.raises(ValueError, match="biallelic"):
        Store(np.array([[[0, 2]]], dtype=np.int8), "tightarray")
