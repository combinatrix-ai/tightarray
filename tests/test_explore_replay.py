import numpy as np
import pytest

pytest.importorskip("blosc2")
from benchmarks.explore_replay import BACKENDS, ReplayStorage, observations


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("states", [8, 32])
@pytest.mark.parametrize("structured", [False, True])
def test_sample_exact(backend, states, structured):
    data = observations(11, 13, states, structured)
    storage = ReplayStorage(data, states, backend)
    indices = np.array([10, 0, 5, 5, 1])
    np.testing.assert_array_equal(storage.sample(indices), data[indices])
    assert storage.sample(np.array([], dtype=np.int64)).shape == (0, 13, 13)
    sampled = storage.sample(indices)
    sampled[:] = 255
    np.testing.assert_array_equal(storage.sample(indices), data[indices])
    if backend == "packed":
        assert storage.payload_bytes == 11 * (
            ((13 * 13 * (states - 1).bit_length() + 63) // 64) * 8
        )
    with pytest.raises(IndexError):
        storage.sample(np.array([-1]))
    with pytest.raises(IndexError):
        storage.sample(np.array([11]))


def test_validation():
    with pytest.raises(ValueError):
        ReplayStorage(np.full((2, 3, 3), 8, dtype=np.uint8), 8, "packed")
