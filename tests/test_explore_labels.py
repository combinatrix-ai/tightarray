import numpy as np
import pytest

pytest.importorskip("blosc2")
pytest.importorskip("numba")
from benchmarks.explore_labels import Store, volume


@pytest.mark.parametrize("states", [8, 32])
@pytest.mark.parametrize("structured", [False, True])
@pytest.mark.parametrize(
    "backend", ["numpy-numba", "tightarray", "blosc-lz4", "blosc-zstd"]
)
def test_patches(states, structured, backend):
    data = volume(35, states, structured)
    store = Store(data, states, backend)
    for width in (1, 7, 16, 35):
        origins = np.array(
            [[0, 0, 0], [35 - width] * 3, [1 if width < 35 else 0] * 3], dtype=np.int64
        )
        expected = Store(data, states, "numpy").sample(origins, width)
        np.testing.assert_array_equal(store.sample(origins, width), expected)
    if backend == "tightarray":
        assert (
            store.storage_bytes <= (data.size * (states - 1).bit_length() + 7) // 8 + 7
        )
    with pytest.raises(ValueError):
        store.sample(np.array([[34, 34, 34]]), 2)
