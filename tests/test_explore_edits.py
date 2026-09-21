import numpy as np
import pytest

pytest.importorskip("blosc2")
pytest.importorskip("numba")
from benchmarks.explore_edits import build, edit


@pytest.mark.parametrize("states", [8, 32])
@pytest.mark.parametrize("backend", ["numpy", "packed", "lz4", "zstd"])
def test_online_edits(states, backend):
    source = np.random.default_rng(4).integers(0, states, 65536, dtype=np.uint8)
    indices = np.array([0, 7, 7, 63, 64, 8191, 8192, 65535], dtype=np.int64)
    expected = source.copy()
    data = build(source, backend, states)
    for _ in range(3):
        assert edit(data, indices, states) == edit(expected, indices, states)
    actual = (
        np.frombuffer(data.tobytes(), dtype=np.uint8)
        if backend == "packed"
        else np.asarray(data[:])
    )
    np.testing.assert_array_equal(actual, expected)


def test_compiled_matches_online():
    from benchmarks.explore_edits import compiled_edit

    a = np.arange(256, dtype=np.uint8) % 8
    b = a.copy()
    indices = np.array([0, 7, 7, 63, 64, 255], dtype=np.int64)
    assert compiled_edit(a, indices, 8) == edit(b, indices, 8)
    np.testing.assert_array_equal(a, b)
